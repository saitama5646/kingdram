-- =========================================================
-- KINGDRAM - SISTEMA DE GUERRA Y REGISTRO DE BATALLAS
-- =========================================================

CREATE TABLE IF NOT EXISTS battle_reports (
    id BIGSERIAL PRIMARY KEY,

    attacker_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    defender_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    attacker_owner_id BIGINT NOT NULL
        REFERENCES players(id) ON DELETE CASCADE,

    defender_owner_id BIGINT NOT NULL
        REFERENCES players(id) ON DELETE CASCADE,

    winner_realm_id BIGINT
        REFERENCES realms(id) ON DELETE SET NULL,

    attacker_power BIGINT NOT NULL DEFAULT 0,
    defender_power BIGINT NOT NULL DEFAULT 0,

    attacker_losses BIGINT NOT NULL DEFAULT 0,
    defender_losses BIGINT NOT NULL DEFAULT 0,

    infrastructure_before BIGINT NOT NULL DEFAULT 0,
    infrastructure_after BIGINT NOT NULL DEFAULT 0,
    infrastructure_damage NUMERIC(7,5) NOT NULL DEFAULT 0,

    vassalage_unlocked BOOLEAN NOT NULL DEFAULT FALSE,

    outcome TEXT NOT NULL DEFAULT 'unknown',
    rounds INTEGER NOT NULL DEFAULT 0,

    attacker_morale NUMERIC(5,3) NOT NULL DEFAULT 1.0,
    defender_morale NUMERIC(5,3) NOT NULL DEFAULT 1.0,

    round_log JSONB NOT NULL DEFAULT '[]'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (attacker_realm_id <> defender_realm_id),
    CHECK (infrastructure_damage >= 0 AND infrastructure_damage <= 1),
    CHECK (rounds >= 0),
    CHECK (attacker_morale >= 0 AND attacker_morale <= 1.25),
    CHECK (defender_morale >= 0 AND defender_morale <= 1.25)
);


-- =========================================================
-- MIGRACIONES PARA BASES DE DATOS EXISTENTES
-- =========================================================

ALTER TABLE battle_reports
    ALTER COLUMN winner_realm_id DROP NOT NULL;

ALTER TABLE battle_reports
ADD COLUMN IF NOT EXISTS infrastructure_before BIGINT NOT NULL DEFAULT 0;

ALTER TABLE battle_reports
ADD COLUMN IF NOT EXISTS infrastructure_after BIGINT NOT NULL DEFAULT 0;

ALTER TABLE battle_reports
ADD COLUMN IF NOT EXISTS infrastructure_damage NUMERIC(7,5) NOT NULL DEFAULT 0;

ALTER TABLE battle_reports
ADD COLUMN IF NOT EXISTS vassalage_unlocked BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE battle_reports
ADD COLUMN IF NOT EXISTS outcome TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE battle_reports
ADD COLUMN IF NOT EXISTS rounds INTEGER NOT NULL DEFAULT 0;

ALTER TABLE battle_reports
ADD COLUMN IF NOT EXISTS attacker_morale NUMERIC(5,3) NOT NULL DEFAULT 1.0;

ALTER TABLE battle_reports
ADD COLUMN IF NOT EXISTS defender_morale NUMERIC(5,3) NOT NULL DEFAULT 1.0;

ALTER TABLE battle_reports
ADD COLUMN IF NOT EXISTS round_log JSONB NOT NULL DEFAULT '[]'::JSONB;


-- =========================================================
-- ÍNDICES DE INFORMES
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_battle_reports_attacker
ON battle_reports(attacker_realm_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_battle_reports_defender
ON battle_reports(defender_realm_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_battle_reports_created
ON battle_reports(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_battle_reports_attacker_owner
ON battle_reports(attacker_owner_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_battle_reports_defender_owner
ON battle_reports(defender_owner_id, created_at DESC);


-- =========================================================
-- RESULTADOS POR UNIDAD
-- =========================================================

CREATE TABLE IF NOT EXISTS battle_unit_results (
    id BIGSERIAL PRIMARY KEY,

    battle_id BIGINT NOT NULL
        REFERENCES battle_reports(id) ON DELETE CASCADE,

    realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    unit_type TEXT NOT NULL,

    initial_quantity BIGINT NOT NULL DEFAULT 0,
    lost_quantity BIGINT NOT NULL DEFAULT 0,
    remaining_quantity BIGINT NOT NULL DEFAULT 0,

    CHECK (initial_quantity >= 0),
    CHECK (lost_quantity >= 0),
    CHECK (remaining_quantity >= 0),
    CHECK (lost_quantity <= initial_quantity)
);


-- =========================================================
-- ÍNDICES DE RESULTADOS
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_battle_unit_results_battle
ON battle_unit_results(battle_id);

CREATE INDEX IF NOT EXISTS idx_battle_unit_results_realm
ON battle_unit_results(realm_id, battle_id);
