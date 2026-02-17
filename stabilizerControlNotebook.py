# -----------------------------------------------------------------------------
# Install Packages
# -----------------------------------------------------------------------------
#Note: minconf and paho.mqtt may need to be installed, use "uv pip install miniconf paho.mqtt"



import miniconf
from miniconf import Miniconf

import paho.mqtt.client as mqtt

import stabilizer_filter_design
from stabilizer_filter_design import (
    FilterLibrary,
    StabilizerParameters,
)

import asyncio

# --- Module locations ---
print("miniconf module file:               ", miniconf.__file__)
print("paho.mqtt.client module file:       ", mqtt.__file__)
print("stabilizer_filter_design module file:", stabilizer_filter_design.__file__)
print("asyncio module file:                ", asyncio.__file__)

# --- Class origins (sanity check) ---
print("Miniconf class defined in module:           ", Miniconf.__module__)
print("FilterLibrary class defined in module:      ", FilterLibrary.__module__)
print("StabilizerParameters class defined in module:", StabilizerParameters.__module__)


