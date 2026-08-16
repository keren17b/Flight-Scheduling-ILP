# Project Planning and Flow – Airline Crew Pairing

## 1. Project Goal

The goal of the project is to receive flight data, generate legal `duties` and `pairings`, and then use an ILP Solver to select the optimal set of pairings so that every flight is covered exactly once.

The general pipeline is:

```text
Flight CSV + Crew Bases CSV
            |
            v
       Flight Graph
            |
            v
      Duty Generation
           DFS
            |
            v
       List of Duties
            |
            v
        Duty Graph
            |
            v
     Pairing Generation
           DFS
            |
            v
      List of Pairings
            |
            v
          Solver
            |
            v
   Optimal Pairing Set
```

---

# 2. Pipeline Stages

## Stage 1 – Load the Data and Build the Flight Graph

File: `flights_graph.py`

The input is:

```text
Flights CSV
Crew Bases CSV
```

The flights file contains, among other fields, the following information for each flight:

- Flight ID
- Departure airport
- Arrival airport
- Departure date and time
- Arrival date and time

The bases file defines which airports are `crew bases`.

### Data Structures

`Airport` represents an airport:

```python
Airport
- port_name
- is_crew_base
```

`Flight` represents a flight:

```python
Flight
- flight_id
- origin
- destination
- departure_datetime
- arrival_datetime
```

### Flight Graph

In the flight graph:

```text
Node = Flight
Edge = Legal connection between two flights
```

Example:

```text
F1 -> F2 -> F5
   \
    -> F3
```

To create an edge:

```text
F1 -> F2
```

the following conditions must be checked:

- `F1` arrives at the airport from which `F2` departs.
- `F2` departs after `F1` arrives.
- The waiting time between `F1` and `F2` is greater than or equal to the `minimum connection time`.
- The waiting time between `F1` and `F2` is less than or equal to the `maximum connection time`.

Therefore, an edge in the graph represents a legal option to perform `F2` immediately after `F1` within the same duty.

The current default values in the code are:

```text
Minimum connection time = 30 minutes
Maximum connection time = 8 hours
```

These values can be changed according to the constraints defined for the project.

The output of `flights_graph.py` is:

```python
FlightGraph = Dict[Flight, List[Flight]]
```

---

# 3. Duty Generation

File: `duties.py`

Input:

```text
Flight Graph
```

Output:

```text
Collection of legal Duty objects
```

## Duty

Each `Duty` is an ordered sequence of flights:

```text
F1 -> F2 -> F3
```

The object stores:

```python
Duty
- duty_id
- flights
- total_time
- sitting_time
- start_airport
- end_airport
- start_time
- end_time
```

`sitting_time` is the total connection wait between flights inside the duty. A single-flight duty has `sitting_time = 0`.

## Crew Base Rule

A Duty does not have to start at a crew base and does not have to end at a crew base.

DFS starts from every flight in the graph. Start and return at a crew base are pairing-level rules only.

## Generating Duties Using DFS

DFS starts from every flight in the graph and tries to continue to flights that can legally follow it.

Example:

```text
F1
 |
 +-- F2
 |    |
 |    +-- F3
 |         |
 |         +-- F4
 |
 +-- F5
```

During the search, sequences such as the following are generated:

```text
[F1]

[F1, F2]

[F1, F2, F3]

[F1, F2, F3, F4]
```

Whenever the current sequence forms a legal `Duty`, it is saved as a separate Duty.

Therefore, if the following three sequences are legal:

```text
[F1, F2]

[F1, F2, F3]

[F1, F2, F3, F4]
```

three different `Duty` objects are created.

DFS does not wait until it reaches the longest sequence and then generate shorter subsequences from it. Each legal Duty is saved during the search, and DFS then continues trying to extend it.

The output is currently stored as:

```python
Dict[str, Duty]
```

For example:

```python
{
    "D1": Duty(...),
    "D2": Duty(...),
    "D3": Duty(...)
}
```

---

# 4. Building the Duty Graph

File: `duty_graph.py`

Input:

```text
Collection of Duty objects
```

Output:

```text
Duty Graph
```

In this graph:

```text
Node = Duty
Edge = Duty2 can legally follow Duty1
```

Example:

```text
D1 -> D4 -> D8
 |
 +--> D5
```

To create an edge:

```text
D1 -> D2
```

the following conditions must be checked:

- `D1` ends at the airport where `D2` starts.
- `D2` starts after `D1` ends.
- The rest / layover time between `D1` and `D2` is greater than or equal to the minimum rest.
- The rest / layover time between `D1` and `D2` is less than or equal to the maximum layover.

The current default values in the code are:

```text
Minimum rest between duties = 10 hours   # legality / safety constraint
Maximum layover between duties = 48 hours  # modeling / pruning constraint
```

These values can be changed according to the constraints defined for the project.

The output of `duty_graph.py` is:

```python
DutyGraph = Dict[Duty, List[Duty]]
```

---

# 5. Pairing Generation

Suggested file:

```text
pairings.py
```

Input:

```text
Duty Graph
```

Output:

```text
Collection of legal Pairing objects
```

DFS will also be used at this stage.

For example:

```text
D1 -> D4 -> D8
```

may represent:

```text
Pairing
Day 1: D1
Day 2: D4
Day 3: D8
```

Unlike a single Duty, a Pairing is closed: it must start at a crew base and end at the same crew base it started from.

## Crew Base Rule

