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
 Pairing-Flight Matrix
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
- flight_time
- sitting_time
- start_airport
- end_airport
- start_time
- end_time
```

`flight_time` is the sum of the scheduled duration of every flight in the duty.

`sitting_time` is the total connection wait between flights inside the duty. A single-flight duty has `sitting_time = 0`.

The stored components satisfy `total_time = flight_time + sitting_time`.

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
- flight_time
- sitting_time
- rest
- start_airport
- end_airport
- start_time
- end_time
```

`flight_time` and `sitting_time` are the sums of those values across every duty in the pairing.

`rest` is the total layover time between consecutive duties in the pairing:

```text
rest = Σ (duty[i+1].start_time - duty[i].end_time)
```

A pairing with a single duty has `rest = 0`.

The stored components satisfy `total_time = flight_time + sitting_time + rest`.

---

# 6. Cost Calculation

Pairing cost is a number of hours:

```text
cost = (rest + Σ sitting_time of every duty in the pairing) in hours
```

That is:

- `rest` is the total layover time between consecutive duties.
- `sitting_time` of a duty is the total connection wait between flights inside that duty.
- `cost` is that sum converted to hours, not a clock time.

The pairing stores the time components, not a fixed cost. The default
`current_pairing_cost(pairing)` function in `pairing_cost.py` implements this
formula. A different function can use the same pairing data to define another
cost model without regenerating pairings.

---

# 7. Pairing-Flight Matrix

File: `pairing_to_metrix.py`

Input:

```text
flights  – Dict[str, Flight] from load_flight_network
pairings – Dict[str, Pairing] from generate_pairings
```

Output:

```text
Binary Pairing-Flight Matrix
Cost List
```

The function `pairings_to_matrix(flights, pairings, cost_function)` builds the
two objects that `solver.py` expects. `cost_function` defaults to
`current_pairing_cost`.

## Matrix Structure

```text
Row    = Pairing  (dict order of pairings)
Column = Flight   (dict order of flights)
```

The matrix is binary:

```text
matrix[i][j] = 1  if pairing i contains flight j
matrix[i][j] = 0  otherwise
```

A pairing contains a flight when that flight appears in any duty of the pairing:

```text
for each pairing
    for each duty in pairing.duties
        for each flight in duty.flights
            matrix[pairing_row][flight_column] = 1
```

## Cost List

`costs[i]` is `cost_function(pairing)` for the pairing in row `i`. The row order
of the matrix and the order of the cost list match, so they can be passed
together to the Solver:

```python
matrix, costs = pairings_to_matrix(flights, pairings)
solution, total_cost = simple_model(matrix, costs)
```

The output types are:

```python
matrix: np.ndarray   # shape (num_pairings, num_flights), values in {0, 1}
costs:  List[float]  # length num_pairings
```

---

# 8. Optimization Solver

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
5. Returns the solution vector and the total cost.

The Solver input is produced by `pairing_to_metrix.py`:

```text
Pairing-Flight Matrix
+
Cost List
```

The output is:

```text
Optimal Pairing Set
```

---

# Column Generation

Full pairing DFS can produce millions of pairings. Building the dense pairing-flight matrix and one binary variable per pairing then runs out of memory.

Column generation does not generate every pairing first. It starts from a small pool, solves a smaller LP, and later adds only pairings that can improve that LP.

`generate_pairings` is still in `pairings.py`. The column-generation path is additional.

What is implemented so far:

1. A limited initial pairing pool.
2. A restricted master LP that returns flight duals.

Pricing and the loop that adds new pairings are not implemented yet. `main_tmp.py` still runs the full pairing DFS and `simple_model`.

## Initial pairing pool

File: `pairings.py`

Function: `generate_initial_pairings`

Input:

```text
Duty Graph
Flight IDs to track
```

Output:

```text
Small Dict[str, Pairing]
coverage_count for those flight IDs
```

The search uses the same pairing rules as `generate_pairings`:

