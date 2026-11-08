-- KINGDRAM: sistema de transporte logístico

CREATE TABLE IF NOT EXISTS logistics_missions (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    origin_realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    target_realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,

    caravan_quantity BIGINT NOT NULL CHECK (caravan_quantity > 0),

    wood BIGINT NOT NULL DEFAULT 0 CHECK (wood >= 0),
    stone BIGINT NOT NULL DEFAULT 0 CHECK (stone >= 0),
    gold BIGINT NOT NULL DEFAULT 0 CHECK (gold >= 0),
    food BIGINT NOT NULL DEFAULT 0 CHECK (food >= 0),

    distance DOUBLE PRECISION NOT NULL DEFAULT 0,

    status TEXT NOT NULL DEFAULT 'travelling'
        CHECK (
            status IN (
                'travelling',
                'returning',
                'completed',
                'cancelled'
            )
        ),

    departure_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivery_at TIMESTAMPTZ NOT NULL,
    return_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    CHECK (origin_realm_id <> target_realm_id)
);

CREATE INDEX IF NOT EXISTS idx_logistics_due
ON logistics_missions(status, delivery_at, return_at);
