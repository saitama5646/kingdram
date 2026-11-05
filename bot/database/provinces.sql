-- KINGDRAM: PROVINCIAS Y EXPANSION TERRITORIAL
-- Migracion segura: conserva todos los registros existentes.

ALTER TABLE provinces
    ADD COLUMN IF NOT EXISTS continent INTEGER,
    ADD COLUMN IF NOT EXISTS region INTEGER;

-- Retirar la restriccion incorrecta de la actualizacion anterior.
DROP INDEX IF EXISTS idx_kingdram_one_province_per_realm;

CREATE INDEX IF NOT EXISTS idx_kingdram_provinces_location
ON provinces(continent, region);

-- Impedir nuevas provincias adicionales para un mismo reino
-- y evitar que dos provincias ocupen el mismo territorio.
CREATE OR REPLACE FUNCTION kingdram_validate_province()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM provinces
        WHERE realm_id = NEW.realm_id
          AND id <> COALESCE(NEW.id, 0)
    ) THEN
        RAISE EXCEPTION
            'Este reino ya tiene una provincia.';
    END IF;

    IF NEW.continent IS NOT NULL
       AND NEW.region IS NOT NULL
       AND EXISTS (
            SELECT 1
            FROM provinces
            WHERE continent = NEW.continent
              AND region = NEW.region
              AND id <> COALESCE(NEW.id, 0)
       ) THEN
        RAISE EXCEPTION
            'Ese territorio ya tiene una provincia.';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS kingdram_province_limit
ON provinces;

CREATE TRIGGER kingdram_province_limit
BEFORE INSERT OR UPDATE ON provinces
FOR EACH ROW
EXECUTE FUNCTION kingdram_validate_province();
