"""
============================================================
File: server.py
Author: Ronan Hughes and ChatGPT
Created: 2/23/2026
Last Modified: 2/23/2026

Description:
    Complete plug-and-play Sinara Stabilizer Server.
    Computes filter coefficients, applies PID settings,
    sets streaming targets, and manages stabilizer loops
    autonomously.

Dependencies:
    - miniconf
    - anyio
    - rockdove
    - pydux.control_support.config_handler
============================================================
"""
import logging
import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Self

import anyio
from anyio import AsyncContextManagerMixin, CancelScope
from rockdove.rpc import RPCNamespace

import miniconf
from miniconf import Miniconf

from pydux.control_support.config_handler import ConfigHandler

# -----------------------------------------------------------------------------
# Filter Design
# -----------------------------------------------------------------------------
import sympy as sp
from sympy import pi
import numpy as np
from scipy import signal
from functools import lru_cache

class StabilizerParameters:
    Ts = 128 / 100e6
    fs = 1 / Ts
    full_scale_code = (1 << 15) - 1
    full_scale_volt = 10.0
    volt_per_lsb = full_scale_volt / full_scale_code

    @classmethod
    def volt_to_mu(cls, val):
        return int(np.round(val / cls.volt_per_lsb))

    @classmethod
    def mu_to_volt(cls, val):
        return val * cls.volt_per_lsb

class FilterLibrary:
    Ts = sp.symbols("Ts")
    q, s = sp.symbols("q s")
    K, g, f0, F0, Q = sp.symbols("K g f0 F0 Q")

    library = {
        "LP": K / (1 + s / (2 * pi * f0)),
        "HP": K / (1 + 2 * pi * f0 / s),
        "AP": K * (s / (2 * pi * f0) - 1) / (s / (2 * pi * f0) + 1),
        "I": K * 2 * pi * f0 / s,
        "PI": K * (1 + s / (2 * pi * f0)) / (1 / g + s / (2 * pi * f0)),
        "P": K,
        "PD": K * (1 + s / (2 * pi * f0)) / (1 + s / (2 * pi * f0 * g)),
    }

    names = list(library.keys())

    @classmethod
    @lru_cache
    def get_ba_sym(cls, name):
        H = cls.library[name]
        Hq = (
            H.subs({cls.s: 2 / cls.Ts * (1 - cls.q) / (1 + cls.q)})
            .subs({pi * cls.f0 * cls.Ts: cls.F0})
            .simplify()
        )
        b, a = [expr.expand().collect(cls.q) for expr in sp.fraction(Hq)]
        a0 = a.coeff(cls.q, 0)
        a_coeffs = [-a.coeff(cls.q, n)/a0 for n in range(1,3)]
        b_coeffs = [b.coeff(cls.q, n)/a0 for n in range(3)]
        return b_coeffs + a_coeffs

    @classmethod
    def get_ba(cls, name, **params):
        ba = cls.get_ba_sym(name)
        if "Ts" not in params:
            params["Ts"] = StabilizerParameters.Ts
        syms = set.union(*(expr.free_symbols for expr in ba))
        p = {s: params[str(s)] for s in syms}
        return [float(expr.evalf(subs=p)) for expr in ba]

# -----------------------------------------------------------------------------
# Logger
# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
@dataclass(kw_only=True, frozen=True, slots=True)
class SinaraStabilizerConfig:
    broker: str
    prefix: str
    channel: int

