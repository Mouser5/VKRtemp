import copy
from typing import Dict, List, Tuple, Any

from mc_config import GameConfig, DeckConfig
from mc_simulator import run_simulation, SimulationResult


def self_play_test(
    config: GameConfig,
    agent_name: str = "random",
    n_games: int = 500,
    n_workers: int = 4,
    verbose: bool = True,
) -> SimulationResult:
    if verbose:
        print(f"\n=== SELF-PLAY: {agent_name} ===")
        print(
            f"Конфиг: колода={sum(asdict_deck(config.deck).values())} карт, "
            f"раундов={config.rules.rounds}, "
            f"рука=[{config.rules.hand_size_first},{config.rules.hand_size_second}]"
        )
    res = run_simulation(config, agent_name, agent_name, n_games, n_workers, verbose)
    return res


def compare_agents(
    config: GameConfig,
    agent_pairs: List[Tuple[str, str]],
    n_games: int = 500,
    n_workers: int = 4,
    verbose: bool = True,
) -> Dict[Tuple[str, str], SimulationResult]:
    results = {}
    for a0, a1 in agent_pairs:
        if verbose:
            print(f"\n=== {a0} vs {a1} ===")
        res = run_simulation(config, a0, a1, n_games, n_workers, verbose)
        results[(a0, a1)] = res
    return results


def asdict_deck(deck: DeckConfig) -> Dict[str, int]:
    return {
        "tunnel_cross": deck.tunnel_cross,
        "tunnel_t": deck.tunnel_t,
        "tunnel_straight": deck.tunnel_straight,
        "tunnel_corner": deck.tunnel_corner,
        "tunnel_deadend": deck.tunnel_deadend,
        "tunnel_bridge": deck.tunnel_bridge,
        "tunnel_double_corner": deck.tunnel_double_corner,
        "tunnel_split_t_up": deck.tunnel_split_t_up,
        "tunnel_split_t_l": deck.tunnel_split_t_l,
        "door_blue": deck.door_blue,
        "door_green": deck.door_green,
        "ladder": deck.ladder,
        "act_boom": deck.act_boom,
        "act_key": deck.act_key,
        "act_map": deck.act_map,
        "brk_LAMP": deck.brk_LAMP,
        "brk_CART": deck.brk_CART,
        "brk_PICKAXE": deck.brk_PICKAXE,
        "rep_LAMP": deck.rep_LAMP,
        "rep_CART": deck.rep_CART,
        "rep_PICKAXE": deck.rep_PICKAXE,
    }


def grid_search(
    base_config: GameConfig,
    param_grid: Dict[str, List[Any]],
    agent_pairs: List[Tuple[str, str]],
    n_games: int = 300,
    n_workers: int = 4,
    verbose: bool = True,
) -> Dict[str, Dict[Tuple[str, str], SimulationResult]]:
    from itertools import product

    keys = list(param_grid.keys())
    all_results: Dict[str, Dict[Tuple[str, str], SimulationResult]] = {}

    for values in product(*param_grid.values()):
        config_label_parts = []
        cfg = copy.deepcopy(base_config)

        for k, v in zip(keys, values):
            config_label_parts.append(f"{k}={v}")
            parts = k.split(".")
            if len(parts) == 2:
                section, field = parts
                section_obj = getattr(cfg, section)
                setattr(section_obj, field, v)
            else:
                setattr(cfg, k, v)

        label = ", ".join(config_label_parts) if config_label_parts else "default"

        if verbose:
            print(f"\n{'=' * 70}")
            print(f"КОНФИГ: {label}")
            print(f"Колода: {sum(asdict_deck(cfg.deck).values())} карт")
            print(
                f"Раундов: {cfg.rules.rounds}, рука: [{cfg.rules.hand_size_first},{cfg.rules.hand_size_second}]"
            )
            print(f"{'=' * 70}")

        pair_results = {}
        for a0, a1 in agent_pairs:
            if verbose:
                print(f"\n  -> {a0} vs {a1}")
            res = run_simulation(cfg, a0, a1, n_games, n_workers, verbose=False)
            pair_results[(a0, a1)] = res

        all_results[label] = pair_results

    return all_results


