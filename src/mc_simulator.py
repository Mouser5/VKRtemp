import random
import time
from typing import Dict, List, Optional, Tuple, Type
from dataclasses import dataclass
from multiprocessing import Pool

from mc_config import GameConfig
from game import Game


AGENT_REGISTRY: Dict[str, Type] = {}


def _import_agents():
    global AGENT_REGISTRY
    if AGENT_REGISTRY:
        return
    import logging

    logging.getLogger().setLevel(logging.CRITICAL)
    from random_agent import RandomAgent
    from heuristic_agent import HeuristicAgent
    from smart_agent import SmartAgent

    AGENT_REGISTRY = {
        "random": RandomAgent,
        "heuristic": HeuristicAgent,
        "smart": SmartAgent,
    }


@dataclass
class SingleGameResult:
    winner: Optional[int]
    scores: Dict[int, int]
    turns: int
    error: bool = False
    error_msg: str = ""


@dataclass
class SimulationResult:
    agent0_name: str
    agent1_name: str
    n_games: int
    wins: Dict[str, int]
    draw: int
    avg_turns: float
    avg_scores: Dict[str, float]
    std_scores: Dict[str, float]
    error_rate: float
    total_turns: int
    elapsed: float
    games_per_sec: float
    config: GameConfig
    p0_wins: int = 0
    p1_wins: int = 0

    def winrate_pct(self, agent_name: str) -> float:
        return 100.0 * self.wins.get(agent_name, 0) / max(self.n_games, 1)

    def summary(self) -> str:
        sep = "-" * 60
        same_agent = self.agent0_name == self.agent1_name
        n_valid = self.n_games

        if same_agent:
            lines = [
                sep,
                f"SELF-PLAY: {self.agent0_name:<12}  ({self.n_games} игр)",
                sep,
                f"  P0 побед: {self.p0_wins:5d} ({100.0 * self.p0_wins / max(n_valid, 1):5.1f}%)  ср.очек {self.avg_scores.get(self.agent0_name, 0):.2f}",
                f"  P1 побед: {self.p1_wins:5d} ({100.0 * self.p1_wins / max(n_valid, 1):5.1f}%)",
                f"  Ничьих:    {self.draw:5d} ({100.0 * self.draw / max(n_valid, 1):.1f}%)",
                f"  Средняя длина партии: {self.avg_turns:.1f} ходов",
                f"  Ошибок: {self.error_rate * 100:.1f}%",
                f"  Время: {self.elapsed:.1f}с  ({self.games_per_sec:.1f} игр/с)",
                sep,
            ]
        else:
            lines = [
                sep,
                f"{self.agent0_name:>12} vs {self.agent1_name:<12}  ({self.n_games} игр)",
                sep,
                f"  {self.agent0_name:<12}  {self.wins.get(self.agent0_name, 0):5d} побед  ({self.winrate_pct(self.agent0_name):5.1f}%)  ср.очек {self.avg_scores.get(self.agent0_name, 0):.2f}",
                f"  {self.agent1_name:<12}  {self.wins.get(self.agent1_name, 0):5d} побед  ({self.winrate_pct(self.agent1_name):5.1f}%)  ср.очек {self.avg_scores.get(self.agent1_name, 0):.2f}",
                f"  {'Ничья':<12}  {self.draw:5d}  ({100.0 * self.draw / max(n_valid, 1):.1f}%)",
                f"  Средняя длина партии: {self.avg_turns:.1f} ходов",
                f"  Ошибок: {self.error_rate * 100:.1f}%",
                f"  Время: {self.elapsed:.1f}с  ({self.games_per_sec:.1f} игр/с)",
                sep,
            ]
        return "\n".join(lines)


