from html import escape

from bot.services.construction import BUILDINGS
from bot.services.military import UNITS
from bot.services.research import RESEARCH


RESOURCE_LABELS = {
    "wood": ("🪵", "Madera"),
    "stone": ("🪨", "Piedra"),
    "gold": ("🪙", "Oro"),
    "food": ("🌾", "Alimentos"),
}

SECTION_LABELS = {
    "army": "⚔️ Ejército",
    "buildings": "🏰 Edificios",
    "research": "🔬 Investigaciones",
}


def format_intelligence(intelligence):
    lines = ["<b>INFORMACIÓN OBTENIDA</b>"]

    for key, value in intelligence.items():
        if key in RESOURCE_LABELS:
            emoji, label = RESOURCE_LABELS[key]
            lines.append(
                f"• {emoji} <b>{label}:</b> "
                f"{int(value):,}"
            )
            continue

        if key == "army":
            lines.append(f"\n<b>{SECTION_LABELS[key]}</b>")

            if not value:
                lines.append("• No hay unidades registradas.")
                continue

            for item in value:
                unit_type = item.get("unit_type", "")
                quantity = int(item.get("quantity", 0))
                unit = UNITS.get(unit_type, {})

                name = unit.get(
                    "name",
                    unit_type.replace("_", " ").title(),
                )
                emoji = unit.get("emoji", "⚔️")

                lines.append(
                    f"• {emoji} <b>{escape(name)}:</b> "
                    f"{quantity:,}"
                )

            continue

        if key == "buildings":
            lines.append(f"\n<b>{SECTION_LABELS[key]}</b>")

            if not value:
                lines.append("• No hay edificios registrados.")
                continue

            for item in value:
                building_type = item.get("building_type", "")
                building = BUILDINGS.get(building_type, {})

                name = building.get(
                    "name",
                    building_type.replace("_", " ").title(),
                )
                emoji = building.get("icon", "🏰")
                level = int(item.get("level", 0))
                damaged = int(item.get("damaged_levels", 0))

                detail = (
                    f"• {emoji} <b>{escape(name)}:</b> "
                    f"Nivel {level}"
                )

                if damaged:
                    detail += f" (Dañados: {damaged})"

                lines.append(detail)

            continue

        if key == "research":
            lines.append(f"\n<b>{SECTION_LABELS[key]}</b>")

            if not value:
                lines.append("• No hay investigaciones registradas.")
                continue

            for item in value:
                research_type = item.get("research_type", "")
                research = RESEARCH.get(research_type, {})

                name = research.get(
                    "name",
                    research_type.replace("_", " ").title(),
                )
                emoji = research.get("icon", "🔬")
                level = int(item.get("level", 0))

                lines.append(
                    f"• {emoji} <b>{escape(name)}:</b> "
                    f"Nivel {level}"
                )

            continue

        if isinstance(value, dict):
            lines.append(f"\n<b>{escape(key.title())}</b>")

            for subkey, subvalue in value.items():
                lines.append(
                    f"• {escape(str(subkey))}: "
                    f"{escape(str(subvalue))}"
                )

        else:
            lines.append(
                f"• <b>{escape(key.title())}:</b> "
                f"{escape(str(value))}"
            )

    return lines
