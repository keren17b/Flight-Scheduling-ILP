# Flight Connection Graph

## Goal
Build a directed graph that represents which flights can legally follow other flights.

## Input
We use two CSV files:

1. **Airports / Bases file**
   - Airport code
   - Whether the airport is a crew base / hub

2. **Flights file**
   - `leg_nb` — flight ID
   - `airport_dep` — departure airport
   - `date_dep` — departure date
   - `hour_dep` — departure time
   - `airport_arr` — arrival airport
   - `date_arr` — arrival date
   - `hour_arr` — arrival time

## Data Objects

### Airport
Each airport is created once and reused by all flights.

Fields:
- `port_name`
- `is_crew_base`

### Flight
Each CSV flight row becomes one `Flight` object.

Fields:
- `flight_id`
- `origin: Airport`
- `destination: Airport`
- `departure_datetime`
- `arrival_datetime`

## Graph Construction

Each **Flight is a node**.

A directed edge:

`F1 -> F2`

exists when `F2` can legally follow `F1`.

Current connection rules:

1. `F1.destination == F2.origin`
2. `F2` departs after `F1` arrives
3. Connection time is between the configured minimum and maximum  
   (currently 30 minutes to 8 hours)

The graph is stored as an adjacency list:

```python
Flight -> [possible_next_flights]
```

Example:

```text
F1 -> [F2, F3]
F2 -> [F4]
F3 -> []
```

## Important Distinction

The graph checks only whether **two consecutive flights can connect**.

It does **not** guarantee that a full sequence of flights is a legal Duty.

Duty legality is checked later when generating Duties from this graph.

## Duty Generation

Duty generation is implemented in `duties.py`. It receives the adjacency list
created by `graph.py` and uses depth-first search (DFS) to enumerate feasible
ordered sequences of flights.

### Duty Data Object

Each generated `Duty` stores:

- `flights` - the ordered tuple of flights in the duty
- `total_time` - the elapsed time from the first flight's departure until the
  last flight's arrival, including connection time between flights

### Duty Rules

A generated duty must satisfy all of the following rules:

1. The first flight departs from an airport marked as a crew base.
2. Every following flight is a successor of the current flight in the flight
   connection graph.
3. Total duty time does not exceed `MAX_DUTY_TIME`, currently 12 hours.
4. The number of flights does not exceed `MAX_FLIGHTS_PER_DUTY`, currently 5.
5. A flight cannot appear twice in the same duty.

Every non-empty valid DFS prefix is stored as a candidate duty. DFS stops
expanding a path as soon as it reaches the flight-count limit. A possible next
flight is skipped when adding it would exceed the duty-time limit.

### Duty API

`generate_duties(graph, ...)` generates duties from an existing flight graph.

`load_duties(flights_csv_path, hubs_csv_path, ...)` calls
`load_flight_network(...)` and then generates duties from the returned graph.

## Current Pipeline

```text
CSV files
   ↓
Airport objects
   ↓
Flight objects
   ↓
Flight Connection Graph
   ↓
Duty Generation
   ↓
Pairing Generation
```
