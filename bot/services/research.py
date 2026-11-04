
from math import ceil


RESEARCH = {
    "agriculture": {
        "name": "Agricultura avanzada",
        "icon": "🌾",
        "branch": "Economía",
        "description": "Mejora los métodos de cultivo y la producción de alimentos.",
        "base_cost": {"wood": 180, "stone": 100, "gold": 120, "food": 80},
        "base_time": 180,
        "requirements": {},
        "building_requirements": {"farm": 2},
        "effects": {
            "food_production": 0.05
        }
    },
    "forestry": {
        "name": "Silvicultura",
        "icon": "🌲",
        "branch": "Economía",
        "description": "Perfecciona la explotación y administración de los bosques.",
        "base_cost": {"wood": 220, "stone": 80, "gold": 120, "food": 60},
        "base_time": 210,
        "requirements": {},
        "building_requirements": {"sawmill": 2},
        "effects": {
            "wood_production": 0.05
        }
    },
    "mining": {
        "name": "Minería avanzada",
        "icon": "⛏️",
        "branch": "Economía",
        "description": "Introduce técnicas más eficientes de extracción mineral.",
        "base_cost": {"wood": 250, "stone": 180, "gold": 160, "food": 80},
        "base_time": 270,
        "requirements": {},
        "building_requirements": {"quarry": 2},
        "effects": {
            "stone_production": 0.05
        }
    },
    "metallurgy": {
        "name": "Metalurgia",
        "icon": "⚒️",
        "branch": "Ingeniería",
        "description": "Desarrolla mejores técnicas para trabajar los metales.",
        "base_cost": {"wood": 350, "stone": 300, "gold": 350, "food": 120},
        "base_time": 420,
        "requirements": {"mining": 1},
        "building_requirements": {"quarry": 3},
        "effects": {
            "military_attack": 0.03
        }
    },
    "architecture": {
        "name": "Arquitectura",
        "icon": "🏛️",
        "branch": "Ingeniería",
        "description": "Permite construir estructuras más resistentes y eficientes.",
        "base_cost": {"wood": 400, "stone": 450, "gold": 300, "food": 120},
        "base_time": 480,
        "requirements": {"forestry": 1},
        "building_requirements": {"sawmill": 3},
        "effects": {
            "construction_speed": 0.04
        }
    },
    "military_doctrine": {
        "name": "Doctrina militar",
        "icon": "⚔️",
        "branch": "Ciencia militar",
        "description": "Estudia la coordinación y disciplina de los ejércitos.",
        "base_cost": {"wood": 300, "stone": 250, "gold": 450, "food": 200},
        "base_time": 420,
        "requirements": {"metallurgy": 1},
        "building_requirements": {"barracks": 2},
        "effects": {
            "military_attack": 0.05,
            "military_defense": 0.02
        }
    },
    "fortification": {
        "name": "Fortificaciones",
        "icon": "🛡️",
        "branch": "Ciencia militar",
        "description": "Mejora la defensa estructural de los dominios.",
        "base_cost": {"wood": 350, "stone": 500, "gold": 350, "food": 150},
        "base_time": 480,
        "requirements": {"architecture": 1},
        "building_requirements": {"barracks": 2},
        "effects": {
            "military_defense": 0.06
        }
    },
    "logistics": {
        "name": "Logística",
        "icon": "🐎",
        "branch": "Logística",
        "description": "Organiza mejor los suministros y el movimiento de tropas.",
        "base_cost": {"wood": 300, "stone": 220, "gold": 400, "food": 250},
        "base_time": 390,
        "requirements": {"agriculture": 1},
        "building_requirements": {"market": 1},
        "effects": {
            "training_speed": 0.05
        }
    },
    "advanced_logistics": {
        "name": "Logística avanzada",
        "icon": "🧭",
        "branch": "Logística",
        "description": "Perfecciona la coordinación de los suministros militares.",
        "base_cost": {"wood": 600, "stone": 450, "gold": 700, "food": 400},
        "base_time": 720,
        "requirements": {"logistics": 2},
        "building_requirements": {"market": 3},
        "effects": {
            "training_speed": 0.08
        }
    },
    "economics": {
        "name": "Administración económica",
        "icon": "📜",
        "branch": "Economía",
        "description": "Mejora la organización de la producción y los recursos.",
        "base_cost": {"wood": 500, "stone": 350, "gold": 650, "food": 250},
        "base_time": 600,
        "requirements": {
            "agriculture": 1,
            "forestry": 1
        },
        "building_requirements": {"market": 2},
        "effects": {
            "wood_production": 0.02,
            "stone_production": 0.02,
            "gold_production": 0.02,
            "food_production": 0.02
        }
    }
}


COST_GROWTH = 1.75
TIME_GROWTH = 1.60


RESOURCE_LABELS = {
    "wood": "Madera",
    "stone": "Piedra",
    "gold": "Oro",
    "food": "Alimentos"
}


def get_research_cost(research_type, target_level):
    research = RESEARCH[research_type]
    multiplier = COST_GROWTH ** (target_level - 1)

    return {
        resource: ceil(amount * multiplier)
        for resource, amount in research["base_cost"].items()
    }


def get_research_time(research_type, target_level):
    research = RESEARCH[research_type]

    return ceil(
        research["base_time"] *
        (TIME_GROWTH ** (target_level - 1))
    )


def get_research_effects(research_levels):
    effects = {}

    for research_type, level in research_levels.items():
        research = RESEARCH.get(research_type)

        if not research:
            continue

        for effect, bonus in research["effects"].items():
            effects[effect] = (
                effects.get(effect, 0)
                + bonus * int(level)
            )

    return effects


def format_cost(cost):
    return "\n".join(
        f"{RESOURCE_LABELS[resource]}: {amount:,}"
        for resource, amount in cost.items()
    )
