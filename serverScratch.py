# we want, raw upload, raw upload from calculated filter, and PID upload.

# -----------------------------------------------------------------------------
# Raw biquad filter support (direct coefficient upload, no filter calculation)
# -----------------------------------------------------------------------------

def make_raw_payload(ba, offset=0, lo=lowVoltageLim, hi=highVoltageLim):
    """
    Construct the full payload required by the Sinara 'Raw' biquad filter.

    Parameters
    ----------
    ba : iterable
        The raw biquad coefficients in DSP order.
        Typically [b0, b1, b2, a1, a2].
        These should already be scaled appropriately for the FPGA.
    offset : int, optional
        Constant offset added to the filter output (DAC units).
        Defaults to 0.
    lo : int, optional
        Minimum clamp value for the filter output.
        Defaults to -32767 (full-scale negative for a signed 16-bit DAC).
    hi : int, optional
        Maximum clamp value for the filter output.
        Defaults to +32767 (full-scale positive for a signed 16-bit DAC).

    Returns
    -------
    dict
        A dictionary matching the exact structure expected by
        /repr/Raw on the stabilizer.
    """
    return {
        # Convert all coefficients to floats to avoid MQTT / JSON type ambiguity
        "ba": [float(x) for x in ba],

        # Output offset applied after filtering
        "u": int(offset),

        # Output saturation limits (hardware safety + numerical stability)
        "min": int(lo),
        "max": int(hi),
    }

async def apply_filter(ba, offset=0):
    """
    Apply a Raw biquad filter to the selected channel on the stabilizer.

    This function:
      1. Connects to the stabilizer over MQTT
      2. Forces the biquad type to 'Raw'
      3. Uploads the full Raw representation payload
      4. Starts the channel processing

    Parameters
    ----------
    ba : iterable
        Raw biquad coefficients [b0, b1, b2, a1, a2].
    offset : int, optional
        Output offset (DAC units). Defaults to 0.
    """

    # Open an asynchronous MQTT connection to the broker
    async with miniconf.Client(broker, protocol=miniconf.MQTTv5) as client:
        # Bind the client to the stabilizer's configuration namespace
        dev = miniconf.Miniconf(client, prefix)

        # Explicitly set the biquad filter type to "Raw"
        # This tells the firmware NOT to reinterpret coefficients
        await dev.set(f"/ch/{channel}/biquad/0/typ", "Raw")

        # Upload the *entire* Raw biquad payload
        # This is critical: partial updates can leave stale values
        # inside the FPGA configuration.
        await dev.set(
            f"/ch/{channel}/biquad/0/repr/Raw",
            make_raw_payload(ba, offset),
        )

        # Start (or restart) the channel so the new filter takes effect
        await dev.set(f"/ch/{channel}/run", "Run")

        print(f"Filter applied for {ba}")




# -----------------------------------------------------------------------------
# Raw biquad filter support (With filter calculation)
# -----------------------------------------------------------------------------
"""
Basically use filter library and then direct ba coefficient upload
"""


# -----------------------------------------------------------------------------
# General Setting Config Upload
# -----------------------------------------------------------------------------


async def set_stream_target(computer_ip, port=9293):
    async with miniconf.Client(broker, protocol=miniconf.MQTTv5) as client:
        dev = miniconf.Miniconf(client, prefix)
        await dev.set("/stream", f"{computer_ip}:{port}")
        print(f"Streaming target set to {computer_ip}:{port}")




# -----------------------------------------------------------------------------
# Setting Checks
# -----------------------------------------------------------------------------


async def check_filter_type():
    async with miniconf.Client(broker, protocol=miniconf.MQTTv5) as client:
        dev = miniconf.Miniconf(client, prefix)

        typ = await dev.get(f"/ch/{channel}/biquad/0/typ")
        print("Filter type:", typ)
