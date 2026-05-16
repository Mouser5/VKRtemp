from typing import Dict, Any, Optional, List
import uuid

from game import Game
from actions import (
    AgentAction,
    ActionBuild,
    ActionPlayBoardUtility,
    ActionPlayPlayerUtility,
    ActionDiscard,
)
from cards import EquipmentType
from web.game_runner import action_to_dsl, GameLog, _format_action
from web.redis_manager import GameRedisManager, game_redis
from web.logger import (
    logger,
    log_game_start,
    log_game_end,
    log_game_error,
)


class RedisGameBridge:
    def __init__(
            self,
            docker_manager=None,
            redis_client: GameRedisManager = None,
            game_engine_factory=None,
            redis_mgr: GameRedisManager = None,
            docker_mgr=None,
    ):
        from web.docker_manager import docker_manager as default_docker_manager
        from game import Game

        self.redis = redis_client or redis_mgr or game_redis
        self.docker = docker_mgr or docker_manager or default_docker_manager
        self.game_engine_factory = game_engine_factory or (lambda _config: Game())

        # Теперь храним словарь ID контейнеров {player_id: container_id}
        self._container_ids: Dict[int, str] = {}

    def run_with_container(
        self,
        container_player_id: int,
        bot_code: str,
        opponent_class: type = None,
        opponent_name: str = "Opponent",
        bot_name: str = "Bot",
        timeout: float = 30.0,
        game: Game = None,
        opponent_agent: Any = None,
    ) -> Dict[str, Any]:
        game_id = str(uuid.uuid4())[:8]
        if game is None:
            game = Game()

        log_game_start(game_id, bot_name, opponent_name)

        container_result = self.docker.start_game_container_redis(
            bot_code=bot_code,
            user_id=0,
            game_id=game_id,
        )

        if "error" in container_result:
            error_msg = f"Failed to start container: {container_result['error']}"
            log_game_error(game_id, error_msg)
            return {
                "winner": None,
                "scores": {0: 0, 1: 0},
                "turns": 0,
                "error": error_msg,
                "dsl_log": "",
                "logs": [],
            }

        container_id = container_result["container_id"]
        self._container_ids[container_player_id] = container_id

        self.redis.wait_for_listener_ready(game_id, timeout=5.0)

        try:
            result = self._run_game_loop(
                game=game,
                game_id=game_id,
                container_player_ids=[container_player_id],
                opponent_class=opponent_class,
                opponent_agent=opponent_agent,
                timeout=timeout,
                bot_codes={container_player_id: bot_code},
                user_id=0,
            )
            return result
        except Exception as e:
            log_game_error(game_id, str(e))
            return {
                "winner": None,
                "scores": game.state.total_scores,
                "turns": game.state.turn_number,
                "error": str(e),
                "dsl_log": "",
                "logs": [],
            }
        finally:
            try:
                self.docker.stop_game_container(container_id)
            except Exception:
                logger.exception(f"Failed to stop container {container_id}")
            try:
                self.redis.delete_game(game_id)
            except Exception:
                logger.exception(f"Failed to delete Redis game {game_id}")

    def run_game_two_containers(
            self,
            bot0_code: str,
            bot1_code: str,
            bot0_name: str,
            bot1_name: str,
            game_config: Optional[Dict[str, Any]] = None,
            action_timeout_sec: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Запуск матча между двумя изолированными ботами с использованием единого цикла.
        """
        game_cfg = game_config or {}
        game_id = str(uuid.uuid4())[:8]
        game = self.game_engine_factory(game_cfg)

        self.redis.client.set(f"game:{game_id}:p0:code", bot0_code)
        self.redis.client.set(f"game:{game_id}:p1:code", bot1_code)

        c0 = self.docker.start_player_container_redis(game_id=game_id, player_id=0)
        if "error" in c0:
            return self._error_result_two_containers(game_id, f"container_start_error_p0: {c0['error']}")

        c1 = self.docker.start_player_container_redis(game_id=game_id, player_id=1)
        if "error" in c1:
            self.docker.stop_and_remove_container(c0["container_id"])
            return self._error_result_two_containers(game_id, f"container_start_error_p1: {c1['error']}")

        self._container_ids[0] = c0["container_id"]
        self._container_ids[1] = c1["container_id"]

        ready0 = self.redis.wait_for_listener_ready(game_id, timeout=5.0, player_id=0)
        ready1 = self.redis.wait_for_listener_ready(game_id, timeout=5.0, player_id=1)

        if not (ready0 and ready1):
            self.docker.stop_and_remove_container(c0["container_id"])
            self.docker.stop_and_remove_container(c1["container_id"])
            self.redis.delete_game(game_id)
            return self._error_result_two_containers(game_id, "listener_ready_timeout")
        log_game_start(game_id, bot0_name, bot1_name)
        try:
            result = self._run_game_loop(
                game=game,
                game_id=game_id,
                container_player_ids=[0, 1],
                timeout=action_timeout_sec,
                bot_codes={0: bot0_code, 1: bot1_code},
                user_id=0,
            )
            result["game_id"] = game_id
            return result
        finally:
            import threading

            def background_cleanup(c0_id, c1_id, g_id):
                try:
                    self.docker.stop_and_remove_container(c0_id)
                    self.docker.stop_and_remove_container(c1_id)
                    self.redis.delete_game(g_id)
                except Exception as e:
                    logger.error(f"Фоновая очистка не удалась: {e}")

            cleanup_thread = threading.Thread(
                target=background_cleanup,
                args=(c0["container_id"], c1["container_id"], game_id)
            )
            cleanup_thread.start()

    def _error_result_two_containers(self, game_id: str, reason: str) -> Dict[str, Any]:
        return {
            "game_id": game_id,
            "winner": None,
            "reason": reason,
            "turns": 0,
            "scores": {0: 0, 1: 0},
            "dsl_log": "",
            "logs": [],
        }

    @staticmethod
    def _winner_from_scores(scores: Dict[int, int]) -> Optional[int]:
        p0 = scores.get(0, 0)
        p1 = scores.get(1, 0)
        if p0 > p1:
            return 0
        if p1 > p0:
            return 1
        return None

    def _run_game_loop(
            self,
            game: Game,
            game_id: str,
            container_player_ids: List[int],
            opponent_class: type = None,
            opponent_agent: Any = None,
            timeout: float = 30.0,
            bot_codes: Dict[int, str] = None,
            user_id: int = 0,
    ) -> Dict[str, Any]:
        bot_codes = bot_codes or {}

        # Определяем локального оппонента, если хотя бы один игрок НЕ в контейнере
        local_player_id = next((p for p in [0, 1] if p not in container_player_ids), None)
        opponent = None
        if local_player_id is not None:
            if opponent_agent is not None:
                opponent = opponent_agent
            elif opponent_class is not None:
                opponent = opponent_class(local_player_id)

        turn_count = 0
        errors: List[str] = []
        dsl_lines: List[str] = []
        logs: List[GameLog] = []

        while not game.is_game_over():
            while not game.is_round_over():
                curr_p = game.state.current_player_id
                turn_count += 1

                if curr_p in container_player_ids:
                    code = bot_codes.get(curr_p, "")
                    success = self._play_container_turn_with_retry(
                        game,
                        game_id,
                        curr_p,
                        turn_count,
                        timeout,
                        dsl_lines,
                        logs,
                        code,
                        user_id,
                        is_two_containers=(len(container_player_ids) == 2)
                    )
                    if not success:
                        errors.append(f"Container turn {turn_count} failed")
                        game.state.current_player_id = 1 - curr_p
                        continue
                else:
                    self._play_local_turn(
                        game, opponent, curr_p, turn_count, errors, dsl_lines, logs
                    )

            game.check_round_end()

        total_scores = game.state.total_scores
        print(f"total_score {total_scores}")
        winner = self._winner_from_scores(total_scores)
        print(f"winner {winner}")

        log_game_end(game_id, str(winner), total_scores, turn_count)

        return {
            "winner": winner,
            "scores": total_scores,
            "turns": turn_count,
            "errors": errors,
            "dsl_log": "\n".join(dsl_lines),
            "logs": [
                {
                    "player_id": log.player_id,
                    "turn_number": log.turn_number,
                    "round_number": log.round_number,
                    "action_type": log.action_type,
                    "action_description": log.action_description,
                    "message": log.message,
                    "action_dsl": log.action_dsl,
                    "gold_found": log.gold_found,
                }
                for log in logs
            ],
        }

    def _play_container_turn(
        self,
        game: Game,
        game_id: str,
        player_id: int,
        turn: int,
        timeout: float,
        dsl_lines: List[str],
        logs: List[GameLog],
    ) -> bool:
        state_dict = self._game_to_json(game, player_id)

        if not self.redis.store_state(game_id, state_dict):
            logger.error(f"Failed to store state for turn {turn}")
            dsl_lines.append(f"P{player_id}\n0\n\n\n0")
            logs.append(
                GameLog(
                    turn_number=turn,
                    round_number=game.state.round_number,
                    player_id=player_id,
                    action_type="error",
                    action_description="Ошибка сохранения состояния",
                    message="Failed to store state",
                )
            )
            game.state.current_player_id = 1 - player_id
            return False

        self.redis.clear_turn_state(game_id, player_id)
        self.redis.signal_turn(game_id, player_id, turn)

        action_data = self.redis.wait_for_action(game_id, player_id, timeout)

        if action_data is None:
            logger.warning(f"Container timeout on turn {turn}")
            dsl_lines.append(f"P{player_id}\n0\n\n\n0")
            logs.append(
                GameLog(
                    turn_number=turn,
                    round_number=game.state.round_number,
                    player_id=player_id,
                    action_type="timeout",
                    action_description="Таймаут контейнера",
                )
            )
            game.state.current_player_id = 1 - player_id
            return False

        pydantic_action = self._json_to_action(action_data)
        if pydantic_action is None:
            logger.debug(f"Container has no legal actions on turn {turn}")
            dsl_lines.append(f"P{player_id}\n0\n\n\n0")
            logs.append(
                GameLog(
                    turn_number=turn,
                    round_number=game.state.round_number,
                    player_id=player_id,
                    action_type="skip",
                    action_description="Нет легальных ходов",
                )
            )
            game.state.current_player_id = 1 - player_id
            return True

        success, msg, rev_gold, _ = game.step(pydantic_action)
        dsl_lines.append(action_to_dsl(pydantic_action, player_id))
        logs.append(
            GameLog(
                turn_number=turn,
                round_number=game.state.round_number,
                player_id=player_id,
                action_type=pydantic_action.type,
                action_description=_format_action(pydantic_action, game),
                message=msg,
                gold_found=rev_gold,
                action_dsl=dsl_lines[-1],
            )
        )
        if not success:
            logger.warning(f"Container action rejected turn {turn}: {msg}")
            game.state.current_player_id = 1 - player_id

        return True

    def _play_container_turn_with_retry(
        self,
        game: Game,
        game_id: str,
        player_id: int,
        turn: int,
        timeout: float,
        dsl_lines: List[str],
        logs: List[GameLog],
        bot_code: str,
        user_id: int,
        max_retries: int = 3,
        is_two_containers: bool = False
    ) -> bool:
        for attempt in range(max_retries):
            dsl_len = len(dsl_lines)
            logs_len = len(logs)
            old_player = game.state.current_player_id

            success = self._play_container_turn(
                game, game_id, player_id, turn, timeout, dsl_lines, logs
            )
            if success:
                return True

            dsl_lines[dsl_len:] = []
            logs[logs_len:] = []
            game.state.current_player_id = old_player

            if attempt == max_retries - 1:
                break

            logger.warning(
                f"Container turn {turn} attempt {attempt + 1}/{max_retries}, restarting..."
            )

            cid = self._container_ids.get(player_id)
            if cid:
                if is_two_containers:
                    self.docker.stop_and_remove_container(cid)
                else:
                    self.docker.stop_game_container(cid)

            # Логика перезапуска зависит от режима (турнир или одиночная игра)
            if is_two_containers:
                self.redis.client.set(f"game:{game_id}:p{player_id}:code", bot_code)
                result = self.docker.start_player_container_redis(game_id=game_id, player_id=player_id)
                ready_key_suffix = f"player:{player_id}:listener_ready"
                player_id_arg = player_id
            else:
                result = self.docker.start_game_container_redis(bot_code=bot_code, user_id=user_id, game_id=game_id)
                ready_key_suffix = "listener_ready"
                player_id_arg = None

            if "error" in result:
                logger.error(f"Container restart failed: {result['error']}")
                continue

            self._container_ids[player_id] = result["container_id"]
            self.redis.client.delete(f"game:{game_id}:{ready_key_suffix}")
            self.redis.wait_for_listener_ready(game_id, timeout=5.0, player_id=player_id_arg)

        return False

    def _play_local_turn(
        self,
        game: Game,
        opponent,
        player_id: int,
        turn: int,
        errors: List[str],
        dsl_lines: List[str],
        logs: List[GameLog],
    ) -> bool:
        try:
            action = opponent.choose_action(game)
            if action is None:
                dsl_lines.append(f"P{player_id}\n0\n\n\n0")
                logs.append(
                    GameLog(
                        turn_number=turn,
                        round_number=game.state.round_number,
                        player_id=player_id,
                        action_type="skip",
                        action_description="Нет легальных ходов",
                    )
                )
                game.state.current_player_id = 1 - player_id
                return True

            success, msg, rev_gold, _ = game.step(action)
            dsl_lines.append(action_to_dsl(action, player_id))
            logs.append(
                GameLog(
                    turn_number=turn,
                    round_number=game.state.round_number,
                    player_id=player_id,
                    action_type=action.type,
                    action_description=_format_action(action, game),
                    message=msg,
                    gold_found=rev_gold,
                    action_dsl=dsl_lines[-1],
                )
            )
            if not success:
                errors.append(f"Opponent action rejected: {msg}")
                game.state.current_player_id = 1 - player_id
            return True
        except Exception as e:
            errors.append(f"Opponent error: {e}")
            dsl_lines.append(f"P{player_id}\n0\n\n\n0")
            logs.append(
                GameLog(
                    turn_number=turn,
                    round_number=game.state.round_number,
                    player_id=player_id,
                    action_type="error",
                    action_description=f"Ошибка оппонента: {e}",
                )
            )
            game.state.current_player_id = 1 - player_id
            return True

    def _game_to_json(self, game: Game, player_id: int) -> Dict[str, Any]:
        legal_actions = game.get_legal_actions()
        actions_json = []

        for action in legal_actions:
            action_dict = {"type": action.type}
            if isinstance(action, ActionBuild):
                action_dict.update(
                    {
                        "template_id": action.template_id,
                        "x": action.x,
                        "y": action.y,
                        "is_rotated_180": action.is_rotated_180,
                    }
                )
            elif isinstance(action, ActionPlayBoardUtility):
                action_dict.update(
                    {
                        "template_id": action.template_id,
                        "x": action.x,
                        "y": action.y,
                    }
                )
            elif isinstance(action, ActionPlayPlayerUtility):
                action_dict.update(
                    {
                        "template_id": action.template_id,
                        "target_player_id": action.target_player_id,
                    }
                )
            elif isinstance(action, ActionDiscard):
                action_dict.update(
                    {
                        "templates": action.templates,
                        "repair_equipment": (
                            action.repair_equipment.value
                            if action.repair_equipment
                            else None
                        ),
                    }
                )
            actions_json.append(action_dict)

        player_state = game.state.players[player_id]
        obs = game.get_observation(player_id)

        return {
            "game_id": "",
            "player_id": player_id,
            "round": game.state.round_number,
            "turn": game.state.turn_number,
            "current_player": game.state.current_player_id,
            "scores": game.state.total_scores,
            "hand": player_state.hand,
            "broken_equipments": [e.value for e in player_state.broken_equipments],
            "known_secrets": list(player_state.known_secrets),
            "board": {
                k: {
                    "template_id": v.template_id,
                    "is_revealed": v.is_revealed,
                    "owner_id": v.owner_id,
                }
                for k, v in obs.board.items()
            },
            "players_broken": {
                p_id: [e.value for e in p_state.broken_equipments]
                for p_id, p_state in obs.players.items()
            },
            "legal_actions": actions_json,
            "is_game_over": game.is_game_over(),
        }

    def _json_to_action(self, action_dict: Dict[str, Any]) -> Optional[AgentAction]:
        type_name = action_dict.get("type", "")

        if type_name in ("None", "none"):
            return None

        try:
            if type_name in ("ActionBuild", "build"):
                return ActionBuild(
                    template_id=int(action_dict["template_id"]),
                    x=action_dict["x"],
                    y=action_dict["y"],
                    is_rotated_180=action_dict.get("is_rotated_180", False),
                )
            elif type_name in (
                "ActionPlayBoardUtility",
                "play_board_utility",
                "play_board",
            ):
                return ActionPlayBoardUtility(
                    template_id=int(action_dict["template_id"]),
                    x=action_dict["x"],
                    y=action_dict["y"],
                )
            elif type_name in (
                "ActionPlayPlayerUtility",
                "play_player_utility",
                "play_player",
            ):
                return ActionPlayPlayerUtility(
                    template_id=int(action_dict["template_id"]),
                    target_player_id=action_dict["target_player_id"],
                )
            elif type_name in ("ActionDiscard", "discard"):
                repair_eq = None
                if action_dict.get("repair_equipment"):
                    repair_eq = EquipmentType(action_dict["repair_equipment"])
                templates = action_dict.get("templates", [])
                return ActionDiscard(
                    templates=[int(t) for t in templates],
                    repair_equipment=repair_eq,
                )
            else:
                logger.warning(f"Unknown action type: {type_name}")
                return None
        except (ValueError, KeyError, TypeError) as e:
            logger.error(f"Failed to convert action {action_dict}: {e}")
            return None


redis_game_bridge = RedisGameBridge()