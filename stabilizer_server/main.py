# main.py

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from .server import StabilizerServer


@asynccontextmanager
async def main(
    *,
    mac: str,
    broker: str,
) -> AsyncGenerator[StabilizerServer]:

    async with StabilizerServer(mac=mac, broker=broker) as server:
        yield server