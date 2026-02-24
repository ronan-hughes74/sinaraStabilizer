# server.py

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Self

from rockdove.rpc import RPCNamespace
from anyio import create_task_group

from .miniconf_client import AsyncMiniconfClient
from .mirror import StabilizerMirror


class StabilizerServer(RPCNamespace):
    """
    Rockdove RPC namespace wrapping Miniconf + mirror.
    """

    def __init__(self, mac: str, broker: str) -> None:
        super().__init__()
        self.miniconf = AsyncMiniconfClient(mac, broker)
        self.mirror = StabilizerMirror()

    # ---------------- Lifecycle ----------------

    @asynccontextmanager
    async def __asynccontextmanager__(self) -> AsyncGenerator[Self]:
        await self.miniconf.connect()

        # Populate initial mirror
        tree = await self.miniconf.get_full_tree()
        self.mirror._tree = tree

        # Register update callback
        self.miniconf.register_update_callback(
            self.mirror.update_subtree
        )

        yield self

    # ---------------- RPC: IIR ----------------

    async def set_iir_gain(
        self,
        channel: int,
        param: str,
        value: float,
    ) -> None:
        await self.miniconf.set(["iir", channel, param], value)

    def get_iir_gain(
        self,
        channel: int,
        param: str,
    ) -> float:
        return self.mirror.get(["iir", channel, param])

    # ---------------- RPC: DAC ----------------

    async def set_dac(self, channel: int, value: int) -> None:
        await self.miniconf.set(["dac", channel], value)

    def get_dac(self, channel: int) -> int:
        return self.mirror.get(["dac", channel])

    # ---------------- RPC: Stream ----------------

    async def enable_stream(self, enable: bool) -> None:
        await self.miniconf.set(["stream", "enable"], enable)

    def get_stream_status(self) -> bool:
        return self.mirror.get(["stream", "enable"])