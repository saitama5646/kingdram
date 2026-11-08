import argparse
import json
import random

from bot.services.military import UNITS
from bot.workers.missions import (
    MAX_BATTLE_ROUNDS,
    army_quantity,
    initial_morale,
    update_morale,
    expand_combat_units,
    resolve_battle_round_detailed,
    aggregate_combat_units,
    validate_combat_state,
    validate_survivor_quantities,
)


def validate_roster(troops, side):
    if not isinstance(troops, list) or not troops:
        raise ValueError(
            f"{side}: el ejército no puede estar vacío."
        )

    seen = set()
    normalized = []

    for troop in troops:
        unit_type = troop.get("unit_type")
        quantity = troop.get("quantity")

        if unit_type not in UNITS:
            raise ValueError(
                f"{side}: unidad desconocida: {unit_type!r}."
            )

        if unit_type in seen:
            raise ValueError(
                f"{side}: unidad repetida: {unit_type}."
            )

        seen.add(unit_type)

        try:
            quantity = int(quantity)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(
                f"{side}: cantidad inválida para {unit_type}."
            )

        if quantity <= 0:
            raise ValueError(
                f"{side}: cantidad no positiva para {unit_type}."
            )

        normalized.append({
            "unit_type": unit_type,
            "quantity": quantity,
        })

    return normalized


def simulate_battle(
    attacker_roster,
    defender_roster,
    battles=100,
    seed=42,
    attacker_research=None,
    defender_research=None,
):
    if battles <= 0:
        raise ValueError(
            "La cantidad de simulaciones debe ser positiva."
        )

    attackers_original = validate_roster(
        attacker_roster,
        "Atacante",
    )

    defenders_original = validate_roster(
        defender_roster,
        "Defensor",
    )

    attacker_research = attacker_research or {}
    defender_research = defender_research or {}

    results = {
        "attacker_victory": 0,
        "defender_victory": 0,
        "inconclusive": 0,
        "mutual_destruction": 0,
    }

    total_rounds = 0
    total_attacker_losses = 0
    total_defender_losses = 0
    total_attacker_survivors = 0
    total_defender_survivors = 0

    attacker_initial = army_quantity(
        attackers_original
    )

    defender_initial = army_quantity(
        defenders_original
    )

    for battle_index in range(battles):
        # Cada batalla es reproducible con la misma semilla.
        random.seed(seed + battle_index)

        attackers = expand_combat_units(
            attackers_original,
            attacker_research,
        )

        defenders = expand_combat_units(
            defenders_original,
            defender_research,
        )

        attacker_morale = initial_morale(
            attacker_initial,
            defender_initial,
        )

        defender_morale = initial_morale(
            defender_initial,
            attacker_initial,
        )

        round_number = 0

        while (
            attackers
            and defenders
            and round_number < MAX_BATTLE_ROUNDS
        ):
            round_number += 1

            attacker_before = sum(
                int(unit.get("quantity", 1))
                for unit in attackers
            )

            defender_before = sum(
                int(unit.get("quantity", 1))
                for unit in defenders
            )

            (
                attackers,
                defenders,
                attacker_damage,
                defender_damage,
                damage_details,
            ) = resolve_battle_round_detailed(
                attackers,
                defenders,
                attacker_morale,
                defender_morale,
            )

            validate_combat_state(
                attackers,
                attackers_original,
                "Atacante",
            )

            validate_combat_state(
                defenders,
                defenders_original,
                "Defensor",
            )

            attacker_after = sum(
                int(unit.get("quantity", 1))
                for unit in attackers
            )

            defender_after = sum(
                int(unit.get("quantity", 1))
                for unit in defenders
            )

            attacker_losses = (
                attacker_before - attacker_after
            )

            defender_losses = (
                defender_before - defender_after
            )

            attacker_morale = update_morale(
                attacker_morale,
                attacker_losses,
                attacker_before,
                defender_losses,
                defender_before,
            )

            defender_morale = update_morale(
                defender_morale,
                defender_losses,
                defender_before,
                attacker_losses,
                attacker_before,
            )

        attackers = aggregate_combat_units(attackers)
        defenders = aggregate_combat_units(defenders)

        attacker_losses_total = (
            validate_survivor_quantities(
                attackers_original,
                attackers,
                "Atacante",
            )
        )

        defender_losses_total = (
            validate_survivor_quantities(
                defenders_original,
                defenders,
                "Defensor",
            )
        )

        attacker_remaining = army_quantity(attackers)
        defender_remaining = army_quantity(defenders)

        if attacker_remaining > 0 and defender_remaining == 0:
            outcome = "attacker_victory"

        elif defender_remaining > 0 and attacker_remaining == 0:
            outcome = "defender_victory"

        elif attacker_remaining > 0 and defender_remaining > 0:
            outcome = "inconclusive"

        else:
            outcome = "mutual_destruction"

        results[outcome] += 1

        total_rounds += round_number

        total_attacker_losses += attacker_losses_total
        total_defender_losses += defender_losses_total

        total_attacker_survivors += attacker_remaining
        total_defender_survivors += defender_remaining

    return {
        "battles": battles,
        "seed": seed,
        "initial_armies": {
            "attacker": attacker_initial,
            "defender": defender_initial,
        },
        "outcomes": {
            key: {
                "count": count,
                "percentage": round(
                    count * 100 / battles,
                    2,
                ),
            }
            for key, count in results.items()
        },
        "averages": {
            "rounds": round(
                total_rounds / battles,
                2,
            ),
            "attacker_losses": round(
                total_attacker_losses / battles,
                2,
            ),
            "defender_losses": round(
                total_defender_losses / battles,
                2,
            ),
            "attacker_survivors": round(
                total_attacker_survivors / battles,
                2,
            ),
            "defender_survivors": round(
                total_defender_survivors / battles,
                2,
            ),
            "attacker_loss_percentage": round(
                total_attacker_losses
                * 100
                / (attacker_initial * battles),
                2,
            ),
            "defender_loss_percentage": round(
                total_defender_losses
                * 100
                / (defender_initial * battles),
                2,
            ),
        },
    }


def parse_roster(value):
    troops = []

    for entry in value.split(","):
        if "=" not in entry:
            raise argparse.ArgumentTypeError(
                "Usa el formato unidad=cantidad."
            )

        unit_type, quantity = entry.split("=", 1)

        try:
            quantity = int(quantity)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Cantidad inválida: {quantity}"
            )

        troops.append({
            "unit_type": unit_type.strip(),
            "quantity": quantity,
        })

    return troops


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Simulador estadístico de combate de Kingdram."
        )
    )

    parser.add_argument(
        "--attacker",
        required=True,
        type=parse_roster,
        help="Ejemplo: spearman=100,archer=50",
    )

    parser.add_argument(
        "--defender",
        required=True,
        type=parse_roster,
        help="Ejemplo: spearman=80,royal_guard=10",
    )

    parser.add_argument(
        "--battles",
        type=int,
        default=100,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    args = parser.parse_args()

    result = simulate_battle(
        args.attacker,
        args.defender,
        battles=args.battles,
        seed=args.seed,
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
