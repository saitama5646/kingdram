-- =========================================
-- KINGDRAM: UNA PROVINCIA POR REINO
-- =========================================

-- Si existen provincias duplicadas, conservar
-- la más antigua de cada reino.
DELETE FROM provinces
WHERE id IN (
    SELECT id
    FROM (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY realm_id
                ORDER BY created_at ASC, id ASC
            ) AS position
        FROM provinces
    ) ranked
    WHERE position > 1
);

-- Impedir que un reino pueda tener otra provincia.
CREATE UNIQUE INDEX IF NOT EXISTS
idx_kingdram_one_province_per_realm
ON provinces(realm_id);

