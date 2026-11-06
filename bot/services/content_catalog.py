from math import isfinite
from numbers import Real

from bot.services.construction import BUILDINGS
from bot.services.military import UNITS
from bot.services.research import RESEARCH


RESOURCES = {"wood", "stone", "gold", "food"}

BUILDING_FIELDS = {
    "name",
    "description",
    "resource",
    "base_cost",
    "base_time",
    "production",
}

UNIT_FIELDS = {
    "name",
    "description",
    "attack",
    "defense",
    "shield",
    "hull",
    "wood",
    "stone",
    "gold",
    "food",
    "seconds",
    "barracks",
}

RESEARCH_FIELDS = {
    "name",
    "description",
    "branch",
    "base_cost",
    "base_time",
    "requirements",
    "building_requirements",
    "effects",
}


def _valid_number(value, minimum=None, integer=False):
    if isinstance(value, bool):
        return False

    if not isinstance(value, Real):
        return False

    if not isfinite(value):
        return False

    if integer and not isinstance(value, int):
        return False

    if minimum is not None and value < minimum:
        return False

    return True


def _validate_cost(cost, location, errors):
    if not isinstance(cost, dict) or not cost:
        errors.append(f"{location}: base_cost debe ser un diccionario no vacío.")
        return

    for resource, amount in cost.items():
        if resource not in RESOURCES:
            errors.append(
                f"{location}: recurso de coste desconocido '{resource}'."
            )
            continue

        if not _valid_number(amount, minimum=1, integer=True):
            errors.append(
                f"{location}: coste inválido para '{resource}'."
            )


def _validate_required_fields(catalog, fields, category, errors):
    for code, data in catalog.items():
        if not isinstance(code, str) or not code.strip():
            errors.append(f"{category}: identificador vacío o inválido.")
            continue

        if not isinstance(data, dict):
            errors.append(f"{category}.{code}: definición inválida.")
            continue

        missing = fields - data.keys()

        for field in sorted(missing):
            errors.append(
                f"{category}.{code}: falta el campo '{field}'."
            )


def _validate_buildings(buildings, errors):
    _validate_required_fields(
        buildings,
        BUILDING_FIELDS,
        "building",
        errors,
    )

    for code, data in buildings.items():
        if not isinstance(data, dict):
            continue

        if not BUILDING_FIELDS.issubset(data):
            continue

        if not isinstance(data["name"], str) or not data["name"].strip():
            errors.append(f"building.{code}: nombre inválido.")

        if not isinstance(data["description"], str) or not data["description"].strip():
            errors.append(f"building.{code}: descripción inválida.")

        resource = data["resource"]

        if resource is not None and resource not in RESOURCES:
            errors.append(
                f"building.{code}: recurso de producción desconocido '{resource}'."
            )

        _validate_cost(
            data["base_cost"],
            f"building.{code}",
            errors,
        )

        if not _valid_number(data["base_time"], minimum=1, integer=True):
            errors.append(f"building.{code}: base_time debe ser un entero positivo.")

        if not _valid_number(data["production"], minimum=0, integer=True):
            errors.append(f"building.{code}: production debe ser un entero no negativo.")

        if resource is None and data["production"] != 0:
            errors.append(
                f"building.{code}: un edificio sin recurso no puede producir recursos."
            )


def _validate_units(units, buildings, errors):
    _validate_required_fields(
        units,
        UNIT_FIELDS,
        "unit",
        errors,
    )

    for code, data in units.items():
        if not isinstance(data, dict):
            continue

        if not UNIT_FIELDS.issubset(data):
            continue

        for field in ("name", "description"):
            if not isinstance(data[field], str) or not data[field].strip():
                errors.append(f"unit.{code}: campo '{field}' inválido.")

        for field in ("attack", "defense", "shield", "hull", "seconds", "barracks"):
            if not _valid_number(data[field], minimum=1, integer=True):
                errors.append(
                    f"unit.{code}: '{field}' debe ser un entero positivo."
                )

        for resource in RESOURCES:
            if not _valid_number(data[resource], minimum=0, integer=True):
                errors.append(
                    f"unit.{code}: coste inválido para '{resource}'."
                )

        if "barracks" in buildings and data["barracks"] < 1:
            errors.append(
                f"unit.{code}: el requisito de cuartel debe ser positivo."
            )

    if units and "barracks" not in buildings:
        errors.append(
            "unit: existe contenido militar, pero falta el edificio 'barracks'."
        )


