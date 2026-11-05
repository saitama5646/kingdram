
-- =========================================================
-- KINGDRAM - COLAS SECUENCIALES
-- =========================================================

-- ---------------------------------------------------------
-- COLA DE CONSTRUCCIÓN
-- ---------------------------------------------------------

ALTER TABLE construction_queue
ADD COLUMN IF NOT EXISTS queue_position INTEGER;

WITH ordered AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY realm_id
            ORDER BY finishes_at, id
        ) AS position
    FROM construction_queue
)
UPDATE construction_queue AS queue
SET queue_position = ordered.position
FROM ordered
WHERE queue.id = ordered.id
  AND queue.queue_position IS NULL;

ALTER TABLE construction_queue
ALTER COLUMN queue_position SET DEFAULT 1;

ALTER TABLE construction_queue
ALTER COLUMN queue_position SET NOT NULL;

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    FOR constraint_name IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'construction_queue'::regclass
          AND contype = 'u'
    LOOP
        EXECUTE format(
            'ALTER TABLE construction_queue DROP CONSTRAINT %I',
            constraint_name
        );
    END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS
idx_kingdram_construction_queue_position
ON construction_queue(realm_id, queue_position);

CREATE INDEX IF NOT EXISTS
idx_kingdram_construction_queue_finish
ON construction_queue(finishes_at);


-- ---------------------------------------------------------
-- COLA DE INVESTIGACIÓN
-- ---------------------------------------------------------

ALTER TABLE research_queue
ADD COLUMN IF NOT EXISTS queue_position INTEGER;

WITH ordered AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY realm_id
            ORDER BY finishes_at, id
        ) AS position
    FROM research_queue
)
UPDATE research_queue AS queue
SET queue_position = ordered.position
FROM ordered
WHERE queue.id = ordered.id
  AND queue.queue_position IS NULL;

ALTER TABLE research_queue
ALTER COLUMN queue_position SET DEFAULT 1;

ALTER TABLE research_queue
ALTER COLUMN queue_position SET NOT NULL;

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    FOR constraint_name IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'research_queue'::regclass
          AND contype = 'u'
    LOOP
        EXECUTE format(
            'ALTER TABLE research_queue DROP CONSTRAINT %I',
            constraint_name
        );
    END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS
idx_kingdram_research_queue_position
ON research_queue(realm_id, queue_position);

CREATE INDEX IF NOT EXISTS
idx_kingdram_research_queue_finish
ON research_queue(finishes_at);

-- =========================================================
-- FIN
-- =========================================================
