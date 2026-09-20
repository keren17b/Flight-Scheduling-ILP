# Initial Pairings for Column Generation

## 1. Why Initial Pairings Are Needed

Column Generation does not begin with all possible pairings.

It starts with a small set of valid pairings called the **initial columns**.

In this project, a duty cannot automatically be used as a pairing because:

- a pairing must start at a hub / crew base
- a pairing must end at a valid hub / crew base
- a single duty may not satisfy both conditions

Therefore the initial columns must be actual valid pairings, not just duties.

---

## 2. Main Idea

Use the existing duty graph and run a **limited DFS**.

The goal is not to generate all valid pairings.

The goal is to generate a small useful initial pool.

While generating pairings, keep track of which flights already have initial coverage.

For example:

```python
coverage_count = {
    flight_id: 0
    for flight_id in all_flight_ids
}
```

If a pairing covers:

```text
F1, F2, F3
```

update:

```text
F1 -> +1
F2 -> +1
F3 -> +1
```

---

## 3. Why Keep a Coverage Dictionary?

Suppose the current state is:

```text
F1 -> 1
F2 -> 1
F3 -> 1
F4 -> 0
```

If DFS finds a new pairing:

```text
[F1, F2]
```

it does not help with any currently uncovered flight.

If the goal is only to create a small initial pool, we may skip it.

If DFS finds:

```text
[F2, F4]
```

it is useful because `F4` currently has no initial coverage.

This helps avoid generating thousands of redundant initial pairings.

---

## 4. Recommended Stopping Conditions

Do not stop only when every flight is covered.

Some flights may not be reachable by the current DFS search before the search becomes too large.

The initial DFS should stop when one of the following happens:

1. Every required flight has reached the desired minimum initial coverage.
2. The number of generated initial pairings reaches `MAX_INITIAL_PAIRINGS`.
3. The DFS naturally exhausts all valid branches.

Example:

```python
MAX_INITIAL_PAIRINGS = 5000
MIN_INITIAL_COVERAGE = 1
```

---

## 5. Flights That Remain Uncovered

After the initial DFS finishes:

```python
uncovered_flights = [
    flight_id
    for flight_id, count in coverage_count.items()
    if count == 0
]
```

These flights do not necessarily have no valid pairing.

There are two possibilities:

### Case A: DFS exhausted all possibilities

Then the flight may truly have no valid pairing under the current model constraints.

### Case B: DFS stopped because of the pairing limit

Then the flight may still have a valid pairing that was simply not reached.

Therefore the initial stage should not depend on full coverage.

---

## 6. Artificial Variables

To guarantee that the first Master Problem is feasible, add an artificial variable for every required flight.

For flight `f`:

\[
\sum_{p: f \in p} x_p + a_f = 1
\]

where:

```text
a_f
```

is an artificial variable.

Give it a very high cost:

```python
ARTIFICIAL_COST = 1_000_000
```

This means:

- the Master can always satisfy the coverage constraint
- real pairings are preferred
- Pricing can later introduce better real pairings
- artificial variables should disappear from the final solution if enough valid pairings are generated

It is safer to add artificial variables for **all required flights**, not only uncovered flights.

The reason is that even if every flight appears in at least one initial pairing, the initial pairings may still be mutually incompatible under exact-cover constraints.

Example:

```text
P1 = [F1, F2]
P2 = [F2, F3]
```

Every flight appears somewhere, but selecting both causes `F2` to be covered twice.

Artificial variables guarantee feasibility regardless of this interaction.

---

## 7. Suggested DFS Skeleton

