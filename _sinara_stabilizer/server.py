"""
Stabilizer Rockdove Server
==========================

This server integrates a Sinara Stabilizer (dual-iir applet)
into the pydux / Rockdove distributed control system.

Architecture Summary
--------------------

Hardware:
    Stabilizer device running dual-iir applet
    Publishes telemetry via MQTT
    Accepts configuration via MQTT
    Streams raw ADC data via UDP (handled externally by stabilizer-stream)

This server:
    - Subscribes to MQTT telemetry + status topics
    - Publishes configuration commands
    - Maintains internal device state
    - Exposes RPC methods to GUI via Rockdove
    - Optionally launches stabilizer-stream later

This server DOES NOT:
    - Process UDP stream data
    - Implement feedback loops
    - Replace stabilizer-stream

It only handles control + state abstraction.

This file is intentionally heavily commented for lab maintainability.
"""

# -----------------------------------------------------------------------------
# Standard Library Imports
# -----------------------------------------------------------------------------

import json
import logging
import subprocess
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator, Self

# -----------------------------------------------------------------------------
# Third-Party Imports
# -----------------------------------------------------------------------------

import anyio
from anyio import AsyncContextManagerMixin
from rockdove.rpc import RPCNamespace

# -----------------------------------------------------------------------------
# Logging Setup
# -----------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Configuration Dataclass
# -----------------------------------------------------------------------------

@dataclass(kw_only=True, frozen=True, slots=True)
class StabilizerConfig:
    """
    Configuration required to connect to and control a Stabilizer.

    Parameters
    ----------
    mac:
        MAC address of the stabilizer device.
        Example: "44-b7-d0-cc-65-c0"

    broker:
        MQTT broker IP or hostname.
        Example: "192.168.1.222"

    stream_target:
        IP address where UDP stream should be sent.
        Usually the control computer IP.

    low_voltage / high_voltage:
        DAC limits enforced by server.
        These should match hardware safety constraints.
    """

    mac: str
    broker: str
    stream_target: str
    low_voltage: int
    high_voltage: int


# -----------------------------------------------------------------------------
# Stabilizer RPC Namespace
# -----------------------------------------------------------------------------

