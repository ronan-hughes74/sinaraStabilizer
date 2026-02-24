# miniconf_client.py

import anyio
from typing import Callable, Any


class AsyncMiniconfClient:
    """
    Async wrapper around blocking Miniconf MQTT client.
    """

    def __init__(self, mac: str, broker: str) -> None:
        self.mac = mac
        self.broker = broker
        self._client = None
        self._update_callback: Callable[[list[str | int], Any], None] | None = None

    async def connect(self) -> None:
        await anyio.to_thread.run_sync(self._connect_blocking)

    def _connect_blocking(self) -> None:
        from miniconf import Client  # actual Miniconf client

        prefix = f"dt/sinara/dual-iir/{self.mac}"
        self._client = Client(self.broker, prefix)

        self._client.on_update(self._handle_update)
        self._client.connect()

    def _handle_update(self, path, value) -> None:
        if self._update_callback:
            self._update_callback(path, value)

    def register_update_callback(
        self,
        callback: Callable[[list[str | int], Any], None],
    ) -> None:
        self._update_callback = callback

    async def get(self, path: list[str | int]) -> Any:
        return await anyio.to_thread.run_sync(self._client.get, path)

    async def set(self, path: list[str | int], value: Any) -> None:
        await anyio.to_thread.run_sync(self._client.set, path, value)

    async def get_full_tree(self) -> Any:
        return await anyio.to_thread.run_sync(self._client.get_tree)