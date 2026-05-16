import sys
from pathlib import Path
from typing import Dict, Any, Optional
import uuid

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
import requests  # noqa: E402
import uvicorn  # noqa: E402

sys.path.insert(0, str(src_path))

from game import Game  # noqa: E402
from actions import (  # noqa: E402
    AgentAction,
    ActionBuild,
    ActionPlayBoardUtility,
    ActionPlayPlayerUtility,
    ActionDiscard,
)
from dsl_parser import (  # noqa: E402
    encode_game_state_dsl,
    decode_player_action_dsl,
    DSLActionValidator,
)


app = FastAPI(
    title="Гномы-вредители: API",
    description="""
# API для игры "Гномы-вредители: Дуэль"

## Описание
REST API для проведения игр между ботами. Поддерживает:
- Создание новых игр
- Получение состояния игры в DSL формате
- Выполнение ходов в DSL формате
- Управление ботами через webhook

## DSL Формат
### Состояние от системы (пример):
```
-1;0 1 0
1;0 2 0
p0 0
p1 0
4
3;4;5;6
```
Где:
- `-1;0 1 0` - координата x;y, ID карты, is_rotated
- `p0 0` - у игрока p0 нет сломаных инструментов
- `p1 0` - у игрока p1 нет сломаных инструментов
- `4` - количество карт на руке
- `3;4;5;6` - ID карт на руке

### Ход игрока (примеры):
- Пас: `0`
- Построить: `1\n24\n-5;8\n1`
- Починить: `2\n3\n47`
- Экстренная починка: `2\n3\n47;48`
- Сбросить 1 карту: `3\n47`
- Сбросить 2 карты: `3\n47;48`
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ACTIVE_GAMES: Dict[str, Dict[str, Any]] = {}


class GameStartRequest(BaseModel):
    bot1_code: str = Field(..., description="Python код первого бота")
    bot2_code: str = Field(..., description="Python код второго бота")
    bot1_url: Optional[str] = Field(None, description="URL webhook первого бота")
    bot2_url: Optional[str] = Field(None, description="URL webhook второго бота")


class ActionRequest(BaseModel):
    player_id: int = Field(..., description="ID игрока (0 или 1)")
    action: str = Field(..., description="Ход в DSL формате")


def game_to_json(game: Game, player_id: int) -> Dict[str, Any]:
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


def game_to_dsl(game: Game, player_id: int) -> str:
    return encode_game_state_dsl(game, player_id)


def action_from_dsl(dsl_string: str, game: Game, player_id: int) -> AgentAction:
    game_state = game_to_json(game, player_id)
    card_id_to_template = game.state.players[player_id].card_id_to_template.copy()
    game_state["card_id_to_template"] = card_id_to_template
    action = decode_player_action_dsl(dsl_string, game_state, player_id)
    return action


def notify_bot(url: str, game_id: str, game_state: str, is_dsl: bool = True):
    try:
        if is_dsl:
            resp = requests.post(
                f"{url}/choose", json={"game_state_dsl": game_state}, timeout=30
            )
        else:
            resp = requests.post(
                f"{url}/choose", json={"game_state": game_state}, timeout=30
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Failed to notify bot: {e}")
    return None


@app.get("/health")
def health():
    return {"status": "ok", "games": len(ACTIVE_GAMES)}


@app.post(
    "/games",
    summary="Создать новую игру",
    description="Запускает новую игру между двумя ботами",
)
def start_game(req: GameStartRequest):
    game_id = str(uuid.uuid4())

    game = Game()
    game_id_holder = {"id": game_id}
    game.state.metadata = game_id_holder

    if req.bot1_url:
        try:
            requests.post(
                f"{req.bot1_url}/init",
                json={"code": req.bot1_code, "player_id": 0},
                timeout=10,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to init bot1: {e}")

    if req.bot2_url:
        try:
            requests.post(
                f"{req.bot2_url}/init",
                json={"code": req.bot2_code, "player_id": 1},
                timeout=10,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to init bot2: {e}")

    ACTIVE_GAMES[game_id] = {
        "game": game,
        "bot1_code": req.bot1_code,
        "bot2_code": req.bot2_code,
        "bot1_url": req.bot1_url,
        "bot2_url": req.bot2_url,
    }

    dsl_state = game_to_dsl(game, game.state.current_player_id)
    json_state = game_to_json(game, game.state.current_player_id)

    state = {
        "game_id": game_id,
        "dsl": dsl_state,
        "json": json_state,
    }

    if game.state.current_player_id == 0 and req.bot1_url:
        notify_bot(req.bot1_url, game_id, dsl_state, is_dsl=True)
    elif game.state.current_player_id == 1 and req.bot2_url:
        notify_bot(req.bot2_url, game_id, dsl_state, is_dsl=True)

    return state


@app.get(
    "/games/{game_id}",
    summary="Получить состояние игры",
    description="Возвращает состояние игры в DSL и JSON форматах",
)
def get_game(game_id: str):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found")

    game = ACTIVE_GAMES[game_id]["game"]
    player_id = game.state.current_player_id

    dsl_state = game_to_dsl(game, player_id)
    json_state = game_to_json(game, player_id)

    return {
        "game_id": game_id,
        "dsl": dsl_state,
        "json": json_state,
    }


@app.get(
    "/games/{game_id}/dsl",
    summary="Получить состояние в DSL формате",
    description="Возвращает состояние игры в DSL формате для текущего игрока",
)
def get_game_dsl(game_id: str):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found")

    game = ACTIVE_GAMES[game_id]["game"]
    player_id = game.state.current_player_id

    return {
        "game_id": game_id,
        "player_id": player_id,
        "dsl": game_to_dsl(game, player_id),
    }


@app.get(
    "/games/{game_id}/json",
    summary="Получить состояние в JSON формате",
    description="Возвращает состояние игры в JSON формате для текущего игрока",
)
def get_game_json(game_id: str):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found")

    game = ACTIVE_GAMES[game_id]["game"]
    player_id = game.state.current_player_id

    return {
        "game_id": game_id,
        "player_id": player_id,
        "state": game_to_json(game, player_id),
    }


@app.get(
    "/games/{game_id}/state",
    summary="Получить полное состояние",
    description="Возвращает состояние игры для обоих игроков",
)
def get_game_state(game_id: str):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found")

    game = ACTIVE_GAMES[game_id]["game"]

    states = {}
    for pid in [0, 1]:
        states[pid] = {
            "dsl": game_to_dsl(game, pid),
            "json": game_to_json(game, pid),
        }

    return {
        "game_id": game_id,
        "current_player": game.state.current_player_id,
        "states": states,
    }


@app.get(
    "/games/{game_id}/legal-actions",
    summary="Получить легальные ходы",
    description="Возвращает список возможных ходов для текущего игрока",
)
def get_legal_actions(game_id: str):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found")

    game = ACTIVE_GAMES[game_id]["game"]
    player_id = game.state.current_player_id

    return {
        "game_id": game_id,
        "player_id": player_id,
        "legal_actions": game_to_json(game, player_id)["legal_actions"],
    }


@app.post(
    "/games/{game_id}/action",
    summary="Совершить ход",
    description="Выполняет ход игрока в DSL формате",
)
def submit_action(game_id: str, req: ActionRequest):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found")

    game_data = ACTIVE_GAMES[game_id]
    game = game_data["game"]

    if req.player_id != game.state.current_player_id:
        raise HTTPException(status_code=400, detail="Not your turn")

    try:
        action = action_from_dsl(req.action, game, req.player_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid action: {e}")

    game_state_json = game_to_json(game, req.player_id)
    validator = DSLActionValidator(game_state_json, req.player_id)
    is_valid, error_msg = validator.is_action_valid(action)

    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    success, msg, gold, _ = game.step(action)

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    game.state.move_log_dsl.append(f"p{req.player_id}: {req.action}")

    state_dsl = game_to_dsl(game, game.state.current_player_id)
    state_json = game_to_json(game, game.state.current_player_id)

    state = {
        "game_id": game_id,
        "dsl": state_dsl,
        "json": state_json,
        "last_action": {"success": True, "message": msg, "gold_found": gold},
    }

    if game.is_game_over():
        game.state.move_log_dsl.append(
            f"SYSTEM: game_over scores={game.state.total_scores}"
        )

        dsl_log = "\n".join(game.state.move_log_dsl)
        winner = (
            0
            if game.state.total_scores[0] > game.state.total_scores[1]
            else (
                1 if game.state.total_scores[1] > game.state.total_scores[0] else None
            )
        )

        try:
            from models import GameLog, SessionLocal, init_db

            init_db()
            db = SessionLocal()
            db_game_log = GameLog(
                game_id=game_id,
                bot1_code=game_data.get("bot1_code"),
                bot2_code=game_data.get("bot2_code"),
                dsl_log=dsl_log,
                scores_p0=game.state.total_scores[0],
                scores_p1=game.state.total_scores[1],
                winner=winner,
                turns=game.state.turn_number,
            )
            db.add(db_game_log)
            db.commit()
            db.close()
        except Exception as e:
            print(f"Failed to save game log: {e}")

        return {
            "game_over": True,
            "winner": winner,
            "scores": game.state.total_scores,
            "dsl_log": dsl_log,
            "state": state,
        }

    next_player = game.state.current_player_id
    if next_player == 0 and game_data["bot1_url"]:
        notify_bot(game_data["bot1_url"], game_id, state_dsl, is_dsl=True)
    elif next_player == 1 and game_data["bot2_url"]:
        notify_bot(game_data["bot2_url"], game_id, state_dsl, is_dsl=True)

    return state


@app.post(
    "/games/{game_id}/action/json",
    summary="Совершить ход в JSON формате",
    description="Выполняет ход игрока в JSON формате (старый формат)",
)
def submit_action_json(game_id: str, req: ActionRequest):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found")

    game_data = ACTIVE_GAMES[game_id]
    game = game_data["game"]

    if req.player_id != game.state.current_player_id:
        raise HTTPException(status_code=400, detail="Not your turn")

    action_dict = req.action if isinstance(req.action, dict) else {"type": req.action}
    action_type = action_dict.get("type", "")

    if action_type == "build":
        action = ActionBuild(
            template_id=action_dict["template_id"],
            x=action_dict["x"],
            y=action_dict["y"],
            is_rotated_180=action_dict.get("is_rotated_180", False),
        )
    elif action_type == "play_board_utility":
        action = ActionPlayBoardUtility(
            template_id=action_dict["template_id"],
            x=action_dict["x"],
            y=action_dict["y"],
        )
    elif action_type == "play_player_utility":
        from cards import EquipmentType

        action = ActionPlayPlayerUtility(
            template_id=action_dict["template_id"],
            target_player_id=action_dict["target_player_id"],
        )
    elif action_type == "discard":
        from cards import EquipmentType

        repair_eq = None
        if action_dict.get("repair_equipment"):
            repair_eq = EquipmentType(action_dict["repair_equipment"])
        action = ActionDiscard(
            templates=action_dict["templates"],
            repair_equipment=repair_eq,
        )
    else:
        raise HTTPException(
            status_code=400, detail=f"Unknown action type: {action_type}"
        )

    success, msg, gold, _ = game.step(action)

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    game.state.move_log_dsl.append(f"p{req.player_id}: {action_dict}")

    state = game_to_json(game, game.state.current_player_id)
    state["game_id"] = game_id
    state["last_action"] = {"success": True, "message": msg, "gold_found": gold}

    if game.is_game_over():
        return {
            "game_over": True,
            "winner": game.state.total_scores[0] > game.state.total_scores[1],
            "scores": game.state.total_scores,
            "state": state,
        }

    return state


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
