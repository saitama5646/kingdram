
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


-- ---------------------------------------------------------
-- TRIBUTO FEUDAL
-- ---------------------------------------------------------

ALTER TABLE vassalage_relations
ADD COLUMN IF NOT EXISTS tribute_rate NUMERIC(5,4)
NOT NULL DEFAULT 0.20;

ALTER TABLE vassalage_relations
ADD CONSTRAINT chk_vassalage_tribute_rate
CHECK (
    tribute_rate >= 0
    AND tribute_rate <= 1
);

-- Relacionar cada registro de tributo con su vasallaje.
ALTER TABLE vassalage_tribute_log
ADD COLUMN IF NOT EXISTS relation_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_vassalage_tribute_relation'
          AND conrelid = 'vassalage_tribute_log'::regclass
    ) THEN
        ALTER TABLE vassalage_tribute_log
        ADD CONSTRAINT fk_vassalage_tribute_relation
        FOREIGN KEY (relation_id)
        REFERENCES vassalage_relations(id)
        ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS
idx_vassalage_tribute_relation
ON vassalage_tribute_log(relation_id, recorded_at DESC);
