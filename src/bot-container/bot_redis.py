import sys
import pickle
import threading
import redis
from typing import Optional

sys.path.insert(0, "/app/src")


class RedisBotListener:
    def __init__(
        self,
        redis_url: str,
        game_id: str,
        agent_instance,
        player_id: int = 0,
    ):
        self.redis_url = redis_url
        self.game_id = game_id
        self.agent = agent_instance
        self.player_id = player_id
        self._client: Optional[redis.Redis] = None
        self._running = False

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self.redis_url, decode_responses=False)
            self._client.ping()
        return self._client

    def _state_key(self) -> str:
        return f"game:{self.game_id}:state"

    def _action_key(self) -> str:
        return f"game:{self.game_id}:player:{self.player_id}:action"

    def _events_channel(self) -> str:
        return f"game:{self.game_id}:events"

    def _load_state(self):
        data = self.client.get(self._state_key())
        if data is None:
            return None
        return pickle.loads(data)

    def _store_action(self, action_dict: dict):
        self.client.set(self._action_key(), pickle.dumps(action_dict))

    def _publish_action_ready(self, turn: int):
        self.client.publish(
            self._events_channel(),
            pickle.dumps(
                {
                    "event": "action_ready",
                    "player_id": self.player_id,
                    "turn": turn,
                }
            ),
        )

    def _handle_turn(self, turn: int):
        from web.game_proxy import GameProxy

        state_dict = self._load_state()
        if state_dict is None:
            print(f"[RedisBot] No state found for turn {turn}")
            return

        game = GameProxy.from_state(state_dict)
        action = self.agent.choose_action(game)
        if action is None:
            self._store_action({"type": "None", "reason": "no_legal_actions"})
        else:
            action_dict = {
                "type": type(action).__name__,
                "template_id": getattr(action, "template_id", None),
                "x": getattr(action, "x", None),
                "y": getattr(action, "y", None),
                "is_rotated_180": getattr(action, "is_rotated_180", False),
                "templates": getattr(action, "templates", None),
                "repair_equipment": getattr(action, "repair_equipment", None),
            }
            self._store_action(action_dict)

        self._publish_action_ready(turn)

    def listen(self, timeout: float = None):
        self._running = True
        channel = self._events_channel()
        pubsub = self.client.pubsub()
        pubsub.subscribe(channel)
        self.client.set(f"game:{self.game_id}:listener_ready", "1")
        self.client.set(f"game:{self.game_id}:player:{self.player_id}:listener_ready", "1")

        print(f"[RedisBot] Listening on {channel}")

        try:
            while self._running:
                msg = pubsub.get_message(timeout=1.0)
                if msg is None:
                    if timeout is not None:
                        timeout -= 1
                        if timeout <= 0:
                            break
                    continue

                if msg["type"] != "message":
                    continue

                try:
                    event = pickle.loads(msg["data"])
                except Exception:
                    continue

                event_type = event.get("event")

                if event_type == "your_turn":
                    turn = event.get("turn", 0)
                    print(
                        f"[RedisBot] Your turn (player={self.player_id}, turn={turn})"
                    )
                    self._handle_turn(turn)

                elif event_type == "game_ended":
                    print("[RedisBot] Game ended")
                    break
        # [RedisBot] Your turn (player=0, turn=0)
        #
        # [RedisBot] Your turn (player=0, turn=1)
        except KeyboardInterrupt:
            pass
        finally:
            pubsub.unsubscribe(channel)
            self._running = False
            print("[RedisBot] Stopped")

    def stop(self):
        self._running = False


def start_listener_thread(
    redis_url: str,
    game_id: str,
    agent_instance,
    player_id: int = 0,
    daemon: bool = True,
) -> RedisBotListener:
    listener = RedisBotListener(
        redis_url=redis_url,
        game_id=game_id,
        agent_instance=agent_instance,
        player_id=player_id,
    )
    thread = threading.Thread(
        target=listener.listen,
        daemon=daemon,
    )
    thread.start()
    return listener