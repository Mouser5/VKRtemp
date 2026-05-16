import pickle
import time
import uuid
from typing import Optional, Dict, Any, List
from config import REDIS_URL
from web.logger import (
    log_redis_connected,
    log_redis_error,
    log_redis_operation,
)


class GameRedisManager:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or REDIS_URL
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import redis

            try:
                self._client = redis.from_url(self.redis_url, decode_responses=False)
                self._client.ping()
                log_redis_connected(self.redis_url)
            except Exception as e:
                log_redis_error("connect", str(e))
                raise
        return self._client

    def _state_key(self, game_id: str) -> str:
        return f"game:{game_id}:state"

    def _channel(self, game_id: str) -> str:
        return f"game:{game_id}"

    def _player_channel(self, game_id: str, user_id: int) -> str:
        return f"game:{game_id}:player:{user_id}"

    def _action_key(self, game_id: str, player_id: int) -> str:
        return f"game:{game_id}:player:{player_id}:action"

    def _current_player_key(self, game_id: str) -> str:
        return f"game:{game_id}:current_player"

    def _turn_key(self, game_id: str) -> str:
        return f"game:{game_id}:turn"

    def _events_channel(self, game_id: str) -> str:
        return f"game:{game_id}:events"

    def _listener_ready_key(self, game_id: str, player_id: Optional[int] = None) -> str:
        if player_id is None:
            return f"game:{game_id}:listener_ready"
        return f"game:{game_id}:player:{player_id}:listener_ready"

    def create_game(self, game_state: Dict[str, Any]) -> str:
        game_id = str(uuid.uuid4())[:8]
        key = self._state_key(game_id)
        try:
            self.client.set(key, pickle.dumps(game_state))
            log_redis_operation("create_game", game_id, f"key={key}")
        except Exception as e:
            log_redis_error("create_game", str(e))
            raise
        return game_id

    def get_game(self, game_id: str) -> Optional[Dict[str, Any]]:
        key = self._state_key(game_id)
        try:
            data = self.client.get(key)
            log_redis_operation("get_game", game_id, f"found={data is not None}")
            if data is None:
                return None
            return pickle.loads(data)
        except Exception as e:
            log_redis_error("get_game", str(e))
            return None

    def update_game(self, game_id: str, game_state: Dict[str, Any]) -> bool:
        key = self._state_key(game_id)
        try:
            result = self.client.set(key, pickle.dumps(game_state))
            log_redis_operation("update_game", game_id)
            return result
        except Exception as e:
            log_redis_error("update_game", str(e))
            return False

    def delete_game(self, game_id: str) -> bool:
        channel = self._events_channel(game_id)
        try:
            pattern = f"game:{game_id}:*"
            keys = list(self.client.scan_iter(match=pattern, count=100))
            if keys:
                self.client.delete(*keys)
            self.client.publish(channel, pickle.dumps({"event": "game_ended"}))
            log_redis_operation(
                "delete_game", game_id, f"published game_ended deleted={len(keys)}"
            )
            return True
        except Exception as e:
            log_redis_error("delete_game", str(e))
            return False

    def subscribe_player(self, game_id: str, user_id: int) -> str:
        channel = self._player_channel(game_id, user_id)
        log_redis_operation(
            "subscribe_player", game_id, f"user_id={user_id} channel={channel}"
        )
        return channel

    def unsubscribe_player(self, game_id: str, user_id: int) -> bool:
        channel = self._player_channel(game_id, user_id)
        log_redis_operation(
            "unsubscribe_player", game_id, f"user_id={user_id} channel={channel}"
        )
        return True

    def publish_to_player(
        self, game_id: str, user_id: int, message: Dict[str, Any]
    ) -> int:
        channel = self._player_channel(game_id, user_id)
        try:
            count = self.client.publish(channel, pickle.dumps(message))
            log_redis_operation(
                "publish_to_player", game_id, f"user_id={user_id} subscribers={count}"
            )
            return count
        except Exception as e:
            log_redis_error("publish_to_player", str(e))
            return 0

    def publish_to_game(self, game_id: str, message: Dict[str, Any]) -> int:
        channel = self._channel(game_id)
        try:
            count = self.client.publish(channel, pickle.dumps(message))
            log_redis_operation("publish_to_game", game_id, f"subscribers={count}")
            return count
        except Exception as e:
            log_redis_error("publish_to_game", str(e))
            return 0

    def get_all_games(self) -> List[str]:
        try:
            pattern = "game:*:state"
            keys = self.client.keys(pattern)
            game_ids = [k.decode().split(":")[1] for k in keys]
            log_redis_operation("get_all_games", "*", f"count={len(game_ids)}")
            return game_ids
        except Exception as e:
            log_redis_error("get_all_games", str(e))
            return []

    def game_exists(self, game_id: str) -> bool:
        key = self._state_key(game_id)
        try:
            exists = self.client.exists(key) > 0
            log_redis_operation("game_exists", game_id, f"exists={exists}")
            return exists
        except Exception as e:
            log_redis_error("game_exists", str(e))
            return False

    # ─── методы игрового цикла (host → container через Redis) ───

    def store_state(self, game_id: str, state_dict: Dict[str, Any]) -> bool:
        key = self._state_key(game_id)
        try:
            result = self.client.set(key, pickle.dumps(state_dict))
            log_redis_operation("store_state", game_id)
            return bool(result)
        except Exception as e:
            log_redis_error("store_state", str(e))
            return False

    def load_state(self, game_id: str) -> Optional[Dict[str, Any]]:
        return self.get_game(game_id)

    def signal_turn(
        self,
        game_id: str,
        player_id: int,
        turn: int,
        state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        channel = self._events_channel(game_id)
        try:
            pipe = self.client.pipeline()
            if state is not None:
                pipe.set(self._state_key(game_id), pickle.dumps(state))
            pipe.set(self._current_player_key(game_id), player_id)
            pipe.set(self._turn_key(game_id), turn)
            pipe.publish(
                channel,
                pickle.dumps(
                    {
                        "event": "your_turn",
                        "player_id": player_id,
                        "turn": turn,
                        "has_state": state is not None,
                    }
                ),
            )
            pipe.execute()
            log_redis_operation(
                "signal_turn", game_id, f"player={player_id} turn={turn}"
            )
            return True
        except Exception as e:
            log_redis_error("signal_turn", str(e))
            return False

    def wait_for_action(
        self,
        game_id: str,
        player_id: int,
        timeout: float = 30.0,
        turn: Optional[int] = None,
        timeout_sec: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        if timeout_sec is not None:
            timeout = timeout_sec
        key = self._action_key(game_id, player_id)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data = self.client.get(key)
                if data is not None:
                    self.client.delete(key)
                    action = pickle.loads(data)
                    log_redis_operation(
                        "wait_for_action",
                        game_id,
                        (
                            f"player={player_id} turn={turn} action_received"
                            if turn is not None
                            else f"player={player_id} action_received"
                        ),
                    )
                    return action
            except Exception as e:
                log_redis_error("wait_for_action", str(e))
            time.sleep(0.1)
        log_redis_operation(
            "wait_for_action",
            game_id,
            (
                f"player={player_id} turn={turn} timeout={timeout}s"
                if turn is not None
                else f"player={player_id} timeout={timeout}s"
            ),
        )
        return None

    def store_action(
        self, game_id: str, player_id: int, action_dict: Dict[str, Any]
    ) -> bool:
        key = self._action_key(game_id, player_id)
        try:
            result = self.client.set(key, pickle.dumps(action_dict))
            log_redis_operation("store_action", game_id, f"player={player_id}")
            return bool(result)
        except Exception as e:
            log_redis_error("store_action", str(e))
            return False

    def publish_action_ready(self, game_id: str, player_id: int, turn: int) -> int:
        channel = self._events_channel(game_id)
        try:
            count = self.client.publish(
                channel,
                pickle.dumps(
                    {
                        "event": "action_ready",
                        "player_id": player_id,
                        "turn": turn,
                    }
                ),
            )
            log_redis_operation(
                "publish_action_ready",
                game_id,
                f"player={player_id} subscribers={count}",
            )
            return count
        except Exception as e:
            log_redis_error("publish_action_ready", str(e))
            return 0

    def clear_turn_state(self, game_id: str, player_id: int) -> bool:
        key = self._action_key(game_id, player_id)
        try:
            self.client.delete(key)
            log_redis_operation("clear_turn_state", game_id)
            return True
        except Exception as e:
            log_redis_error("clear_turn_state", str(e))
            return False

    def wait_for_listener_ready(
        self, game_id: str, timeout: float = 10.0, player_id: Optional[int] = None
    ) -> bool:
        key = self._listener_ready_key(game_id, player_id)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.client.exists(key):
                    details = (
                        f"player={player_id} ready"
                        if player_id is not None
                        else "ready"
                    )
                    log_redis_operation("wait_for_listener_ready", game_id, details)
                    return True
            except Exception as e:
                log_redis_error("wait_for_listener_ready", str(e))
            time.sleep(0.1)
        details = (
            f"player={player_id} timeout" if player_id is not None else "timeout"
        )
        log_redis_operation("wait_for_listener_ready", game_id, details)
        return False

    def publish_game_event(
        self,
        game_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> int:
        channel = self._events_channel(game_id)
        message = {
            "event": event_type,
            "payload": payload or {},
        }
        try:
            count = self.client.publish(channel, pickle.dumps(message))
            log_redis_operation(
                "publish_game_event",
                game_id,
                f"event={event_type} subscribers={count}",
            )
            return count
        except Exception as e:
            log_redis_error("publish_game_event", str(e))
            return 0

    def wait_for_turn_signal(
        self, game_id: str, player_id: int, timeout: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        channel = self._events_channel(game_id)
        try:
            pubsub = self.client.pubsub()
            pubsub.subscribe(channel)
            deadline = time.time() + timeout
            while time.time() < deadline:
                msg = pubsub.get_message(timeout=1.0)
                if msg and msg["type"] == "message":
                    event = pickle.loads(msg["data"])
                    if (
                        event.get("event") == "your_turn"
                        and event.get("player_id") == player_id
                    ):
                        log_redis_operation(
                            "wait_for_turn_signal",
                            game_id,
                            f"player={player_id} turn={event.get('turn')}",
                        )
                        pubsub.unsubscribe(channel)
                        return event
            pubsub.unsubscribe(channel)
            log_redis_operation(
                "wait_for_turn_signal",
                game_id,
                f"player={player_id} timeout",
            )
            return None
        except Exception as e:
            log_redis_error("wait_for_turn_signal", str(e))
            return None


game_redis = GameRedisManager()