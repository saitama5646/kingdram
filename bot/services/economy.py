
from decimal import Decimal, ROUND_FLOOR

from bot.services.construction import BUILDINGS, get_production


RESOURCES = ("wood", "stone", "gold", "food")

PRODUCTION_INTERVAL_MINUTES = 1
VASSAL_TRIBUTE_RATE = Decimal("0.20")
MINUTES_PER_DAY = 24 * 60


def get_realm_production(buildings, research_effects=None):
    """
    Calcula la producción real por minuto de un reino.

    Incluye las bonificaciones de investigación para que
    las estimaciones y la producción del trabajador coincidan.
    """

    research_effects = research_effects or {}

    production = {
        resource: 0
        for resource in RESOURCES
    }

    for building in buildings:
        building_type = building["building_type"]
        level = int(building["level"])

        if level <= 0 or building_type not in BUILDINGS:
            continue

        resource = BUILDINGS[building_type]["resource"]

        if resource not in production:
            continue

        production[resource] += get_production(
            building_type,
            level
        )

    for resource in RESOURCES:
        bonus = float(
            research_effects.get(
                f"{resource}_production",
                0,
            )
        )

        multiplier = max(0, 1 + bonus)

        production[resource] = int(
            production[resource] * multiplier
        )

    return production


def get_daily_production(buildings, research_effects=None):
    """
    Calcula la producción estimada de 24 horas,
    incluyendo las bonificaciones de investigación.
    """

    production_per_minute = get_realm_production(
        buildings,
        research_effects,
    )

    return {
        resource: amount * MINUTES_PER_DAY
        for resource, amount in production_per_minute.items()
    }


def calculate_interval_production(
    buildings,
    elapsed_minutes,
    research_effects=None,
):
    """
    Calcula los recursos generados durante un intervalo,
    incluyendo las bonificaciones tecnológicas.
    """

    elapsed_minutes = max(0, int(elapsed_minutes))

    production_per_minute = get_realm_production(
        buildings,
        research_effects,
    )

    return {
        resource: amount * elapsed_minutes
        for resource, amount in production_per_minute.items()
    }


def calculate_vassal_tribute(produced_resources):
    """
    Separa el 20 % de los recursos recién producidos.

    Devuelve dos diccionarios:
    - tribute: recursos que recibe el señor feudal.
    - retained: recursos que conserva el vasallo.

    No utiliza ni modifica las reservas anteriores.
    """

    tribute = {}
    retained = {}

    for resource in RESOURCES:
        produced = max(
            0,
            int(produced_resources.get(resource, 0))
        )

        amount = int(
            (Decimal(produced) * VASSAL_TRIBUTE_RATE)
            .to_integral_value(rounding=ROUND_FLOOR)
        )

        tribute[resource] = amount
        retained[resource] = produced - amount

    return tribute, retained


def calculate_realm_income(
    buildings,
    elapsed_minutes,
    is_vassal=False,
    research_effects=None,
):
    """
    Calcula los ingresos de un reino durante un intervalo.

    Si el reino es vasallo, separa el tributo antes de
    devolver los recursos que conservará.
    """

    produced = calculate_interval_production(
        buildings,
        elapsed_minutes,
        research_effects,
    )

    if not is_vassal:
        return {
            "produced": produced,
            "tribute": {
                resource: 0
                for resource in RESOURCES
            },
            "retained": produced.copy()
        }

    tribute, retained = calculate_vassal_tribute(produced)

    return {
        "produced": produced,
        "tribute": tribute,
        "retained": retained
    }


def format_resources(resources):
    """
    Convierte un diccionario de recursos en texto legible.
    """

    labels = {
        "wood": "Madera",
        "stone": "Piedra",
        "gold": "Oro",
        "food": "Alimentos"
    }

    return "\n".join(
        f"{labels[resource]}: {int(resources.get(resource, 0)):,}"
        for resource in RESOURCES
    )