- DFS starts only from a duty that departs a crew base.
- A pairing is saved only when it returns to that same crew base.
- A duty is not repeated in one pairing.
- At most `MAX_DUTIES_PER_PAIRING` duties (5).
- Total time at most `MAX_PAIRING_TIME` (5 days), including rest between duties.

It does not store every legal path. A closed pairing is kept only when it covers at least one tracked flight that is still below `MIN_INITIAL_COVERAGE` (1). Each kept pairing increments `coverage_count` for the flights it covers.

The search stops when one of these happens:

1. Every tracked flight has reached `MIN_INITIAL_COVERAGE`.
2. The pool reaches `MAX_INITIAL_PAIRINGS` (5000).
3. DFS has no remaining legal branches.

`build_pairing_from_path` builds the `Pairing` object. Both `generate_pairings` and `generate_initial_pairings` use it.

## Restricted Master LP

File: `master_lp.py`

Function: `solve_master_lp`

Input:

```text
Current pairings
flights
cost function (default: current_pairing_cost)
```

Output: `MasterLpResult`

```text
pairing_values      x[p] for each current pairing
duals               one dual per flight constraint
objective           LP objective value
artificial_values   leftover coverage for each required flight
```

This LP is not the final binary model in `solver.py`.

For each current pairing `p`:

```text
0 <= x[p] <= 1
```

`x[p]` can be fractional. It is only an intermediate value used to obtain duals.

Coverage is built from the flight IDs inside each pairing. The dense pairing-flight matrix is not built.

Required flights, from `padding_flights.py`, use exact cover plus an artificial variable:

```text
sum of x[p] over pairings that contain f  +  a[f]  =  1
0 <= a[f] <= 1
```

`a[f]` is the uncovered fraction of flight `f`. Its cost is `ARTIFICIAL_COST` (1,000,000), so the LP prefers real pairings.

Padding flights have no artificial variable:

```text
sum of x[p] over pairings that contain f  <=  1
```

Objective:

```text
minimize  sum(cost[p] * x[p])  +  ARTIFICIAL_COST * sum(a[f])
```

After `M.solve()`, `constraint.dual()` is stored as `duals[flight_id]`. Those duals are the input the later pricing search will use.

The function expects a non-empty pairing set and at least one required flight.

Tests for this LP are in `test_master_lp.py`.

---

# 9. Main Pipeline

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
   +--> pairing_to_metrix.py
   |
   +--> solver.py
```

The existing `main_tmp.py` is currently used as a temporary test runner for connecting the pipeline stages, including matrix construction and the Solver.

---

# 10. File Responsibilities

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
    DFS for all legal pairings (generate_pairings)
    Limited DFS for the initial column-generation pool (generate_initial_pairings)

pairing_cost.py
    Replaceable pairing cost functions

pairing_to_metrix.py
    Pairing-flight binary matrix
    Pairing cost list calculated by the selected cost function

master_lp.py
    Restricted master LP for column generation
    Continuous pairing variables, artificials, and flight duals

solver.py
    ILP model
    Selection of optimal pairings

main.py
    Full pipeline
```

---

# 11. Roadmap

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
8. Convert Pairings into a Pairing-Flight matrix and a cost list (`pairing_to_metrix.py`).
9. Connect Pairing generation to the existing Solver.

## Next Stages

10. Complete and define all constraints for a legal Duty.
11. Define all constraints for a legal Pairing.
12. Build the `Duty Graph`.
13. Implement the `Pairing` class.
14. Generate Pairings using DFS.
15. Define and calculate costs.
16. Run the complete pipeline.
17. Test on a small dataset.
18. Run on a large / full dataset.
19. Analyze the results.

## Optional Extensions

- Column Generation. The initial pairing pool and the restricted master LP are in place. Pricing and the column-generation loop are not implemented yet.
- Crew Scheduling – assigning specific crew members to pairings.
- Performance optimizations and pruning during duty and pairing generation.

---

# 12. Architectural Principle

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