```python
def generate_initial_pairings(
    graph,
    all_flight_ids,
    max_pairing_time,
    max_duties,
    min_cover_per_flight=1,
    max_pairings=5000,
):
    pairings = {}

    coverage_count = {
        flight_id: 0
        for flight_id in all_flight_ids
    }

    def pairing_flight_ids(path):
        covered = set()

        for duty in path:
            for flight in duty.flights:
                covered.add(flight.flight_id)

        return covered

    def enough_coverage():
        return all(
            count >= min_cover_per_flight
            for count in coverage_count.values()
        )

    def dfs(current_duty, path):
        # Stop if enough initial pairings were already generated
        if len(pairings) >= max_pairings:
            return

        # Stop if every flight already has enough initial coverage
        if enough_coverage():
            return

        # Check whether this path forms a valid pairing
        returned_to_base = (
            current_duty.end_airport.is_crew_base
            and current_duty.end_airport.port_name
            == path[0].start_airport.port_name
        )

        if returned_to_base:
            covered = pairing_flight_ids(path)

            # Keep this pairing only if it helps a flight
            # that still needs initial coverage
            useful = any(
                coverage_count[flight_id] < min_cover_per_flight
                for flight_id in covered
            )

            if useful:
                pairing_id = f"P{len(pairings) + 1}"

                pairings[pairing_id] = build_pairing_from_path(
                    pairing_id,
                    path,
                )

                for flight_id in covered:
                    coverage_count[flight_id] += 1

        # Pruning: maximum number of duties
        if len(path) >= max_duties:
            return

        # Continue DFS through valid next duties
        for next_duty in graph.get(current_duty, []):
            if next_duty in path:
                continue

            total_time = (
                next_duty.end_time
                - path[0].start_time
            )

            # Pruning: maximum pairing duration
            if total_time > max_pairing_time:
                continue

            path.append(next_duty)

            dfs(
                next_duty,
                path,
            )

            path.pop()

            # Global stopping conditions
            if enough_coverage():
                return

            if len(pairings) >= max_pairings:
                return

    # Start DFS only from duties that begin at a crew base
    for first_duty in graph:
        if enough_coverage():
            break

        if len(pairings) >= max_pairings:
            break

        if not first_duty.start_airport.is_crew_base:
            continue

        dfs(
            first_duty,
            [first_duty],
        )

    return pairings, coverage_count
```

---

## 8. Notes About the Skeleton

The helper:

```python
build_pairing_from_path(...)
```

is only a placeholder.

In the project, this should contain the existing logic that constructs a `Pairing` object, including:

- duties
- total time
- flight time
- sitting time
- rest
- pairing ID
- any other current fields

The existing pairing legality rules should remain unchanged.

The initial DFS should only change **how many pairings are stored** and **when the search stops**.

---

## 9. Better Variant: Allow More Than One Initial Cover per Flight

Instead of:

```python
MIN_INITIAL_COVERAGE = 1
```

it may be useful to use:

```python
MIN_INITIAL_COVERAGE = 2
```

or another small number.

This gives the first Master LP some alternatives.

The tradeoff is:

- more initial pairings
- potentially better initial LP
- slightly more work before Column Generation starts

A reasonable implementation can make this configurable.

---

## 10. Important Limitation of the Coverage Dictionary

The dictionary only tells us:

```text
how many initial pairings contain each flight
```

It does **not** prove that all flights can be covered simultaneously.

For example:

```text
P1 = [F1, F2]
P2 = [F2, F3]
```

Coverage count may be:

```text
F1 -> 1
F2 -> 2
F3 -> 1
```

but there is no exact-cover solution using both pairings because `F2` would be covered twice.

This is why artificial variables are useful even when every flight has nonzero coverage.

---

## 11. Suggested Overall Initialization Flow

```text
Build duty graph
      ↓
Run limited DFS
      ↓
Collect a small set of valid pairings
      ↓
Maintain coverage_count
      ↓
Stop when:
    - enough coverage, OR
    - max pairings reached, OR
    - DFS exhausted
      ↓
Build Restricted Master Problem
      ↓
Add artificial variable for each required flight
      ↓
Solve LP
      ↓
Read duals
      ↓
Start Pricing iterations
```

---

## 12. Difference Between Initial DFS and Pricing DFS

The initial DFS asks:

> Can I build a small useful starting pool of valid pairings?

The Pricing DFS asks:

> Using the current dual values, can I find a valid pairing with negative reduced cost?

These should be separate functions.

Suggested structure:

```python
initial_pairings = generate_initial_pairings(
    duty_graph,
    flights,
)

while True:
    solution, duals = solve_master_lp(
        initial_pairings,
        flights,
    )

    new_pairings = generate_pricing_pairings(
        duty_graph,
        duals,
    )

    if not new_pairings:
        break

    initial_pairings.extend(new_pairings)
```

---

## 13. Main Idea in One Sentence

> Generate only a small number of valid starting pairings with a limited DFS, track flight coverage, stop before the search explodes, and rely on expensive artificial variables to keep the first Master Problem feasible.
