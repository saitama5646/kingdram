-- =========================================================
-- KINGDRAM - MIGRACION UNIFICADA DE SISTEMAS
-- Compatible con las tablas principales de schema.sql
-- =========================================================

-- ---------------------------------------------------------
-- 1. VASALLAJE: COMPATIBILIDAD
-- ---------------------------------------------------------

ALTER TABLE vassalage_requests
ADD COLUMN IF NOT EXISTS destruction_ratio NUMERIC(5,4);

UPDATE vassalage_requests
SET destruction_ratio = 0.50
WHERE destruction_ratio IS NULL;

ALTER TABLE vassalage_requests
ALTER COLUMN destruction_ratio SET DEFAULT 0.50;

ALTER TABLE vassalage_requests
ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ;

ALTER TABLE vassalage_requests
ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_kingdram_vassalage_requests
ON vassalage_requests(vassal_realm_id, status);


-- ---------------------------------------------------------
-- 2. RELACIONES FEUDALES
-- ---------------------------------------------------------

ALTER TABLE vassalage_relations
ADD COLUMN IF NOT EXISTS tribute_rate NUMERIC(5,4)
NOT NULL DEFAULT 0.20;

ALTER TABLE vassalage_relations
ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;

ALTER TABLE vassalage_relations
ADD COLUMN IF NOT EXISTS ended_by_owner_id BIGINT
REFERENCES players(id);

-- Permite que un reino vuelva a ser vasallo después
-- de haber recibido la independencia.
ALTER TABLE vassalage_relations
DROP CONSTRAINT IF EXISTS
vassalage_relations_vassal_realm_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS
idx_kingdram_one_active_lord_per_vassal
ON vassalage_relations(vassal_realm_id)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS
idx_kingdram_active_vassals_by_lord
ON vassalage_relations(lord_realm_id)
WHERE status = 'active';


-- ---------------------------------------------------------
-- 3. REGISTRO DE TRIBUTOS
-- ---------------------------------------------------------

ALTER TABLE vassalage_tribute_log
ADD COLUMN IF NOT EXISTS relation_id BIGINT;

ALTER TABLE vassalage_tribute_log
ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ
NOT NULL DEFAULT NOW();

-- Vincula los registros antiguos cuando sea posible.
UPDATE vassalage_tribute_log AS log
SET relation_id = relation.id
FROM vassalage_relations AS relation
WHERE log.relation_id IS NULL
  AND log.lord_realm_id = relation.lord_realm_id
  AND log.vassal_realm_id = relation.vassal_realm_id;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_kingdram_tribute_relation'
    ) THEN
        ALTER TABLE vassalage_tribute_log
        ADD CONSTRAINT fk_kingdram_tribute_relation
        FOREIGN KEY (relation_id)
        REFERENCES vassalage_relations(id)
        ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS
idx_kingdram_tribute_relation
ON vassalage_tribute_log(relation_id);


-- ---------------------------------------------------------
-- 4. INVESTIGACIONES
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS realm_research (
    realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    research_type TEXT NOT NULL,

    level INTEGER NOT NULL DEFAULT 0,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (realm_id, research_type),

    CHECK (level >= 0)
);


CREATE TABLE IF NOT EXISTS research_queue (
    id BIGSERIAL PRIMARY KEY,

    realm_id BIGINT NOT NULL UNIQUE
        REFERENCES realms(id) ON DELETE CASCADE,

    research_type TEXT NOT NULL,

    target_level INTEGER NOT NULL,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    finishes_at TIMESTAMPTZ NOT NULL,

    CHECK (target_level >= 1)
);

CREATE INDEX IF NOT EXISTS
idx_kingdram_research_finish
ON research_queue(finishes_at);


-- ---------------------------------------------------------
-- 5. ESTADISTICAS
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS realm_statistics (
    realm_id BIGINT PRIMARY KEY
        REFERENCES realms(id) ON DELETE CASCADE,

    building_points BIGINT NOT NULL DEFAULT 0,

    military_points BIGINT NOT NULL DEFAULT 0,

    research_points BIGINT NOT NULL DEFAULT 0,

    total_points BIGINT NOT NULL DEFAULT 0,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------
-- 6. HISTORIAL DE ACTIVIDAD
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS realm_event_log (
    id BIGSERIAL PRIMARY KEY,

    realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    event_type TEXT NOT NULL,

    description TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS
idx_kingdram_event_log_recent
ON realm_event_log(realm_id, created_at DESC);


-- ---------------------------------------------------------
-- 7. VALIDACIONES E INDICES FINALES
-- ---------------------------------------------------------

CREATE INDEX IF NOT EXISTS
idx_kingdram_vassalage_lord
ON vassalage_relations(lord_realm_id);

CREATE INDEX IF NOT EXISTS
idx_kingdram_vassalage_vassal
ON vassalage_relations(vassal_realm_id);

CREATE INDEX IF NOT EXISTS
idx_kingdram_statistics_ranking
ON realm_statistics(total_points DESC);

-- =========================================================
-- FIN DE MIGRACION
-- =========================================================
