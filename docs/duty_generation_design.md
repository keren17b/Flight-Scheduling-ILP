# Duty Generation Design

## 1. Duty Class

Each duty should be represented as an object containing an ordered list of `Flight` objects.

```python
class Duty:
    def __init__(self, duty_id, flights):
        self.duty_id = duty_id
        self.flights = flights

        self.start_airport = flights[0].origin
        self.end_airport = flights[-1].destination
        self.start_time = flights[0].departure_datetime
        self.end_time = flights[-1].arrival_datetime
```

The order of the flights in `flights` represents the chronological order of the duty.

A Python `list` is preferred over a linked list because it is simpler to iterate over, access, copy, and extend during DFS.

## 2. How DFS Should Generate Duties

The DFS runs on the flight connection graph.

During the search, it maintains the current sequence of flights, for example:

```text
[F1]
[F1, F2]
[F1, F2, F3]
[F1, F2, F3, F4]
```

Every time the current sequence satisfies all duty constraints, it should be saved as a separate `Duty`.

For example, if all of these sequences are legal:

```text
[F1, F2]
[F1, F2, F3]
[F1, F2, F3, F4]
```

then all three should be saved as different duties.

The DFS should not wait until it reaches the longest path and then generate shorter sub-sequences afterward. It should save each legal sequence while traversing the graph and continue extending it as long as further extensions are possible.

Conceptually:

```python
def dfs(current_path):
    if is_legal_duty(current_path):
        save_duty(current_path.copy())

    for next_flight in possible_next_flights:
        if can_extend(current_path, next_flight):
            dfs(current_path + [next_flight])
```

A legal duty may contain a single flight unless the project explicitly defines a different rule.

## 3. Output of the Duty Generation Step

The DFS module should output a collection of `Duty` objects.

Recommended format:

```python
duties = {
    "D1": Duty("D1", [F1, F2]),
    "D2": Duty("D2", [F1, F2, F3]),
    "D3": Duty("D3", [F4]),
}
```

A dictionary indexed by `duty_id` is convenient because the next pipeline step can use these IDs when building the duty connection graph.

Pipeline:

```text
Flight Graph
    |
    v
DFS Duty Generation
    |
    v
Dictionary of Duty Objects
    |
    v
Duty Connection Graph
    |
    v
Pairing Generation
```
