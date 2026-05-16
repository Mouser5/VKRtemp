import os
import sys
import redis
import importlib.util

sys.path.insert(0, "/app/src")
from bot_redis import RedisBotListener

GAME_ID = os.environ.get("GAME_ID")
PLAYER_ID = int(os.environ.get("PLAYER_ID", 0))
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")


def load_agent(code: str, player_id: int):
    module_name = f"bot_agent_{player_id}"
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(module_name, loader=None))
    sys.modules[module_name] = module
    exec(compile(code, "<bot_code>", "exec"), module.__dict__)

    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and hasattr(obj, "choose_action"):
            return obj(player_id=player_id)
    raise ValueError("Класс агента с методом choose_action не найден")


if __name__ == "__main__":
    if not GAME_ID:
        print("ОШИБКА: GAME_ID не задан.")
        sys.exit(1)

    r = redis.from_url(REDIS_URL)

    code_key = f"game:{GAME_ID}:p{PLAYER_ID}:code"
    bot_code_bytes = r.get(code_key)

    if not bot_code_bytes:
        print(f"ОШИБКА: Код бота не найден в Redis по ключу {code_key}")
        sys.exit(1)

    agent = load_agent(bot_code_bytes.decode("utf-8"), PLAYER_ID)
    print(f"[Worker] Агент для Игрока {PLAYER_ID} успешно загружен.")

    listener = RedisBotListener(
        redis_url=REDIS_URL,
        game_id=GAME_ID,
        agent_instance=agent,
        player_id=PLAYER_ID
    )

    listener.listen()