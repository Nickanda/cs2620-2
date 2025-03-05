# CS2620 Design Exercise 3

## Installation

Our project uses only libraries that are included in the default Python installation. Importantly, we rely on the following:

- `socket` for socket handling
- `threading` for parallel processing of the three machines that we are simulating
- `unittest` for our unit tests

This was run on the Python 3.11.0, but should be compatible with Python versions 3.10.0 and above.

## Running the Project

This repository contains two main scripts for simulating and analyzing a distributed system that implements Lamport-style logical clocks. The system consists of multiple Virtual Machines (VMs) that communicate over TCP and maintain independent logical clocks.

- **`main.py`**: Runs the simulation of three virtual machines that communicate using logical clocks.
- **`analyze.py`**: Automates running multiple simulation experiments with varying parameters and analyzes the resulting logs.

---

## `main.py`: Running the Simulation
### Description
`main.py` starts a distributed system simulation where three Virtual Machines (VMs) operate independently with logical clocks. Each VM:
- Maintains a **logical clock** that updates based on Lamport's clock synchronization rules.
- Performs either an **internal event** (increments its logical clock) or a **message send event** (sends its logical clock to peers).
- Receives messages from other VMs and updates its logical clock accordingly.
- Logs all events to a log file.

### Inputs
`main.py` takes command-line arguments to control various parameters of the simulation:

#### Required Arguments
- `--run_time <int>`: Duration of the simulation in seconds.
- `--log_dir <str>`: Directory where log files will be stored.

#### Optional Arguments
- `--variation_mode <str>`: Determines the clock rate variation for VMs:
  - `order`: Clock rates vary from **1 to 6** ticks per second.
  - `small`: Clock rates vary from **2 to 3** ticks per second.
  - `medium`: Clock rates vary from **1 to 4** ticks per second.
- `--internal_prob <float>`: Probability (between 0 and 1) that an event is internal rather than a message send event.
- `--port_offset <int>`: Adjusts base port numbers to prevent conflicts when running parallel simulations.

### Example Usage
```bash
python main.py --run_time 60 --log_dir logs --variation_mode order --internal_prob 0.7


## Credits

This project is created by Nicholas Yang and Victoria Li. Portions of the code is created from generative AI, but may be modified. An exhaustive list of where this code can be found is listed here:

- Within our unit and integration tests
- Design of the virtual machine class