def format_grid_table(
    grid_results: Dict[str, Dict[Tuple[str, str], SimulationResult]],
    agent_pairs: List[Tuple[str, str]],
) -> str:
    sep = "-" * 80
    lines = [sep]

    header_cols = ["Config"]
    pair_labels = []
    for a0, a1 in agent_pairs:
        if a0 == a1:
            label = f"{a0} self-play"
            header_cols.append("P0 wr%")
            header_cols.append("Draw%")
        else:
            label = f"{a0} vs {a1}"
            header_cols.append(f"{a0} wr%")
            header_cols.append("Draw%")
        pair_labels.append(label)

    header = f"  {'Config':<30}  " + "  ".join(f"{h:>10}" for h in header_cols[1:])
    lines.append(header)
    lines.append(sep)

    for config_label, pair_results in grid_results.items():
        row_cols = [f"  {config_label:<30}"]
        for (a0, a1), res in pair_results.items():
            n_valid = res.n_games
            if a0 == a1:
                p0_wr = 100.0 * res.p0_wins / max(n_valid, 1)
                draw_pct = 100.0 * res.draw / max(n_valid, 1)
                row_cols.append(f"{p0_wr:>8.1f}%  ")
                row_cols.append(f"{draw_pct:>8.1f}%")
            else:
                a0_class_name = res.agent0_name
                wr = res.winrate_pct(a0_class_name)
                draw_pct = 100.0 * res.draw / max(n_valid, 1)
                row_cols.append(f"{wr:>8.1f}%  ")
                row_cols.append(f"{draw_pct:>8.1f}%")
        lines.append("".join(row_cols))

    lines.append(sep)
    return "\n".join(lines)


def run_default_analysis(
    n_games: int = 500,
    n_workers: int = 4,
) -> Dict[str, Any]:
    print("=" * 70)
    print("MONTE CARLO АНАЛИЗ БАЛАНСА ИГРЫ")
    print("Гномы-вредители: Дуэль")
    print("=" * 70)

    base_config = GameConfig()
    results = {}

    # 1. Self-play для каждого агента
    print("\n\n--- 1. SELF-PLAY БАЛАНС ---")
    for agent in ["random", "heuristic", "smart"]:
        res = self_play_test(base_config, agent, n_games, n_workers)
        results[("self", agent)] = res

    # 2. Cross-play
    print("\n\n--- 2. CROSS-PLAY ---")
    pairs = [("smart", "heuristic"), ("smart", "random"), ("heuristic", "random")]
    cross_results = compare_agents(base_config, pairs, n_games, n_workers)
    results.update({("cross", k): v for k, v in cross_results.items()})

    # 3. Grid search по композиции колоды
    print("\n\n--- 3. GRID SEARCH: ВАРИАЦИИ КОЛОДЫ ---")
    grid_params = {
        "deck.tunnel_cross": [6, 10, 14],
        "deck.tunnel_deadend": [2, 4, 8],
    }
    grid_pairs = [("heuristic", "random")]
    grid_res = grid_search(
        base_config, grid_params, grid_pairs, n_games // 2, n_workers
    )

    print("\n\n--- 4. GRID SEARCH: ВАРИАЦИИ СТРУКТУРЫ ИГРЫ ---")
    rules_params = {
        "rules.rounds": [1, 3, 5],
        "rules.hand_size_first": [3, 4, 5],
    }
    rules_grid_res = grid_search(
        base_config, rules_params, grid_pairs, n_games // 2, n_workers
    )

    print("\n\n=== ИТОГОВАЯ ТАБЛИЦА: Вариации колоды ===")
    print(format_grid_table(grid_res, grid_pairs))

    print("\n\n=== ИТОГОВАЯ ТАБЛИЦА: Вариации структуры игры ===")
    print(format_grid_table(rules_grid_res, grid_pairs))

    return {
        "self_play": {
            a: results[("self", a)] for a in ["random", "heuristic", "smart"]
        },
        "cross_play": {str(k): v for k, v in cross_results.items()},
        "grid_deck": grid_res,
        "grid_rules": rules_grid_res,
    }


if __name__ == "__main__":
    import sys

    n = 200 if "--fast" in sys.argv else 500
    run_default_analysis(n_games=n)
