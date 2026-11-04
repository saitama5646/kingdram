
BUILDINGS = {
    "sawmill": {
        "name": "Aserradero",
        "icon": "🪵",
        "description": "Produce madera.",
        "resource": "wood",
        "base_cost": {"wood": 150, "stone": 80, "gold": 100},
        "base_time": 60,
        "production": 10
    },
    "quarry": {
        "name": "Cantera",
        "icon": "⛏",
        "description": "Produce piedra.",
        "resource": "stone",
        "base_cost": {"wood": 100, "stone": 150, "gold": 100},
        "base_time": 90,
        "production": 8
    },
    "farm": {
        "name": "Granja",
        "icon": "🌾",
        "description": "Produce alimentos.",
        "resource": "food",
        "base_cost": {"wood": 120, "stone": 60, "gold": 80},
        "base_time": 60,
        "production": 15
    },
    "gold_mine": {
        "name": "Mina de oro",
        "icon": "🪙",
        "description": "Produce oro.",
        "resource": "gold",
        "base_cost": {"wood": 250, "stone": 200, "gold": 150},
        "base_time": 180,
        "production": 5
    },
    "barracks": {
        "name": "Cuartel",
        "icon": "⚔️",
        "description": "Permite entrenar unidades militares.",
        "resource": None,
        "base_cost": {"wood": 300, "stone": 250, "gold": 250},
        "base_time": 240,
        "production": 0
    },
    "market": {
        "name": "Mercado",
        "icon": "🏪",
        "description": "Impulsa la economía del reino.",
        "resource": "gold",
        "base_cost": {"wood": 200, "stone": 150, "gold": 200},
        "base_time": 150,
        "production": 3
    }
}


def get_upgrade_cost(building_type, level):
    building = BUILDINGS[building_type]
    multiplier = 1.65 ** (level - 1)

    return {
        resource: int(amount * multiplier)
        for resource, amount in building["base_cost"].items()
    }


def get_upgrade_time(building_type, level):
    building = BUILDINGS[building_type]

    return int(building["base_time"] * (1.8 ** (level - 1)))


def get_production(building_type, level):
    building = BUILDINGS[building_type]

    if not building["resource"]:
        return 0

    return int(building["production"] * level)
