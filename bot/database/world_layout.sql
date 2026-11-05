CREATE TABLE IF NOT EXISTS world_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL
);

DO $$
DECLARE
    current_version TEXT;
    realm_count BIGINT;
BEGIN
    SELECT setting_value
    INTO current_version
    FROM world_settings
    WHERE setting_key = 'layout_version';

    IF current_version IS DISTINCT FROM '2' THEN

        SELECT COUNT(*) INTO realm_count
        FROM realms;

        IF realm_count > 6000 THEN
            RAISE EXCEPTION
                'Hay % reinos, pero el nuevo mapa admite 6000.',
                realm_count;
        END IF;

        DROP INDEX IF EXISTS idx_realms_world_position;

        WITH ranked_realms AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    ORDER BY
                        continent NULLS LAST,
                        region NULLS LAST,
                        position NULLS LAST,
                        id
                ) AS world_order
            FROM realms
        )
        UPDATE realms AS realm
        SET
            continent = (
                (ranked_realms.world_order - 1) / 60
            ) + 1,
            region = (
                ((ranked_realms.world_order - 1) % 60) / 20
            ) + 1,
            position = (
                (ranked_realms.world_order - 1) % 20
            ) + 1
        FROM ranked_realms
        WHERE realm.id = ranked_realms.id;

        INSERT INTO world_settings (
            setting_key,
            setting_value
        )
        VALUES ('layout_version', '2')
        ON CONFLICT (setting_key)
        DO UPDATE SET setting_value = EXCLUDED.setting_value;

    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_realms_world_position
ON realms(continent, region, position)
WHERE continent IS NOT NULL
  AND region IS NOT NULL
  AND position IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_realms_world_region
ON realms(continent, region);