# -----------------------------------------------------------------------------
# Server
# -----------------------------------------------------------------------------
class SinaraStabilizerServer(RPCNamespace, AsyncContextManagerMixin):
    def __init__(self, parameters_file: str, config: SinaraStabilizerConfig):
        super().__init__()
        self.config = config
        self.config_handler = ConfigHandler(
            ["servers", "sinara_stabilizer", parameters_file]
        )
        self.parameters = {}
        self._connected = False
        self._dev: Miniconf | None = None

    # Lifecycle
    @asynccontextmanager
    async def __asynccontextmanager__(self) -> AsyncGenerator[Self]:
        await self._load_config()
        try:
            async with miniconf.Client(self.config.broker, protocol=miniconf.MQTTv5) as client:
                self._dev = Miniconf(client, self.config.prefix)
                self._connected = True
                await self.send_signal("all", "on_connection_state", True)
                yield self
        finally:
            self._connected = False
            await self.send_signal("all", "on_connection_state", False)
            with CancelScope(shield=True):
                await self.config_handler.save(self.parameters)

    # Utilities
    def _make_raw_payload(self, ba, offset=0):
        return {
            "ba": [float(x) for x in ba],
            "u": int(offset),
            "min": int(self.parameters["low_voltage_limit"]),
            "max": int(self.parameters["high_voltage_limit"]),
        }

    def _make_pid_payload(self, kp, ki, kd, setpoint, preload):
        return {
            "kp": float(kp),
            "ki": float(ki),
            "kd": float(kd),
            "setpoint": float(setpoint),
            "u": float(preload),
            "min": int(self.parameters["low_voltage_limit"]),
            "max": int(self.parameters["high_voltage_limit"]),
        }

    # ----------------------
    # Raw Filter API
    # ----------------------
    async def apply_raw_filter(self, ba, offset=0):
        ch = self.config.channel
        await self._dev.set(f"/ch/{ch}/biquad/0/typ", "Raw")
        await self._dev.set(f"/ch/{ch}/biquad/0/repr/Raw", self._make_raw_payload(ba, offset))
        await self._dev.set(f"/ch/{ch}/run", "Run")
        await self.send_signal("others", "on_raw_filter_applied", ba, offset)

    # ----------------------
    # PID API
    # ----------------------
    async def apply_pid(self, kp, ki, kd, setpoint, preload=0):
        ch = self.config.channel
        await self._dev.set(f"/ch/{ch}/run", "Hold")
        await self._dev.set(f"/ch/{ch}/biquad/0/typ", "Pid")
        await self._dev.set(f"/ch/{ch}/biquad/0/repr/Pid", self._make_pid_payload(kp, ki, kd, setpoint, preload))
        await self._dev.set(f"/ch/{ch}/run", "Run")
        await self.send_signal("others", "on_pid_applied", kp, ki, kd, setpoint, preload)

    # ----------------------
    # High-Level Filter & PID Helpers
    # ----------------------
    async def design_and_apply_filter(self, filter_name, **params):
        """
        Design a filter using FilterLibrary and apply as Raw.
        params can include K, f0, g, Q, offset.
        """
        ba = FilterLibrary.get_ba(filter_name, **params)
        offset = params.get("offset", 0)
        await self.apply_raw_filter(ba, offset)

    async def set_pid_from_gui(self, Kp, Ki, Kd, setpoint, preload=None):
        """
        Fully plug-and-play PID setup:
        - Kp, Ki, Kd: controller gains
        - setpoint: target setpoint
        - preload: integrator preload (optional)
        """
        ch = self.config.channel
        await self._dev.set(f"/ch/{ch}/run", "Hold")
        await self._dev.set(f"/ch/{ch}/biquad/0/typ", "Pid")

        # Gains
        await self._dev.set(f"/ch/{ch}/biquad/0/repr/Pid/gain/p", float(Kp))
        await self._dev.set(f"/ch/{ch}/biquad/0/repr/Pid/gain/i", float(Ki))
        await self._dev.set(f"/ch/{ch}/biquad/0/repr/Pid/gain/d", float(Kd))

        # Limits
        await self._dev.set(f"/ch/{ch}/biquad/0/repr/Pid/min", self.parameters["low_voltage_limit"])
        await self._dev.set(f"/ch/{ch}/biquad/0/repr/Pid/max", self.parameters["high_voltage_limit"])

        # Setpoint
        await self._dev.set(f"/ch/{ch}/biquad/0/repr/Pid/setpoint", float(setpoint))

        # Integrator preload
        if preload is None:
            preload = 0.0
        await self._dev.set(f"/ch/{ch}/biquad/0/repr/Pid/limit/i", float(preload))

        await asyncio.sleep(0.05)
        await self._dev.set(f"/ch/{ch}/run", "Run")
        await self.send_signal("others", "on_pid_enabled")

    # ----------------------
    # Streaming
    # ----------------------
    async def set_stream_target(self, computer_ip: str, port: int = 9293):
        await self._dev.set("/stream", f"{computer_ip}:{port}")
        await self.send_signal("others", "on_stream_target_set", computer_ip, port)

    # ----------------------
    # Config
    # ----------------------
    async def _load_config(self):
        self.parameters = await self.config_handler.load()
        if self.parameters is None:
            self.parameters = {
                "low_voltage_limit": -6553,
                "high_voltage_limit": 6553,
            }

    # ----------------------
    # Status
    # ----------------------
    def get_connection_status(self) -> bool:
        return self._connected

# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------
@asynccontextmanager
async def main(
    *,
    parameters_file: str,
    broker: str,
    prefix: str,
    channel: int,
) -> AsyncGenerator[SinaraStabilizerServer]:

    config = SinaraStabilizerConfig(
        broker=broker,
        prefix=prefix,
        channel=channel,
    )

    async with SinaraStabilizerServer(
        parameters_file=parameters_file,
        config=config,
    ) as namespace:
        yield namespace