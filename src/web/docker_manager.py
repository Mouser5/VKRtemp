import docker
import os
import time
import uuid
from typing import Optional, Dict
import requests
from loguru import logger
from web.logger import (
    log_container_start,
    log_container_stop,
    log_container_error,
)


class DockerManager:
    def __init__(self):
        self._docker_client = None
        self.game_api_url = "http://game-api:8000"
        self.redis_url = "redis://redis:6379/0"
        self.network = os.getenv("DOCKER_NETWORK")

    @property
    def client(self):
        if self._docker_client is None:
            try:
                self._docker_client = docker.from_env()
            except Exception as e:
                log_container_error("init", f"Docker недоступен: {e}")
                raise
        return self._docker_client

    def _wait_container_running(self, container, timeout: float = 15.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            container.reload()
            if container.status == "running":
                return True
            time.sleep(0.5)
        return False

    def _wait_container_ready(self, container_id: str, timeout: float = 15.0) -> bool:
        url = f"http://{container_id}:8001/health"
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200:
                    return True
            except requests.ConnectionError:
                pass
            time.sleep(0.5)
        return False

    def _network_exists(self, network_name: str) -> bool:
        try:
            self.client.networks.get(network_name)
            return True
        except docker.errors.NotFound:
            return False
        except docker.errors.APIError as e:
            logger.warning(f"Не удалось проверить сеть Docker '{network_name}': {e}")
            return False

    def _detect_current_container_network(self) -> Optional[str]:
        """Определяет сеть контейнера по HOSTNAME текущего процесса."""
        container_name = os.getenv("HOSTNAME")
        if not container_name:
            return None

        try:
            current_container = self.client.containers.get(container_name)
            networks = (
                current_container.attrs.get("NetworkSettings", {}).get("Networks", {})
            )
            if networks:
                return next(iter(networks.keys()), None)
        except docker.errors.NotFound:
            return None
        except docker.errors.APIError as e:
            logger.warning(f"Не удалось определить сеть текущего контейнера: {e}")
            return None

    def _resolve_network(self) -> Optional[str]:
        """Возвращает рабочую сеть Docker и кэширует автоопределённое имя в self.network."""
        configured_network = self.network
        if configured_network and self._network_exists(configured_network):
            return configured_network

        detected_network = self._detect_current_container_network()
        if detected_network and self._network_exists(detected_network):
            self.network = detected_network
            return detected_network

        if configured_network:
            log_container_error("network", f"Сеть Docker не найдена: {configured_network}")
        return None

    def _start_container(
            self,
            image: str,
            name: str,
            environment: dict,
    ) -> Dict[str, str]:
        try:
            container = self.client.containers.run(
                image,
                name=name,
                detach=True,
                environment=environment,
                remove=False,
                network=self.network,
            )

            if not self._wait_container_running(container):
                container.stop()
                container.remove()
                log_container_error(name, "Контейнер не перешёл в состояние running")
                return {"error": "Container did not reach running state"}

            return {"container_id": name}

        except docker.errors.ImageNotFound:
            log_container_error(name, "Image gnomes-bot:latest не найден")
            return {
                "error": "Image not found. Build with: docker build -t gnomes-bot -f src/bot-container/Dockerfile ."
            }
        except Exception as e:
            log_container_error(name, str(e))
            return {"error": str(e)}

    # def start_game_container(
    #     self,
    #     bot_code: str,
    #     user_id: int,
    #     game_id: str,
    #     redis_channel: str,
    # ) -> Dict[str, str]:
    #     container_id = f"game-{game_id}-{uuid.uuid4().hex[:8]}"
    #
    #     result = self._start_container(
    #         "gnomes-bot:latest",
    #         container_id,
    #         {
    #             "GAME_API_URL": self.game_api_url,
    #             "GAME_ID": game_id,
    #             "REDIS_URL": self.redis_url,
    #             "USER_CHANNEL": redis_channel,
    #             "USER_ID": str(user_id),
    #         },
    #     )
    #
    #     if "error" in result:
    #         return result
    #
    #     base_url = f"http://{container_id}:8001"
    #
    #     resp = requests.post(
    #         f"{base_url}/init",
    #         json={"code": bot_code, "player_id": 0, "game_id": game_id},
    #         timeout=10,
    #     )
    #     if resp.status_code != 200:
    #         self.stop_game_container(container_id)
    #         log_container_error(container_id, f"Init failed: {resp.text}")
    #         return {"error": f"Init failed: {resp.text}"}
    #
    #     log_container_start(container_id, base_url, bot_code)
    #     return {
    #         "container_id": container_id,
    #         "url": base_url,
    #         "game_id": game_id,
    #     }
    #
    # def start_bot_container(self, bot_code: str, player_id: int = 0) -> Dict[str, str]:
    #     container_id = f"bot-{uuid.uuid4().hex[:8]}"
    #
    #     result = self._start_container(
    #         "gnomes-bot:latest",
    #         container_id,
    #         {
    #             "GAME_API_URL": self.game_api_url,
    #         },
    #     )
    #
    #     if "error" in result:
    #         return result
    #
    #     base_url = f"http://{container_id}:8001"
    #
    #     resp = requests.post(
    #         f"{base_url}/init",
    #         json={"code": bot_code, "player_id": player_id},
    #         timeout=10,
    #     )
    #     if resp.status_code != 200:
    #         self.stop_game_container(container_id)
    #         log_container_error(container_id, f"Init failed: {resp.text}")
    #         return {"error": f"Init failed: {resp.text}"}
    #
    #     log_container_start(container_id, base_url, bot_code)
    #     return {"container_id": container_id, "url": base_url}

    def start_game_container_redis(
        self,
        bot_code: str,
        user_id: int,
        game_id: str,
    ) -> Dict[str, str]:
        container_id = f"game-{game_id}-{uuid.uuid4().hex[:8]}"

        result = self._start_container(
            "gnomes-bot:latest",
            container_id,
            {
                "GAME_API_URL": self.game_api_url,
                "GAME_ID": game_id,
                "REDIS_URL": self.redis_url,
                "REDIS_MODE": "1",
                "USER_ID": str(user_id),
            },
        )

        if "error" in result:
            return result

        base_url = f"http://{container_id}:8001"

        resp = requests.post(
            f"{base_url}/init_redis",
            json={
                "code": bot_code,
                "player_id": 0,
                "redis_url": self.redis_url,
                "game_id": game_id,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            if not self.stop_game_container(container_id):
                log_container_error(
                    container_id, "Cleanup failed after init redis error"
                )
            log_container_error(container_id, f"Init redis failed: {resp.text}")
            return {"error": f"Init redis failed: {resp.text}"}

        log_container_start(container_id, base_url, bot_code)
        return {
            "container_id": container_id,
            "url": base_url,
            "game_id": game_id,
        }

    def start_player_container_redis(
        self,
        game_id: str,
        player_id: int,
    ) -> Dict[str, str]:
        # Убрали аргумент bot_code, код мы положим в Redis до вызова этого метода
        container_id = f"game-{game_id}-p{player_id}-{uuid.uuid4().hex[:8]}"

        result = self._start_container(
            "gnomes-bot:latest",
            container_id,
            {
                "GAME_API_URL": self.game_api_url,
                "GAME_ID": game_id,
                "REDIS_URL": self.redis_url,
                "PLAYER_ID": str(player_id),
            },
        )

        if "error" in result:
            return result

        # Больше не делаем requests.post() к контейнеру!
        log_container_start(container_id, "Redis Pub/Sub", "Code loaded from Redis")
        return {
            "container_id": container_id,
            "game_id": game_id,
            "player_id": str(player_id),
        }

    def stop_game_container(self, container_id: str) -> bool:
        try:
            container = self.client.containers.get(container_id)
            container.stop()
            container.remove()
            log_container_stop(container_id, "завершение игры")
            return True
        except Exception:
            log_container_error(container_id, "Ошибка при остановке")
            return False

    def stop_bot_container(self, container_id: str) -> bool:
        try:
            container = self.client.containers.get(container_id)
            container.stop()
            container.remove()
            log_container_stop(container_id, "завершение")
            return True
        except Exception:
            log_container_error(container_id, "Ошибка при остановке")
            return False

    def stop_and_remove_container(self, container_id: str) -> bool:
        try:
            container = self.client.containers.get(container_id)
            container.stop()
            container.remove()
            log_container_stop(container_id, "stop_and_remove")
            return True
        except Exception:
            log_container_error(container_id, "Ошибка при stop_and_remove")
            return False

    # def get_container_status(self, container_id: str) -> Optional[str]:
    #     try:
    #         container = self.client.containers.get(container_id)
    #         return container.status
    #     except Exception:
    #         return None

    # def cleanup_all_bots(self) -> int:
    #     count = 0
    #     try:
    #         for container in self.client.containers.list(filters={"name": "bot-"}):
    #             container.stop()
    #             container.remove()
    #             log_container_stop(container.name, "cleanup ботов")
    #             count += 1
    #     except Exception:
    #         pass
    #     logger.info(f"🧹 Очищено контейнеров ботов: {count}")
    #     return count
    #
    # def cleanup_all_games(self) -> int:
    #     count = 0
    #     try:
    #         for container in self.client.containers.list(filters={"name": "game-"}):
    #             container.stop()
    #             container.remove()
    #             log_container_stop(container.name, "cleanup игр")
    #             count += 1
    #     except Exception:
    #         pass
    #     logger.info(f"🧹 Очищено контейнеров игр: {count}")
    #     return count


docker_manager = DockerManager()