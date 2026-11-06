
-- KINGDRAM: SISTEMA DE ESPIONAJE
-- Migración incremental y no destructiva.

CREATE TABLE IF NOT EXISTS realm_spies (
    realm_id BIGINT PRIMARY KEY
        REFERENCES realms(id) ON DELETE CASCADE,

    quantity INTEGER NOT NULL DEFAULT 0
        CHECK (quantity >= 0),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS espionage_missions (
    id BIGSERIAL PRIMARY KEY,

    attacker_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    target_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    mission_type TEXT NOT NULL
        CHECK (mission_type IN (
            'resources',
            'military',
            'buildings',
            'research'
        )),

    spies_sent INTEGER NOT NULL
        CHECK (spies_sent > 0),

    status TEXT NOT NULL DEFAULT 'travelling'
        CHECK (status IN (
            'travelling',
            'completed',
            'failed',
            'cancelled'
        )),

    departure_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    arrival_at TIMESTAMPTZ NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (attacker_realm_id <> target_realm_id)
);

CREATE INDEX IF NOT EXISTS idx_espionage_arrival
ON espionage_missions(status, arrival_at);

CREATE INDEX IF NOT EXISTS idx_espionage_attacker
ON espionage_missions(attacker_realm_id, status);

CREATE INDEX IF NOT EXISTS idx_espionage_target
ON espionage_missions(target_realm_id, status);

CREATE TABLE IF NOT EXISTS espionage_reports (
    id BIGSERIAL PRIMARY KEY,

    mission_id BIGINT NOT NULL UNIQUE
        REFERENCES espionage_missions(id) ON DELETE CASCADE,

    attacker_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    target_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    mission_type TEXT NOT NULL,

    success BOOLEAN NOT NULL,

    spies_sent INTEGER NOT NULL,

    spies_lost INTEGER NOT NULL DEFAULT 0
        CHECK (spies_lost >= 0),

    intelligence JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_espionage_reports_attacker
ON espionage_reports(attacker_realm_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_espionage_reports_target
ON espionage_reports(target_realm_id, created_at DESC);
