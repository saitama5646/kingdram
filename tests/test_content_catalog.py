import copy
import unittest

from bot.services.content_catalog import (
    BUILDING_FIELDS,
    UNIT_FIELDS,
    RESEARCH_FIELDS,
    assert_valid_content_catalogs,
    get_content_catalog_summary,
    validate_content_catalogs,
)
from bot.services.construction import BUILDINGS
from bot.services.military import UNITS
from bot.services.research import RESEARCH


class ContentCatalogTests(unittest.TestCase):

    def setUp(self):
        self.buildings = copy.deepcopy(BUILDINGS)
        self.units = copy.deepcopy(UNITS)
        self.research = copy.deepcopy(RESEARCH)

    def validate(self):
        return validate_content_catalogs(
            self.buildings,
            self.units,
            self.research,
        )

    def test_existing_catalogs_are_valid(self):
        self.assertEqual(self.validate(), [])

    def test_existing_catalogs_pass_public_assertion(self):
        self.assertTrue(assert_valid_content_catalogs())

    def test_summary_contains_all_catalogs(self):
        summary = get_content_catalog_summary()

        self.assertEqual(summary["buildings"], len(BUILDINGS))
        self.assertEqual(summary["units"], len(UNITS))
        self.assertEqual(summary["research"], len(RESEARCH))

    def test_building_missing_field_is_detected(self):
        code = next(iter(self.buildings))
        del self.buildings[code]["base_time"]

        errors = self.validate()

        self.assertTrue(
            any(
                f"building.{code}" in error
                and "base_time" in error
                for error in errors
            )
        )

    def test_unknown_building_resource_is_detected(self):
        code = next(iter(self.buildings))
        self.buildings[code]["resource"] = "mana"

        errors = self.validate()

        self.assertTrue(
            any("recurso de producción desconocido" in error for error in errors)
        )

    def test_invalid_building_cost_is_detected(self):
        code = next(iter(self.buildings))
        self.buildings[code]["base_cost"]["wood"] = -10

        errors = self.validate()

        self.assertTrue(
            any("coste inválido" in error for error in errors)
        )

    def test_building_time_must_be_positive(self):
        code = next(iter(self.buildings))
        self.buildings[code]["base_time"] = 0

        errors = self.validate()

        self.assertTrue(
            any("base_time" in error for error in errors)
        )

    def test_unit_missing_field_is_detected(self):
        code = next(iter(self.units))
        del self.units[code]["attack"]

        errors = self.validate()

        self.assertTrue(
            any(
                f"unit.{code}" in error and "attack" in error
                for error in errors
            )
        )

    def test_unit_stats_must_be_positive(self):
        code = next(iter(self.units))
        self.units[code]["attack"] = 0

        errors = self.validate()

        self.assertTrue(
            any("attack" in error for error in errors)
        )

    def test_unit_cost_cannot_be_negative(self):
        code = next(iter(self.units))
        self.units[code]["gold"] = -1

        errors = self.validate()

        self.assertTrue(
            any("coste inválido" in error for error in errors)
        )

    def test_research_missing_field_is_detected(self):
        code = next(iter(self.research))
        del self.research[code]["effects"]

        errors = self.validate()

        self.assertTrue(
            any(
                f"research.{code}" in error and "effects" in error
                for error in errors
            )
        )

    def test_unknown_research_requirement_is_detected(self):
        code = next(iter(self.research))
        self.research[code]["requirements"]["missing_technology"] = 1

        errors = self.validate()

        self.assertTrue(
            any("missing_technology" in error for error in errors)
        )

    def test_unknown_building_requirement_is_detected(self):
        code = next(iter(self.research))
        self.research[code]["building_requirements"]["missing_building"] = 1

        errors = self.validate()

        self.assertTrue(
            any("missing_building" in error for error in errors)
        )

    def test_research_cycle_is_detected(self):
        codes = list(self.research)

        self.research[codes[0]]["requirements"] = {codes[1]: 1}
        self.research[codes[1]]["requirements"] = {codes[0]: 1}

        errors = self.validate()

        self.assertTrue(
            any("dependencia circular" in error for error in errors)
        )

    def test_invalid_research_effect_is_detected(self):
        code = next(iter(self.research))
        self.research[code]["effects"]["food_production"] = float("inf")

        errors = self.validate()

        self.assertTrue(
            any("valor inválido" in error for error in errors)
        )

    def test_invalid_catalog_type_is_detected(self):
        errors = validate_content_catalogs(
            buildings=[],
            units=self.units,
            research=self.research,
        )

        self.assertTrue(
            any("catálogo de edificios" in error for error in errors)
        )

    def test_catalog_definitions_are_not_modified(self):
        before = (
            copy.deepcopy(BUILDINGS),
            copy.deepcopy(UNITS),
            copy.deepcopy(RESEARCH),
        )

        validate_content_catalogs()

        self.assertEqual(BUILDINGS, before[0])
        self.assertEqual(UNITS, before[1])
        self.assertEqual(RESEARCH, before[2])


if __name__ == "__main__":
    unittest.main()
