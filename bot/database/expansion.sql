
-- =========================================================
-- KINGDRAM - EXPANSION DE SISTEMAS
-- Migracion aditiva: no elimina datos existentes.
-- =========================================================

-- ---------------------------------------------------------
-- 1. INVESTIGACION Y TECNOLOGIAS
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS realm_research (
    realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,
    research_type TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0 CHECK (level >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (realm_id, research_type)
);

CREATE TABLE IF NOT EXISTS research_queue (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,
    research_type TEXT NOT NULL,
    target_level INTEGER NOT NULL CHECK (target_level > 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finishes_at TIMESTAMPTZ NOT NULL,
    UNIQUE (realm_id)
);

CREATE INDEX IF NOT EXISTS idx_research_finish
ON research_queue(finishes_at);


-- ---------------------------------------------------------
-- 2. DEFENSAS DEL REINO
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS realm_defenses (
    realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,
    defense_type TEXT NOT NULL,
    quantity BIGINT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (realm_id, defense_type)
);


-- ---------------------------------------------------------
-- 3. INFORMES DE BATALLA
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS battle_reports (
    id BIGSERIAL PRIMARY KEY,
    attacker_realm_id BIGINT
        REFERENCES realms(id) ON DELETE SET NULL,
    defender_realm_id BIGINT
        REFERENCES realms(id) ON DELETE SET NULL,
    winner_realm_id BIGINT
        REFERENCES realms(id) ON DELETE SET NULL,
    battle_type TEXT NOT NULL DEFAULT 'attack',
    attacker_power BIGINT NOT NULL DEFAULT 0,
    defender_power BIGINT NOT NULL DEFAULT 0,
    attacker_losses JSONB NOT NULL DEFAULT '{}'::jsonb,
    defender_losses JSONB NOT NULL DEFAULT '{}'::jsonb,
    loot JSONB NOT NULL DEFAULT '{}'::jsonb,
    infrastructure_damage NUMERIC(5,4) NOT NULL DEFAULT 0
        CHECK (
            infrastructure_damage >= 0
            AND infrastructure_damage <= 1
        ),
    battle_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_battle_attacker_date
ON battle_reports(attacker_realm_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_battle_defender_date
ON battle_reports(defender_realm_id, created_at DESC);


-- ---------------------------------------------------------
-- 4. INFORMES DE ESPIONAJE
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS espionage_reports (
    id BIGSERIAL PRIMARY KEY,
    source_realm_id BIGINT
        REFERENCES realms(id) ON DELETE SET NULL,
    target_realm_id BIGINT
        REFERENCES realms(id) ON DELETE SET NULL,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    detected BOOLEAN NOT NULL DEFAULT FALSE,
    report_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_espionage_target_date
ON espionage_reports(target_realm_id, created_at DESC);


-- ---------------------------------------------------------
-- 5. MERCADO
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS market_offers (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,
    offered_resource TEXT NOT NULL
        CHECK (
            offered_resource IN ('wood', 'stone', 'gold', 'food')
        ),
    offered_amount BIGINT NOT NULL CHECK (offered_amount > 0),
    requested_resource TEXT NOT NULL
        CHECK (
            requested_resource IN ('wood', 'stone', 'gold', 'food')
        ),
    requested_amount BIGINT NOT NULL CHECK (requested_amount > 0),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'completed', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    CHECK (offered_resource <> requested_resource)
);

CREATE INDEX IF NOT EXISTS idx_market_open
ON market_offers(status, expires_at);


-- ---------------------------------------------------------
-- 6. MISIONES Y OBJETIVOS
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS player_missions (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL
        REFERENCES players(id) ON DELETE CASCADE,
    mission_code TEXT NOT NULL,
    progress BIGINT NOT NULL DEFAULT 0 CHECK (progress >= 0),
    target BIGINT NOT NULL CHECK (target > 0),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'claimed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    claimed_at TIMESTAMPTZ,
    UNIQUE (player_id, mission_code)
);

CREATE INDEX IF NOT EXISTS idx_player_missions
ON player_missions(player_id, status);


-- ---------------------------------------------------------
-- 7. ESTADISTICAS Y PUNTUACION
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS realm_statistics (
    realm_id BIGINT PRIMARY KEY
        REFERENCES realms(id) ON DELETE CASCADE,
    economic_points BIGINT NOT NULL DEFAULT 0,
    military_points BIGINT NOT NULL DEFAULT 0,
    research_points BIGINT NOT NULL DEFAULT 0,
    territorial_points BIGINT NOT NULL DEFAULT 0,
    total_points BIGINT NOT NULL DEFAULT 0,
    battles_won BIGINT NOT NULL DEFAULT 0,
    battles_lost BIGINT NOT NULL DEFAULT 0,
    resources_looted BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (economic_points >= 0),
    CHECK (military_points >= 0),
    CHECK (research_points >= 0),
    CHECK (territorial_points >= 0),
    CHECK (total_points >= 0)
);


-- ---------------------------------------------------------
-- 8. HISTORIAL DE TEMPORADAS
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS season_realm_history (
    id BIGSERIAL PRIMARY KEY,
    season_id BIGINT,
    realm_id BIGINT,
    owner_id BIGINT,
    realm_name TEXT NOT NULL,
    final_position INTEGER,
    final_points BIGINT NOT NULL DEFAULT 0,
    economic_points BIGINT NOT NULL DEFAULT 0,
    military_points BIGINT NOT NULL DEFAULT 0,
    research_points BIGINT NOT NULL DEFAULT 0,
    territorial_points BIGINT NOT NULL DEFAULT 0,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------
-- 9. DIPLOMACIA DE ALIANZAS
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS alliance_invitations (
    id BIGSERIAL PRIMARY KEY,
    alliance_id BIGINT NOT NULL
        REFERENCES alliances(id) ON DELETE CASCADE,
    player_id BIGINT NOT NULL
        REFERENCES players(id) ON DELETE CASCADE,
    invited_by BIGINT NOT NULL
        REFERENCES players(id),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN ('pending', 'accepted', 'rejected', 'cancelled')
        ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ,
    UNIQUE (alliance_id, player_id)
);

CREATE TABLE IF NOT EXISTS alliance_treaties (
    id BIGSERIAL PRIMARY KEY,
    alliance_id BIGINT NOT NULL
        REFERENCES alliances(id) ON DELETE CASCADE,
    other_alliance_id BIGINT NOT NULL
        REFERENCES alliances(id) ON DELETE CASCADE,
    treaty_type TEXT NOT NULL
        CHECK (
            treaty_type IN ('non_aggression', 'trade', 'defense')
        ),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN ('pending', 'active', 'ended', 'rejected')
        ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    CHECK (alliance_id <> other_alliance_id)
);

CREATE INDEX IF NOT EXISTS idx_alliance_treaties_active
ON alliance_treaties(alliance_id, status);


-- ---------------------------------------------------------
-- 10. COLA DE EVENTOS ECONOMICOS
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS realm_event_log (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_realm_event_history
ON realm_event_log(realm_id, created_at DESC);


-- =========================================================
-- FIN DE LA EXPANSION
-- =========================================================
