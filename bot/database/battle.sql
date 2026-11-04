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

    winner_realm_id BIGINT NOT NULL
        REFERENCES realms(id) ON DELETE CASCADE,

    attacker_power BIGINT NOT NULL DEFAULT 0,
    defender_power BIGINT NOT NULL DEFAULT 0,

    attacker_losses BIGINT NOT NULL DEFAULT 0,
    defender_losses BIGINT NOT NULL DEFAULT 0,

    infrastructure_before BIGINT NOT NULL DEFAULT 0,
    infrastructure_after BIGINT NOT NULL DEFAULT 0,
    infrastructure_damage NUMERIC(7,5) NOT NULL DEFAULT 0,

    vassalage_unlocked BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (attacker_realm_id <> defender_realm_id),
    CHECK (infrastructure_damage >= 0 AND infrastructure_damage <= 1)
);

CREATE INDEX IF NOT EXISTS idx_battle_reports_attacker
ON battle_reports(attacker_realm_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_battle_reports_defender
ON battle_reports(defender_realm_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_battle_reports_created
ON battle_reports(created_at DESC);


-- Historial detallado de las unidades que participaron.
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
    CHECK (remaining_quantity >= 0)
);

CREATE INDEX IF NOT EXISTS idx_battle_unit_results_battle
ON battle_unit_results(battle_id);
