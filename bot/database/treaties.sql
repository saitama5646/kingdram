
-- =========================================================
-- KINGDRAM: TRATADOS DE ALIANZAS Y PROVINCIAS UNICAS
-- =========================================================

CREATE TABLE IF NOT EXISTS alliance_treaties (
    id BIGSERIAL PRIMARY KEY,
    alliance_id BIGINT NOT NULL
        REFERENCES alliances(id) ON DELETE CASCADE,
    other_alliance_id BIGINT NOT NULL
        REFERENCES alliances(id) ON DELETE CASCADE,
    treaty_type TEXT NOT NULL
        CHECK (treaty_type IN (
            'non_aggression',
            'trade',
            'defense'
        )),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',
            'active',
            'ended',
            'rejected'
        )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    CHECK (alliance_id <> other_alliance_id)
);

CREATE INDEX IF NOT EXISTS idx_alliance_treaties_active
ON alliance_treaties(alliance_id, status);

CREATE INDEX IF NOT EXISTS idx_alliance_treaties_other
ON alliance_treaties(other_alliance_id, status);

-- Cada reino solo puede poseer una provincia propia.
-- Si existen duplicados antiguos, se detiene la migración
-- para evitar eliminar provincias y datos sin autorización.

DO $$
BEGIN
    IF EXISTS (
        SELECT realm_id
        FROM provinces
        GROUP BY realm_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Hay reinos con varias provincias. '
            'Revisa la tabla provinces antes de aplicar '
            'la restricción de provincia única.';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS
idx_kingdram_one_province_per_realm
ON provinces(realm_id);
