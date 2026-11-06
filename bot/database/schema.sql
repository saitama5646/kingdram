-- =========================================================
-- KINGDRAM - ESQUEMA PRINCIPAL Y MIGRACIÓN
-- =========================================================

-- ---------------------------------------------------------
-- 1. JUGADORES
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS players (
    id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT NOT NULL DEFAULT 'Jugador',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE players ADD COLUMN IF NOT EXISTS id BIGINT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS username TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS first_name TEXT DEFAULT 'Jugador';
ALTER TABLE players ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'players'
          AND column_name = 'telegram_id'
    ) THEN
        UPDATE players
        SET id = telegram_id
        WHERE id IS NULL;
    END IF;
END $$;

UPDATE players SET first_name = 'Jugador' WHERE first_name IS NULL;
UPDATE players SET created_at = NOW() WHERE created_at IS NULL;

ALTER TABLE players ALTER COLUMN id SET NOT NULL;
ALTER TABLE players ALTER COLUMN first_name SET DEFAULT 'Jugador';
ALTER TABLE players ALTER COLUMN first_name SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_kingdram_players_id
ON players(id);

-- Sincroniza el identificador interno con Telegram.
CREATE OR REPLACE FUNCTION kingdram_sync_player_ids()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.id IS NULL THEN
        NEW.id := NEW.telegram_id;
    END IF;

    IF NEW.telegram_id IS NULL THEN
        NEW.telegram_id := NEW.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS kingdram_player_ids_trigger ON players;

CREATE TRIGGER kingdram_player_ids_trigger
BEFORE INSERT OR UPDATE ON players
FOR EACH ROW
EXECUTE FUNCTION kingdram_sync_player_ids();


-- ---------------------------------------------------------
-- 2. TEMPORADAS
-- ---------------------------------------------------------

-- La tabla seasons existente se conserva.
-- Se utiliza la temporada más reciente como predeterminada.

DO $$
DECLARE
    current_season BIGINT;
BEGIN
    IF to_regclass('public.seasons') IS NOT NULL
       AND to_regclass('public.realms') IS NOT NULL
       AND EXISTS (
           SELECT 1
           FROM information_schema.columns
           WHERE table_schema = 'public'
             AND table_name = 'realms'
             AND column_name = 'season_id'
       ) THEN
        EXECUTE 'SELECT MAX(id) FROM public.seasons'
        INTO current_season;

        IF current_season IS NOT NULL THEN
            EXECUTE format(
                'ALTER TABLE public.realms ALTER COLUMN season_id SET DEFAULT %s',
                current_season
            );
        END IF;
    END IF;
END $$;


-- ---------------------------------------------------------
-- 3. REINOS
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS realms (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL UNIQUE REFERENCES players(id),
    name TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    population INTEGER NOT NULL DEFAULT 120,
    power INTEGER NOT NULL DEFAULT 100,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE realms ADD COLUMN IF NOT EXISTS owner_id BIGINT;
ALTER TABLE realms ADD COLUMN IF NOT EXISTS level INTEGER NOT NULL DEFAULT 1;
ALTER TABLE realms ADD COLUMN IF NOT EXISTS population INTEGER NOT NULL DEFAULT 120;
ALTER TABLE realms ADD COLUMN IF NOT EXISTS power INTEGER NOT NULL DEFAULT 100;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'realms'
          AND column_name = 'telegram_id'
    ) THEN
        UPDATE realms
        SET owner_id = telegram_id
        WHERE owner_id IS NULL;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_kingdram_realms_owner
ON realms(owner_id);

CREATE INDEX IF NOT EXISTS idx_kingdram_realms_power
ON realms(power DESC);

CREATE OR REPLACE FUNCTION kingdram_sync_realm_owner()
RETURNS TRIGGER AS $$
DECLARE
    legacy_telegram_id BIGINT;
BEGIN
    legacy_telegram_id := NULLIF(
        to_jsonb(NEW)->>'telegram_id', ''
    )::BIGINT;

    IF NEW.owner_id IS NULL THEN
        NEW.owner_id := legacy_telegram_id;
    END IF;

    IF to_jsonb(NEW) ? 'telegram_id'
       AND legacy_telegram_id IS NULL THEN
        NEW := jsonb_populate_record(
            NEW,
            jsonb_build_object('telegram_id', NEW.owner_id)
        );
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS kingdram_realm_owner_trigger ON realms;

CREATE TRIGGER kingdram_realm_owner_trigger
BEFORE INSERT OR UPDATE ON realms
FOR EACH ROW
EXECUTE FUNCTION kingdram_sync_realm_owner();


-- ---------------------------------------------------------
-- 4. RECURSOS
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS resources (
    realm_id BIGINT PRIMARY KEY REFERENCES realms(id) ON DELETE CASCADE,
    wood BIGINT NOT NULL DEFAULT 1800,
    stone BIGINT NOT NULL DEFAULT 1200,
    gold BIGINT NOT NULL DEFAULT 500,
    food BIGINT NOT NULL DEFAULT 1600,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (wood >= 0),
    CHECK (stone >= 0),
    CHECK (gold >= 0),
    CHECK (food >= 0)
);


-- ---------------------------------------------------------
-- 5. EDIFICIOS
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS buildings (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    building_type TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (realm_id, building_type),
    CHECK (level >= 1)
);


-- ---------------------------------------------------------
-- 6. TERRITORIOS
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS provinces (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    province_number INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (realm_id, province_number)
);


