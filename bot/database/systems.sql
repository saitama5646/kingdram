
-- =========================================================
-- KINGDRAM - SISTEMAS ECONOMICOS, DIPLOMATICOS Y TECNOLOGICOS
-- =========================================================

-- VASALLAJE
CREATE TABLE IF NOT EXISTS vassalage_requests (
    id BIGSERIAL PRIMARY KEY,
    lord_realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    vassal_realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    infrastructure_damage NUMERIC(6,5) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ,
    CHECK (lord_realm_id <> vassal_realm_id),
    CHECK (infrastructure_damage >= 0 AND infrastructure_damage <= 1),
    CHECK (status IN ('pending', 'accepted', 'rejected', 'cancelled'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_one_pending_vassalage_request
ON vassalage_requests(vassal_realm_id)
WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS vassalage_relations (
    id BIGSERIAL PRIMARY KEY,
    lord_realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    vassal_realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active',
    tribute_rate NUMERIC(5,4) NOT NULL DEFAULT 0.20,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    ended_by_owner_id BIGINT REFERENCES players(id),
    CHECK (lord_realm_id <> vassal_realm_id),
    CHECK (tribute_rate >= 0 AND tribute_rate <= 1),
    CHECK (status IN ('active', 'ended'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_lord_per_vassal
ON vassalage_relations(vassal_realm_id)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_active_vassals_by_lord
ON vassalage_relations(lord_realm_id)
WHERE status = 'active';


-- REGISTRO DE TRIBUTOS
CREATE TABLE IF NOT EXISTS vassalage_tribute_log (
    id BIGSERIAL PRIMARY KEY,
    relation_id BIGINT NOT NULL REFERENCES vassalage_relations(id) ON DELETE CASCADE,
    wood BIGINT NOT NULL DEFAULT 0,
    stone BIGINT NOT NULL DEFAULT 0,
    gold BIGINT NOT NULL DEFAULT 0,
    food BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- INVESTIGACIONES
CREATE TABLE IF NOT EXISTS realm_research (
    realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    research_type TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (realm_id, research_type),
    CHECK (level >= 0)
);

CREATE TABLE IF NOT EXISTS research_queue (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL UNIQUE REFERENCES realms(id) ON DELETE CASCADE,
    research_type TEXT NOT NULL,
    target_level INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finishes_at TIMESTAMPTZ NOT NULL,
    CHECK (target_level >= 1)
);

CREATE INDEX IF NOT EXISTS idx_research_queue_finish
ON research_queue(finishes_at);


-- PUNTUACION Y ESTADISTICAS
CREATE TABLE IF NOT EXISTS realm_statistics (
    realm_id BIGINT PRIMARY KEY REFERENCES realms(id) ON DELETE CASCADE,
    building_points BIGINT NOT NULL DEFAULT 0,
    military_points BIGINT NOT NULL DEFAULT 0,
    research_points BIGINT NOT NULL DEFAULT 0,
    total_points BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- REGISTRO DE ACTIVIDAD DEL REINO
CREATE TABLE IF NOT EXISTS realm_event_log (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_realm_event_log_recent
ON realm_event_log(realm_id, created_at DESC);
