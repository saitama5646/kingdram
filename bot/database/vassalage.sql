
-- =========================================
-- KINGDRAM: MIGRACIÓN DEL VASALLAJE
-- =========================================

CREATE TABLE IF NOT EXISTS vassalage_requests (
    id BIGSERIAL PRIMARY KEY,
    lord_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,
    vassal_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,
    destruction_ratio NUMERIC(5,4) NOT NULL
        CHECK (
            destruction_ratio >= 0.50
            AND destruction_ratio <= 1.00
        ),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'accepted',
                'rejected',
                'cancelled'
            )
        ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ,
    CHECK (lord_realm_id <> vassal_realm_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_vassalage_one_pending
ON vassalage_requests(vassal_realm_id)
WHERE status = 'pending';


CREATE TABLE IF NOT EXISTS vassalage_relations (
    id BIGSERIAL PRIMARY KEY,
    lord_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,
    vassal_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'ended')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    ended_by_owner_id BIGINT
        REFERENCES players(id),
    CHECK (lord_realm_id <> vassal_realm_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_vassalage_one_active_lord
ON vassalage_relations(vassal_realm_id)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_vassalage_lord_active
ON vassalage_relations(lord_realm_id)
WHERE status = 'active';


CREATE TABLE IF NOT EXISTS vassalage_tribute_log (
    id BIGSERIAL PRIMARY KEY,
    lord_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,
    vassal_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,
    wood BIGINT NOT NULL DEFAULT 0,
    stone BIGINT NOT NULL DEFAULT 0,
    gold BIGINT NOT NULL DEFAULT 0,
    food BIGINT NOT NULL DEFAULT 0,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vassalage_tribute_history
ON vassalage_tribute_log(lord_realm_id, recorded_at DESC);