- DFS starts only from duties that depart from a crew base.
- A pairing is saved only when the last duty ends at a crew base and that airport is the same crew base the pairing started from (`end_airport.port_name == start_airport.port_name`).
- Ending at a different crew base is not enough; the pairing must return to the original base.
- After a pairing is saved, DFS continues so both a shorter pairing that already returned to that base and a longer pairing can be kept.

A Duty in the middle of a pairing may start or end at any airport, as long as consecutive duties connect at the same airport in the Duty Graph.

A `Pairing` object contains:

```python
Pairing
- pairing_id
- duties
- total_time
- rest
- start_airport
- end_airport
- start_time
- end_time
- cost
```

`rest` is the total layover time between consecutive duties in the pairing:

```text
rest = Σ (duty[i+1].start_time - duty[i].end_time)
```

A pairing with a single duty has `rest = 0`.

---

# 6. Cost Calculation

Pairing cost is:

```text
cost = rest + Σ sitting_time of every duty in the pairing
```

That is:

- `rest` is the total layover time between consecutive duties.
- `sitting_time` of a duty is the total connection wait between flights inside that duty.

The pairing cost is stored on the `Pairing` object and will be used by the Solver in the objective function.

---

# 7. Optimization Solver

File: `solver.py`

An initial implementation of the optimization stage using `MOSEK` already exists.

The Solver currently receives:

```text
Pairing-Flight Matrix
Pairing Costs
```

The matrix is structured as follows:

```text
Row    = Pairing
Column = Flight
```

The value:

```text
matrix[p][f] = 1
```

means that flight `f` is included in pairing `p`.

For example:

```text
             F1 F2 F3 F4 F5

Pairing 1     1  1  0  0  0
Pairing 2     0  0  1  1  0
Pairing 3     0  0  0  0  1
```

A binary variable is defined for each pairing:

```text
x[p] = 1  -> pairing p selected
x[p] = 0  -> pairing p not selected
```

### Objective Function

The goal is to minimize the total cost of the selected pairings:

```text
minimize Σ cost[p] * x[p]
```

### Flight Coverage Constraint

For every flight:

```text
Σ matrix[p][f] * x[p] = 1
```

That is:

```text
Every flight must be covered exactly once
```

This is a `Set Partitioning` model.

The initial implementation in `solver.py` already:

1. Creates one binary variable for each pairing.
2. Defines an objective function that minimizes total cost.
3. Adds a constraint requiring every flight to be covered exactly once.
4. Runs MOSEK.
5. Returns/prints the selected pairings and their total cost.

Currently, the data in `solver.py` is manually defined test data.

Later, the collection of `Pairing` objects generated in the previous stage will need to be automatically converted into:

```text
Pairing-Flight Matrix
+
Cost List
```

and passed to the Solver.

The future input:

```text
Legal Pairing Objects
```

will be converted into:

```text
Pairing-Flight Matrix
Pairing Costs
```

and the output will be:

```text
Optimal Pairing Set
```

---

# 8. Main Pipeline

The file:

```text
main.py
```

should not contain the internal logic for building graphs, duties, or pairings.

Its purpose is to connect the different stages:

```python
load data

build flight graph

generate duties

build duty graph

generate pairings

calculate / attach costs

build pairing-flight matrix

run solver

return solution
```

That is:

```text
main.py
   |
   +--> flights_graph.py
   |
   +--> duties.py
   |
   +--> duty_graph.py
   |
   +--> pairings.py
   |
   +--> solver.py
```

The existing `main_tmp.py` is currently used as a temporary test runner for connecting flight graph generation with duty generation.

---

# 9. File Responsibilities

The suggested project structure is:

```text
flights_graph.py
    Flight/Airport data
    CSV loading
    Flight graph creation

duties.py
    Duty representation
    Duty constraints
    DFS for duty generation

duty_graph.py
    Conversion from duties to a duty connection graph

pairings.py
    Pairing representation
    Pairing constraints
    DFS for pairing generation

solver.py
    Pairing-flight matrix
    ILP model
    Selection of optimal pairings

main.py
    Full pipeline
```

---

# 10. Roadmap

## Stages Already Decided / Started

1. Select the GERAD dataset.
2. Study methods for generating pairings.
3. Select a two-stage DFS approach:
   - Flight Graph -> Duties
   - Duty Graph -> Pairings
4. Load CSV files and convert them into `Airport` and `Flight` objects.
5. Build the Flight Graph.
6. Implement an initial Duty generation algorithm using DFS.
7. Implement an initial ILP Solver using MOSEK.

## Next Stages

8. Complete and define all constraints for a legal Duty.
9. Define all constraints for a legal Pairing.
10. Build the `Duty Graph`.
11. Implement the `Pairing` class.
12. Generate Pairings using DFS.
13. Define and calculate costs.
14. Convert Pairings into a Pairing-Flight matrix and a cost list.
15. Connect Pairing generation to the existing Solver.
16. Run the complete pipeline.
17. Test on a small dataset.
18. Run on a large / full dataset.
19. Analyze the results.

## Optional Extensions

- Column Generation to reduce the need to generate a very large number of pairings in advance.
- Crew Scheduling – assigning specific crew members to pairings.
- Performance optimizations and pruning during duty and pairing generation.

---

# 11. Architectural Principle

Each stage in the pipeline should receive a clearly defined data structure and return a clearly defined data structure, without depending on the internal implementation of the other stages.

```text
CSV
 ↓
Flight Graph
 ↓
Duties
 ↓
Duty Graph
 ↓
Pairings
 ↓
Pairing-Flight Matrix + Costs
 ↓
Optimization Model
 ↓
Solution
```

This allows every stage to be tested, modified, and improved independently.