class Stabilizer(RPCNamespace, AsyncContextManagerMixin):
    """
    Rockdove RPC namespace for a single Stabilizer device.

    Lifecycle:
        rockdove serve -> calls main() -> enters async context
        __asynccontextmanager__ starts MQTT background task
        RPC methods become callable by GUI
    """

    # -------------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------------

    def __init__(self, config: StabilizerConfig) -> None:
        super().__init__()
        self.config = config

        # Internal device state (updated by MQTT thread)
        self.telemetry: dict | None = None
        self.alive: bool = False

        # MQTT client object (created in blocking thread)
        self._mqtt_client = None

        # Track whether MQTT connection is active
        self._mqtt_connected = False

    # -------------------------------------------------------------------------
    # Async Lifecycle Management
    # -------------------------------------------------------------------------

    @asynccontextmanager
    async def __asynccontextmanager__(self) -> AsyncGenerator[Self]:
        """
        This method defines what happens when the server starts and stops.

        Rockdove will:
            async with Stabilizer(...) as namespace:
                yield namespace

        We start background tasks here.
        """

        logger.info("Starting Stabilizer server for %s", self.config.mac)

        async with anyio.create_task_group() as task_group:
            # Start MQTT client in background
            task_group.start_soon(self._mqtt_loop)

            # Yield control back to Rockdove
            yield self

        logger.info("Stabilizer server shutting down.")

    # -------------------------------------------------------------------------
    # MQTT Background Loop
    # -------------------------------------------------------------------------

    async def _mqtt_loop(self) -> None:
        """
        Runs the blocking MQTT client in a worker thread.

        Why?
        ----
        paho-mqtt is blocking.
        Rockdove uses async + anyio.
        We must not block the event loop.

        So we isolate MQTT in a thread.
        """

        await anyio.to_thread.run_sync(self._blocking_mqtt)

    # -------------------------------------------------------------------------

    def _blocking_mqtt(self) -> None:
        """
        Blocking MQTT client.
        Runs forever inside worker thread.
        """

        import paho.mqtt.client as mqtt

        prefix = f"dt/sinara/dual-iir/{self.config.mac}"

        # ------------------ MQTT Callbacks ------------------

        def on_connect(client, userdata, flags, rc):
            logger.info("Connected to MQTT broker %s", self.config.broker)
            self._mqtt_connected = True

            # Subscribe to topics relevant to this device
            client.subscribe(f"{prefix}/telemetry")
            client.subscribe(f"{prefix}/alive")
            client.subscribe(f"{prefix}/meta")

        def on_disconnect(client, userdata, rc):
            logger.warning("Disconnected from MQTT broker.")
            self._mqtt_connected = False

        def on_message(client, userdata, msg):
            """
            Handles incoming MQTT messages.
            """

            topic = msg.topic

            try:
                payload = json.loads(msg.payload)
            except Exception:
                logger.warning("Failed to parse MQTT payload.")
                return

            # Telemetry update
            if topic.endswith("telemetry"):
                self.telemetry = payload

            # Alive heartbeat
            elif topic.endswith("alive"):
                self.alive = bool(payload)

        # ------------------ Client Setup ------------------

        client = mqtt.Client()
        self._mqtt_client = client

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        client.connect(self.config.broker)
        client.loop_forever()

    # -------------------------------------------------------------------------
    # ---------------------- RPC GETTERS (GUI Reads) --------------------------
    # -------------------------------------------------------------------------

    def get_cpu_temp(self) -> float:
        if self.telemetry:
            return self.telemetry.get("cpu_temp", 0.0)
        return 0.0

    def get_adc(self, channel: int) -> float:
        if self.telemetry:
            return self.telemetry["adcs"][channel]
        return 0.0

    def get_dac(self, channel: int) -> float:
        if self.telemetry:
            return self.telemetry["dacs"][channel]
        return 0.0

    def get_alive(self) -> bool:
        return self.alive

    def get_mqtt_status(self) -> bool:
        return self._mqtt_connected

    # -------------------------------------------------------------------------
    # ---------------------- RPC SETTERS (Control Commands) -------------------
    # -------------------------------------------------------------------------

    async def set_voltage_limits(self, low: int, high: int) -> None:
        """
        Publish voltage limit configuration via MQTT.

        You MUST modify topic/payload here
        to match actual dual-iir configuration schema.
        """

        if low < -32767 or high > 32767:
            raise ValueError("Voltage limits exceed hardware constraints.")

        payload = {
            "low": low,
            "high": high,
        }

        topic = f"dt/sinara/dual-iir/{self.config.mac}/config/voltage_limits"

        await anyio.to_thread.run_sync(
            self._mqtt_client.publish,
            topic,
            json.dumps(payload),
        )

    # -------------------------------------------------------------------------
    # ---------------------- STREAM LAUNCH PLACEHOLDER ------------------------
    # -------------------------------------------------------------------------

    async def launch_stream(self) -> None:
        """
        Launch stabilizer-stream process.

        This runs separately from the Rockdove server.
        Adjust CLI flags later once stabilizer-stream
        configuration is finalized.
        """

        await anyio.to_thread.run_sync(self._launch_stream_process)

    def _launch_stream_process(self) -> None:
        subprocess.Popen([
            "stabilizer-stream",
            "--target",
            self.config.stream_target,
        ])

    # -------------------------------------------------------------------------
    # Future Expansion Points
    # -------------------------------------------------------------------------

    """
    Recommended extensions:

    - Add profile loading via ConfigHandler (like Power_Stabilization)
    - Add persistent voltage limit storage
    - Add configuration schema for:
        - IIR gains
        - Lock state
        - Stream enable
    - Add periodic send_signal() updates to GUI
    - Add structured telemetry dataclass
    - Add reconnection backoff strategy
    """

# -----------------------------------------------------------------------------
# Rockdove Entry Point
# -----------------------------------------------------------------------------

@asynccontextmanager
async def main(
    *,
    mac: str,
    broker: str,
    stream_target: str,
    low_voltage: int,
    high_voltage: int,
) -> AsyncGenerator[Stabilizer]:
    """
    Entry point for `rockdove serve`.

    Example rockdove config usage:

        rockdove serve stabilizer \
            --mac 44-b7-d0-cc-65-c0 \
            --broker 192.168.1.222 \
            --stream-target 192.168.1.134 \
            --low-voltage -6553 \
            --high-voltage 6553
    """

    config = StabilizerConfig(
        mac=mac,
        broker=broker,
        stream_target=stream_target,
        low_voltage=low_voltage,
        high_voltage=high_voltage,
    )

    async with Stabilizer(config=config) as namespace:
        yield namespace