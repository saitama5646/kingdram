-- KINGDRAM: BALANCE ECONÓMICO
-- Reduce las reservas actuales un 90 % una única vez.

CREATE TABLE IF NOT EXISTS kingdram_balance_migrations (
    migration_key TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE resources
    ALTER COLUMN wood SET DEFAULT 180,
    ALTER COLUMN stone SET DEFAULT 120,
    ALTER COLUMN gold SET DEFAULT 50,
    ALTER COLUMN food SET DEFAULT 160;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM kingdram_balance_migrations
        WHERE migration_key = 'economy_balance_xnova_v1'
    ) THEN

        UPDATE resources
        SET
            wood = FLOOR(wood * 0.10)::BIGINT,
            stone = FLOOR(stone * 0.10)::BIGINT,
            gold = FLOOR(gold * 0.10)::BIGINT,
            food = FLOOR(food * 0.10)::BIGINT,
            updated_at = NOW();

        INSERT INTO kingdram_balance_migrations (
            migration_key
        )
        VALUES (
            'economy_balance_xnova_v1'
        );

    END IF;
END $$;
