
-- =========================================================
-- KINGDRAM - MAPA MEDIEVAL Y MISIONES
-- Migración incremental: no elimina datos existentes.
-- =========================================================

ALTER TABLE realms
    ADD COLUMN IF NOT EXISTS continent INTEGER,
    ADD COLUMN IF NOT EXISTS region INTEGER,
    ADD COLUMN IF NOT EXISTS position INTEGER;

-- Coordenadas únicas.
CREATE UNIQUE INDEX IF NOT EXISTS idx_realms_world_position
ON realms(continent, region, position)
WHERE continent IS NOT NULL
  AND region IS NOT NULL
  AND position IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_realms_world_region
ON realms(continent, region);

-- Misiones militares persistentes.
CREATE TABLE IF NOT EXISTS military_missions (
    id BIGSERIAL PRIMARY KEY,

    attacker_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    defender_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    mission_type TEXT NOT NULL DEFAULT 'attack'
        CHECK (mission_type IN ('attack', 'return')),

    status TEXT NOT NULL DEFAULT 'travelling'
        CHECK (status IN (
            'travelling',
            'battling',
            'returning',
            'completed',
            'cancelled'
        )),

    origin_continent INTEGER NOT NULL,
    origin_region INTEGER NOT NULL,
    origin_position INTEGER NOT NULL,

    target_continent INTEGER NOT NULL,
    target_region INTEGER NOT NULL,
    target_position INTEGER NOT NULL,

    distance NUMERIC(12,2) NOT NULL DEFAULT 0,

    departure_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    arrival_at TIMESTAMPTZ NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    CHECK (attacker_realm_id <> defender_realm_id)
);

CREATE INDEX IF NOT EXISTS idx_missions_arrival
ON military_missions(status, arrival_at);

CREATE INDEX IF NOT EXISTS idx_missions_attacker
ON military_missions(attacker_realm_id, status);

CREATE TABLE IF NOT EXISTS military_mission_units (
    id BIGSERIAL PRIMARY KEY,

    mission_id BIGINT NOT NULL
        REFERENCES military_missions(id) ON DELETE CASCADE,

    unit_type TEXT NOT NULL,

    quantity INTEGER NOT NULL
        CHECK (quantity > 0),

    surviving_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (surviving_quantity >= 0)
);

CREATE INDEX IF NOT EXISTS idx_mission_units_mission
ON military_mission_units(mission_id);

-- Rondas de batalla.
CREATE TABLE IF NOT EXISTS battle_rounds (
    id BIGSERIAL PRIMARY KEY,

    battle_id BIGINT NOT NULL
        REFERENCES battle_reports(id) ON DELETE CASCADE,

    round_number INTEGER NOT NULL,

    attacker_power BIGINT NOT NULL DEFAULT 0,
    defender_power BIGINT NOT NULL DEFAULT 0,

    attacker_losses BIGINT NOT NULL DEFAULT 0,
    defender_losses BIGINT NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (battle_id, round_number)
);

ALTER TABLE battle_reports
    ADD COLUMN IF NOT EXISTS mission_id BIGINT
    REFERENCES military_missions(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_battle_mission
ON battle_reports(mission_id);

-- Asignar posiciones a los reinos antiguos que no tengan.
DO $$
DECLARE
    realm_record RECORD;
    selected_continent INTEGER;
    selected_region INTEGER;
    selected_position INTEGER;
    found_position BOOLEAN;
BEGIN
    FOR realm_record IN
        SELECT id
        FROM realms
        WHERE continent IS NULL
           OR region IS NULL
           OR position IS NULL
        ORDER BY id
    LOOP
        found_position := FALSE;

        FOR selected_continent IN 1..100 LOOP
            EXIT WHEN found_position;

            FOR selected_region IN 1..20 LOOP
                EXIT WHEN found_position;

                FOR selected_position IN 1..50 LOOP
                    IF NOT EXISTS (
                        SELECT 1
                        FROM realms
                        WHERE continent = selected_continent
                          AND region = selected_region
                          AND position = selected_position
                    ) THEN
                        UPDATE realms
                        SET continent = selected_continent,
                            region = selected_region,
                            position = selected_position
                        WHERE id = realm_record.id;

                        found_position := TRUE;
                        EXIT;
                    END IF;
                END LOOP;
            END LOOP;
        END LOOP;

        IF NOT found_position THEN
            RAISE EXCEPTION
                'No quedan posiciones libres para el reino %',
                realm_record.id;
        END IF;
    END LOOP;
END $$;