def _run_single_game_worker(args: Tuple) -> SingleGameResult:
    import logging

    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(level=logging.CRITICAL, force=True)

    config, agent0_cls_name, agent1_cls_name, seed = args
    random.seed(seed)

    _import_agents()
    agent0_cls = AGENT_REGISTRY.get(agent0_cls_name)
    agent1_cls = AGENT_REGISTRY.get(agent1_cls_name)
    if not agent0_cls or not agent1_cls:
        return SingleGameResult(
            winner=None,
            scores={0: 0, 1: 0},
            turns=0,
            error=True,
            error_msg=f"Unknown agent: {agent0_cls_name} or {agent1_cls_name}",
        )

    try:
        game = Game(config)
        agents = {0: agent0_cls(0), 1: agent1_cls(1)}
        turn_count = 0

        while not game.is_game_over():
            while not game.is_round_over():
                curr_p = game.state.current_player_id
                try:
                    action = agents[curr_p].choose_action(game)
                    if action is None:
                        game.state.current_player_id = 1 - curr_p
                        continue
                    success, _, _, _ = game.step(action)
                    if not success:
                        game.state.current_player_id = 1 - curr_p
                    turn_count += 1
                except Exception:
                    game.state.current_player_id = 1 - curr_p
                    turn_count += 1
            game.check_round_end()

        total_scores = game.state.total_scores
        if total_scores[0] > total_scores[1]:
            winner = 0
        elif total_scores[1] > total_scores[0]:
            winner = 1
        else:
            winner = None

        return SingleGameResult(
            winner=winner,
            scores=total_scores,
            turns=turn_count,
        )
    except Exception as e:
        return SingleGameResult(
            winner=None,
            scores={0: 0, 1: 0},
            turns=0,
            error=True,
            error_msg=f"{type(e).__name__}: {e}",
        )


def run_simulation(
    config: GameConfig,
    agent0_cls_name: str,
    agent1_cls_name: str,
    n_games: int = 1000,
    n_workers: int = 4,
    verbose: bool = True,
) -> SimulationResult:
    _import_agents()

    agent0_cls = AGENT_REGISTRY.get(agent0_cls_name)
    agent1_cls = AGENT_REGISTRY.get(agent1_cls_name)
    if not agent0_cls or not agent1_cls:
        raise ValueError(f"Unknown agent. Available: {list(AGENT_REGISTRY.keys())}")

    a0_name = agent0_cls.__name__
    a1_name = agent1_cls.__name__

    start_time = time.perf_counter()

    args_list = [
        (
            config,
            agent0_cls_name,
            agent1_cls_name,
            hash(f"game_{i}_{time.time()}") & 0xFFFFFFFF,
        )
        for i in range(n_games)
    ]

    with Pool(processes=min(n_workers, n_games)) as pool:
        results = pool.map(_run_single_game_worker, args_list)

    elapsed = time.perf_counter() - start_time

    wins = {a0_name: 0, a1_name: 0}
    draw = 0
    total_turns = 0
    errors = 0
    scores0, scores1 = [], []
    p0_wins, p1_wins = 0, 0

    for r in results:
        if r.error:
            errors += 1
            continue
        if r.winner == 0:
            wins[a0_name] += 1
            p0_wins += 1
        elif r.winner == 1:
            wins[a1_name] += 1
            p1_wins += 1
        else:
            draw += 1
        total_turns += r.turns
        scores0.append(r.scores[0])
        scores1.append(r.scores[1])

    sum(wins.values()) + draw

    n_valid = n_games - errors
    avg_scores = {
        a0_name: sum(scores0) / max(n_valid, 1),
        a1_name: sum(scores1) / max(n_valid, 1),
    }
    std_scores = _std(scores0), _std(scores1)

    result = SimulationResult(
        agent0_name=a0_name,
        agent1_name=a1_name,
        n_games=n_games,
        wins=wins,
        draw=draw,
        avg_turns=total_turns / max(n_valid, 1),
        avg_scores=avg_scores,
        std_scores={a0_name: std_scores[0], a1_name: std_scores[1]},
        error_rate=errors / max(n_games, 1),
        total_turns=total_turns,
        elapsed=elapsed,
        games_per_sec=n_games / max(elapsed, 0.001),
        config=config,
        p0_wins=p0_wins,
        p1_wins=p1_wins,
    )

    if verbose:
        print(result.summary())

    return result


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return variance**0.5
