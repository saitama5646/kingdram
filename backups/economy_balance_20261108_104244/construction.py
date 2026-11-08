BUILDING_COST_GROWTH = 1.70


BUILDINGS = {
    "sawmill": {
        "name": "Aserradero",
        "icon": "🪵",
        "description": "Produce madera para las construcciones y el desarrollo del reino.",
        "resource": "wood",
        "base_cost": {"wood": 150, "stone": 80, "gold": 30},
        "base_time": 60,
        "production": 18,
    },
    "quarry": {
        "name": "Cantera",
        "icon": "⛏",
        "description": "Extrae piedra para las construcciones y fortificaciones.",
        "resource": "stone",
        "base_cost": {"wood": 100, "stone": 150, "gold": 35},
        "base_time": 90,
        "production": 10,
    },
    "farm": {
        "name": "Granja",
        "icon": "🌾",
        "description": "Produce alimentos para abastecer al reino.",
        "resource": "food",
        "base_cost": {"wood": 120, "stone": 60, "gold": 25},
        "base_time": 60,
        "production": 15,
    },
    "gold_mine": {
        "name": "Mina de oro",
        "icon": "🪙",
        "description": "Extrae oro para financiar el desarrollo del reino.",
        "resource": "gold",
        "base_cost": {"wood": 250, "stone": 200, "gold": 50},
        "base_time": 180,
        "production": 2,
    },
    "academy": {
        "name": "Academia",
        "icon": "📚",
        "description": (
            "Centro de conocimiento del reino. "
            "Cada nivel reduce un 8% el tiempo de investigación, "
            "hasta un máximo del 40%. Su mejora requiere "
            "una inversión extraordinaria de recursos."
        ),
        "resource": None,
        "base_cost": {
            "wood": 500,
            "stone": 450,
            "gold": 250,
            "food": 100,
        },
        "base_time": 480,
        "production": 0,
    },
    "barracks": {
        "name": "Cuartel",
        "icon": "⚔️",
        "description": "Permite entrenar unidades militares.",
        "resource": None,
        "base_cost": {"wood": 300, "stone": 250, "gold": 60},
        "base_time": 240,
        "production": 0,
    },
    "market": {
        "name": "Mercado",
        "icon": "🏪",
        "description": "Genera un ingreso modesto de oro con una inversión inicial reducida.",
        "resource": "gold",
        "base_cost": {"wood": 200, "stone": 150, "gold": 55},
        "base_time": 150,
        "production": 1,
    },
    "warehouse": {
        "name": "Almacén",
        "icon": "🏚️",
        "description": "Aumenta la capacidad de almacenamiento de madera y piedra.",
        "resource": None,
        "base_cost": {"wood": 500, "stone": 350, "gold": 80},
        "base_time": 240,
        "production": 0,
    },
    "treasury": {
        "name": "Tesorería",
        "icon": "🏦",
        "description": "Protege y amplía las reservas de oro del reino.",
        "resource": None,
        "base_cost": {"wood": 450, "stone": 250, "gold": 40},
        "base_time": 180,
        "production": 0,
    },
    "granary": {
        "name": "Granero",
        "icon": "🌾",
        "description": "Aumenta la capacidad de almacenamiento de alimentos.",
        "resource": None,
        "base_cost": {"wood": 400, "stone": 250, "gold": 65},
        "base_time": 210,
        "production": 0,
    },
}


def get_upgrade_cost(building_type, level):
    building = BUILDINGS[building_type]
    multiplier = BUILDING_COST_GROWTH ** (level - 1)

    costs = {
        resource: int(amount * 1.15 * multiplier)
        for resource, amount in building["base_cost"].items()
    }

    resource = building["resource"]

    if resource and building["production"] > 0:
        previous = get_production(
            building_type,
            max(0, level - 1),
        )

        current = get_production(
            building_type,
            level,
        )

        additional = max(0, current - previous)

        # Objetivo de amortización: 72 horas.
        target_cost = int(additional * 4320)

        costs[resource] = max(
            costs.get(resource, 0),
            target_cost,
        )

    return costs



def get_upgrade_time(building_type, level):
    building = BUILDINGS[building_type]

    if building_type == "academy":
        # La Academia también exige más tiempo de construcción.
        return int(
            building["base_time"] * 1.50 * (2.00 ** (level - 1))
        )

    return int(
        building["base_time"] * 1.20 * (1.70 ** (level - 1))
    )


PRODUCTION_GROWTH = 1.65


def get_production(building_type, level):
    building = BUILDINGS[building_type]

    if not building["resource"] or level <= 0:
        return 0

    return int(
        building["production"] *
        (PRODUCTION_GROWTH ** (level - 1))
    )
