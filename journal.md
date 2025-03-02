# Coding Project Journal

## Link to Project

https://github.com/Nickanda/cs2620

## Table of Contents

- [Coding Project Journal](#coding-project-journal)
  - [Table of Contents](#table-of-contents)
  - [Development Log](#development-log)
    - [February 28, 2025](#february-28-2025)
      - [Progress](#progress)
      - [Issues Encountered](#issues-encountered)
    - [Next Steps](#next-steps)

## Development Log

### February 28, 2025

#### Progress

- Implemented the simulation for the concurrent processes problem using asynchronous virtual machines.
- Developed a Python-based model that simulates a distributed system with multiple virtual machines, each running at its own clock rate and maintaining its own logical clock.
- Integrated socket-based communication to allow virtual machines to exchange messages and update their logical clocks using Lamport’s algorithm.
- Added detailed logging to capture system time, event types (send, receive, internal), logical clock updates, and message queue lengths for subsequent analysis.
- Conducted initial tests to observe clock drift, message queue behavior, and the impact of varied clock speeds on event ordering.

#### Issues Encountered

- Faced synchronization challenges with establishing and maintaining concurrent socket connections between processes.
- Noticed occasional discrepancies in logical clock updates during high-frequency message passing, necessitating further refinements.
- Experienced intermittent buffering issues with message packets that required adjustments in the network communication handling.
- Encountered unexpected delays in processing messages under certain clock rate conditions, prompting additional debugging and performance tuning.

[Back to Table of Contents](#table-of-contents)

---

### Next Steps

- Refine the logical clock update mechanism to ensure accurate and consistent event ordering under concurrent loads.
- Enhance error handling and buffering strategies for the socket connections to improve message reliability.
- Conduct more extensive testing with varied clock rate parameters to further analyze clock drift and network queue behaviors.
- Prepare a comprehensive demo and documentation that details the design decisions, challenges, and performance observations of the concurrent processes simulation.
- Explore the potential integration of more efficient communication protocols such as gRPC to optimize inter-process messaging.
