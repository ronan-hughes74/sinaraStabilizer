# sinaraStabilizer
Repository for the artiq sinara stabilizer, prior to it being moved into Jayich Lab

# Sinara Stabilizer Control System

## Overview

This repository provides a plug-and-play backend server for controlling a Sinara dual-IIR stabilizer. The server handles all low-level communication and computation, while the GUI applet serves as the only user interface for changing filters, PID gains, or streaming targets.

Once launched, the server operates hands-off, applying commands received from the GUI via RPC and MQTT/Miniconf.

## Architecture

GUI (PyQt5 Applet)
  - User chooses filters / PID gains
  - Sends inputs via RPC to server

          |
          v

SinaraStabilizerServer
  - Maintains Miniconf connection to broker
  - Calculates IIR coefficients from embedded FilterLibrary
  - Constructs Raw or PID payloads
  - Applies filters / PID to stabilizer
  - Updates stream target if needed

          |
          v

Sinara Stabilizer (Dual IIR FPGA board)
  - Executes Raw biquad or PID filters
  - Responds to Miniconf namespace commands
  - Outputs analog signals to hardware

## Flow Explanation

1. **GUI → Server**  
   - User selects a filter (from `FilterLibrary`) or sets PID gains.  
   - GUI sends parameters via RPC to the server.

2. **Server computation**  
   - Computes biquad coefficients if a filter is selected.  
   - Wraps PID gains into correct payload format.  
   - Enforces offsets, voltage limits, and other safety parameters.

3. **Server → Stabilizer**  
   - Sends payloads over Miniconf/MQTT to the stabilizer.  
   - Starts or updates the channels (Raw or PID).  
   - Can also set the stream target (e.g., your computer for monitoring).

4. **Stabilizer**  
   - Executes the filters and PID loops in FPGA.  
   - Outputs resulting signals to hardware.  
   - Reports state back via Miniconf if queried.

## Key Points

- **Hands-off Operation:** After launch, the server requires no manual intervention. All changes come from the GUI.  
- **Safety & Correctness:** The server enforces voltage limits, valid biquad structures, and proper hold/run logic.  
- **Plug-and-play:** Simply start the server, connect the GUI, and control your stabilizer.  
- **Filter Library Embedded:** The server computes filter coefficients internally, so no separate Python filter files are required.

## Dependencies

- Python 3.11+  
- `asyncio`, `anyio`  
- `miniconf` (for Miniconf/MQTT communication)  
- `rockdove` (RPC backend)  
- `numpy`, `scipy`, `sympy` (for filter computation)  

## Usage

1. **Launch the server:**
python server.py --parameters_file=config.json --broker=192.168.1.222 --prefix=dt/sinara/dual-iir/<stabilizer_name> --channel=0

2. **Connect GUI**  
   - Open the PyQt5 applet and connect to the running server.  
   - Use the GUI to select filters, PID gains, or set streaming targets.  

3. **Server automatically applies commands**  
   - Filters or PID loops are applied immediately.  
   - Streaming target is updated if configured.  

## Notes

- Only two biquad IIR filters per channel are supported.  
- `Raw` and `PID` modes are handled with appropriate hold/reload/run sequence for safe operation.  
- GUI is the sole interface for controlling the stabilizer; server does not modify filters or gains autonomously.