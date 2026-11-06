-- KINGDRAM: reparación temporal de infraestructura
-- y protección contra ciclos de vasallaje.

ALTER TABLE buildings
ADD COLUMN IF NOT EXISTS damaged_levels INTEGER NOT NULL DEFAULT 0;

ALTER TABLE buildings
ADD COLUMN IF NOT EXISTS rebuild_at TIMESTAMPTZ;

UPDATE buildings
SET damaged_levels = 0
WHERE damaged_levels < 0;

-- Resolver vasallajes recíprocos activos existentes.
-- Se conserva la relación creada primero.
UPDATE vassalage_relations newer
SET status = 'ended',
    ended_at = NOW()
WHERE newer.status = 'active'
  AND EXISTS (
      SELECT 1
      FROM vassalage_relations older
      WHERE older.status = 'active'
        AND older.lord_realm_id = newer.vassal_realm_id
        AND older.vassal_realm_id = newer.lord_realm_id
        AND older.id < newer.id
  );

CREATE UNIQUE INDEX IF NOT EXISTS
idx_vassalage_one_active_lord
ON vassalage_relations(vassal_realm_id)
WHERE status = 'active';
