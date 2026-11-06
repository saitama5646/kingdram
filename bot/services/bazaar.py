RESOURCES = {
    "wood": {"name": "Madera", "icon": "🪵", "value": 6},
    "stone": {"name": "Piedra", "icon": "🪨", "value": 12},
    "gold": {"name": "Oro", "icon": "🪙", "value": 36},
    "food": {"name": "Alimentos", "icon": "🌾", "value": 7},
}


def calculate_exchange_amount(amount, source, target):
    return (
        int(amount) * RESOURCES[source]["value"]
        // RESOURCES[target]["value"]
    )