def _validate_research(research, buildings, errors):
    _validate_required_fields(
        research,
        RESEARCH_FIELDS,
        "research",
        errors,
    )

    for code, data in research.items():
        if not isinstance(data, dict):
            continue

        if not RESEARCH_FIELDS.issubset(data):
            continue

        for field in ("name", "description", "branch"):
            if not isinstance(data[field], str) or not data[field].strip():
                errors.append(
                    f"research.{code}: campo '{field}' inválido."
                )

        _validate_cost(
            data["base_cost"],
            f"research.{code}",
            errors,
        )

        if not _valid_number(data["base_time"], minimum=1, integer=True):
            errors.append(
                f"research.{code}: base_time debe ser un entero positivo."
            )

        requirements = data["requirements"]
        building_requirements = data["building_requirements"]
        effects = data["effects"]

        if not isinstance(requirements, dict):
            errors.append(
                f"research.{code}: requirements debe ser un diccionario."
            )
            requirements = {}

        if not isinstance(building_requirements, dict):
            errors.append(
                f"research.{code}: building_requirements debe ser un diccionario."
            )
            building_requirements = {}

        if not isinstance(effects, dict):
            errors.append(
                f"research.{code}: effects debe ser un diccionario."
            )
            effects = {}

        for required_research, level in requirements.items():
            if required_research not in research:
                errors.append(
                    f"research.{code}: requisito inexistente '{required_research}'."
                )

            if not _valid_number(level, minimum=1, integer=True):
                errors.append(
                    f"research.{code}: nivel requerido inválido para '{required_research}'."
                )

        for building, level in building_requirements.items():
            if building not in buildings:
                errors.append(
                    f"research.{code}: edificio requerido inexistente '{building}'."
                )

            if not _valid_number(level, minimum=1, integer=True):
                errors.append(
                    f"research.{code}: nivel de edificio inválido para '{building}'."
                )

        for effect, value in effects.items():
            if not isinstance(effect, str) or not effect.strip():
                errors.append(
                    f"research.{code}: identificador de efecto inválido."
                )

            if not _valid_number(value):
                errors.append(
                    f"research.{code}: valor inválido para el efecto '{effect}'."
                )

    _validate_research_cycles(research, errors)


def _validate_research_cycles(research, errors):
    visited = set()
    active = set()
    reported = set()

    def visit(code, path):
        if code in active:
            cycle_start = path.index(code)
            cycle = tuple(path[cycle_start:] + [code])

            if cycle not in reported:
                reported.add(cycle)
                errors.append(
                    "research: dependencia circular detectada: "
                    + " -> ".join(cycle)
                )
            return

        if code in visited:
            return

        data = research.get(code)

        if not isinstance(data, dict):
            return

        requirements = data.get("requirements", {})

        if not isinstance(requirements, dict):
            return

        active.add(code)
        path.append(code)

        for dependency in requirements:
            if dependency in research:
                visit(dependency, path)

        path.pop()
        active.remove(code)
        visited.add(code)

    for code in research:
        visit(code, [])


def validate_content_catalogs(
    buildings=None,
    units=None,
    research=None,
):
    """
    Valida los catálogos sin modificar sus definiciones.

    Devuelve una lista de errores. Una lista vacía significa
    que las definiciones superaron las validaciones.
    """

    buildings = BUILDINGS if buildings is None else buildings
    units = UNITS if units is None else units
    research = RESEARCH if research is None else research

    errors = []

    if not isinstance(buildings, dict):
        return ["El catálogo de edificios debe ser un diccionario."]

    if not isinstance(units, dict):
        return ["El catálogo de unidades debe ser un diccionario."]

    if not isinstance(research, dict):
        return ["El catálogo de investigaciones debe ser un diccionario."]

    _validate_buildings(buildings, errors)
    _validate_units(units, buildings, errors)
    _validate_research(research, buildings, errors)

    return errors


def assert_valid_content_catalogs():
    errors = validate_content_catalogs()

    if errors:
        raise ValueError(
            "El catálogo de Kingdram contiene errores:\n- "
            + "\n- ".join(errors)
        )

    return True


def get_content_catalog_summary():
    """
    Devuelve un resumen de los contenidos registrados.
    """

    return {
        "buildings": len(BUILDINGS),
        "units": len(UNITS),
        "research": len(RESEARCH),
    }
