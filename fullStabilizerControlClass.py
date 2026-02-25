#This code maps the entire miniconf configuration space for the stabilizer to python data classes, allowing the tree to be 
# mirrored in Python.


from dataclasses import dataclass, field
from enum import Enum 

"""
Beginning snippets of code are shown below, to help give context and guide the constructions of the data classes.
"""
# -----------------------------------------------------------------------------
# Initial Stabilizer Config
# -----------------------------------------------------------------------------
broker = "192.168.1.222"            # replace with your broker IP or hostname
stabilizer_name = "44-b7-d0-cc-65-c0" # check this name from the MQTT explorer window
prefix = f"dt/sinara/dual-iir/{stabilizer_name}"       # topic to subscribe to
channel = 0
computer_ip = "192.168.1.134" #IP address of the computer you are running this on



async def apply_PID_filter():
    # Open an asynchronous MQTT connection to the broker
    async with miniconf.Client(broker, protocol=miniconf.MQTTv5) as client:
        # Bind the client to the stabilizer's configuration namespace
        dev = miniconf.Miniconf(client, prefix)

        await dev.set(f"location", "value")