-- ---------------------------------------------------------
-- 7. COLA DE CONSTRUCCIÓN
-- ---------------------------------------------------------

-- Conservamos la cola antigua si su estructura no es compatible.

DO $$
BEGIN
    IF to_regclass('public.construction_queue') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM information_schema.columns
           WHERE table_schema = 'public'
             AND table_name = 'construction_queue'
             AND column_name = 'building_type'
       )
       AND to_regclass('public.legacy_construction_queue') IS NULL
    THEN
        ALTER TABLE construction_queue
        RENAME TO legacy_construction_queue;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS construction_queue (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    building_type TEXT NOT NULL,
    target_level INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finishes_at TIMESTAMPTZ NOT NULL,
    CHECK (target_level >= 1),
    UNIQUE (realm_id, building_type)
);


-- ---------------------------------------------------------
-- 8. EJÉRCITO
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS army (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    unit_type TEXT NOT NULL,
    quantity BIGINT NOT NULL DEFAULT 0,
    UNIQUE (realm_id, unit_type),
    CHECK (quantity >= 0)
);


-- ---------------------------------------------------------
-- 9. ENTRENAMIENTO
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS training_queue (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    unit_type TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    finishes_at TIMESTAMPTZ NOT NULL,
    CHECK (quantity > 0)
);


-- ---------------------------------------------------------
-- 10. ALIANZAS
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS alliances (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    leader_id BIGINT NOT NULL REFERENCES players(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alliance_members (
    alliance_id BIGINT NOT NULL REFERENCES alliances(id) ON DELETE CASCADE,
    player_id BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (alliance_id, player_id),
    UNIQUE (player_id)
);


-- ---------------------------------------------------------
-- 11. ÍNDICES
-- ---------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_kingdram_provinces_realm
ON provinces(realm_id);

CREATE INDEX IF NOT EXISTS idx_kingdram_construction_finish
ON construction_queue(finishes_at);

CREATE INDEX IF NOT EXISTS idx_kingdram_training_finish
ON training_queue(finishes_at);

CREATE INDEX IF NOT EXISTS idx_kingdram_buildings_realm
ON buildings(realm_id);

CREATE INDEX IF NOT EXISTS idx_kingdram_army_realm
ON army(realm_id);

CREATE INDEX IF NOT EXISTS idx_kingdram_alliance_leader
ON alliances(leader_id);

-- =========================================================
-- COMPATIBILIDAD CON PERFILES ANTIGUOS
-- =========================================================

ALTER TABLE players
ADD COLUMN IF NOT EXISTS display_name TEXT;

ALTER TABLE players
ALTER COLUMN display_name SET DEFAULT 'Jugador';

UPDATE players
SET display_name = COALESCE(
    NULLIF(first_name, ''),
    NULLIF(username, ''),
    'Jugador'
)
WHERE display_name IS NULL OR BTRIM(display_name) = '';

ALTER TABLE players
ALTER COLUMN display_name SET NOT NULL;

CREATE OR REPLACE FUNCTION kingdram_sync_player_ids()
RETURNS TRIGGER AS $$
DECLARE
    old_telegram_id BIGINT;
BEGIN
    old_telegram_id := NULLIF(
        to_jsonb(NEW)->>'telegram_id', ''
    )::BIGINT;

    IF NEW.id IS NULL THEN
        NEW.id := old_telegram_id;
    END IF;

    IF to_jsonb(NEW) ? 'telegram_id'
       AND old_telegram_id IS NULL THEN
        NEW := jsonb_populate_record(
            NEW,
            jsonb_build_object('telegram_id', NEW.id)
        );
    END IF;

    IF NEW.display_name IS NULL
       OR BTRIM(NEW.display_name) = ''
       OR NEW.display_name = 'Jugador' THEN

        NEW.display_name := COALESCE(
            NULLIF(NEW.first_name, ''),
            NULLIF(NEW.username, ''),
            'Jugador'
        );
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =========================================
-- KINGDRAM: SISTEMA DE VASALLAJE
-- =========================================

CREATE TABLE IF NOT EXISTS vassalage_requests (
    id BIGSERIAL PRIMARY KEY,
    lord_realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    vassal_realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    destruction_ratio NUMERIC(5,4) NOT NULL
        CHECK (destruction_ratio >= 0.50 AND destruction_ratio <= 1),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'rejected', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ,
    CHECK (lord_realm_id <> vassal_realm_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_vassalage_pending
ON vassalage_requests(vassal_realm_id)
WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS vassalage_relations (
    id BIGSERIAL PRIMARY KEY,
    lord_realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    vassal_realm_id BIGINT NOT NULL UNIQUE REFERENCES realms(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'ended')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    ended_by_owner_id BIGINT REFERENCES players(id),
    CHECK (lord_realm_id <> vassal_realm_id)
);

CREATE INDEX IF NOT EXISTS idx_vassalage_lord
ON vassalage_relations(lord_realm_id)
WHERE status = 'active';

CREATE TABLE IF NOT EXISTS vassalage_tribute_log (
    id BIGSERIAL PRIMARY KEY,
    lord_realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    vassal_realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    wood BIGINT NOT NULL DEFAULT 0,
    stone BIGINT NOT NULL DEFAULT 0,
    gold BIGINT NOT NULL DEFAULT 0,
    food BIGINT NOT NULL DEFAULT 0,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vassalage_tribute_date
ON vassalage_tribute_log(lord_realm_id, recorded_at DESC);
