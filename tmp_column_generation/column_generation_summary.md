# Column Generation for the Flight Scheduling / Crew Pairing Project

## 1. Why Column Generation Is Needed

The current approach generates all valid pairings first and then gives all of them to the optimization solver.

In the project, this can easily lead to millions of pairings. For example, if there are about 14 million pairings and about 1,000 flights, building a dense pairing-flight matrix becomes extremely expensive in memory.

Even if the matrix is stored sparsely, a full ILP with millions of binary variables is still very large.

Column Generation avoids this by **not generating all pairings in advance**.

Instead:

1. Start with a small subset of valid pairings.
2. Solve the optimization problem using only those pairings.
3. Use the LP dual values to identify promising new pairings.
4. Generate only pairings that can improve the current solution.
5. Add them to the model.
6. Solve again.
7. Repeat until no improving pairing can be found.

---

## 2. What Is the Master Problem?

The **Master Problem** is not a new solver.

It is the optimization model that already exists in the project.

The solver is the tool that solves the model.

For every pairing `p`, there is a decision variable:

```text
x[p]
```

In the original ILP:

```text
x[p] = 1  -> pairing p is selected
x[p] = 0  -> pairing p is not selected
```

The objective is:

```text
minimize total pairing cost
```

Mathematically:

\[
\min \sum_p c_p x_p
\]

where:

- `c_p` is the cost of pairing `p`
- `x_p` is the decision variable of pairing `p`

For every required flight `f`, there is a coverage constraint:

\[
\sum_{p: f \in p} x_p = 1
\]

This means that every required flight must be covered exactly once.

For padding flights, the project may instead use:

\[
\sum_{p: f \in p} x_p \leq 1
\]

So the existing optimization model is already the Master Problem.

The main change in Column Generation is that the Master Problem initially receives only a small subset of all possible pairings.

---

## 3. What Does `x` Represent?

Suppose there are three pairings:

```text
P1 = [F1, F2]
P2 = [F2, F3]
P3 = [F1, F3]
```

Then the optimization model contains:

```text
x1 -> variable for P1
x2 -> variable for P2
x3 -> variable for P3
```

In the final ILP:

```text
x1, x2, x3 ∈ {0, 1}
```

For example:

```text
x1 = 1
```

means that `P1` is selected.

---

## 4. Why the Master Is Solved as an LP During Column Generation

During Column Generation, the Master Problem is temporarily solved as a **continuous LP relaxation**.

Instead of:

\[
x_p \in \{0,1\}
\]

we use:

\[
0 \leq x_p \leq 1
\]

For example, the LP may return:

```text
x1 = 0.4
x2 = 0.6
```

This does **not** represent a probability.

It also does **not** mean that only 40% of the flights inside the pairing are used.

If a pairing contains:

```text
P1 = [F1, F2, F3]
```

and:

```text
x1 = 0.4
```

then `P1` contributes `0.4` to the coverage of every flight in that pairing:

```text
F1: +0.4
F2: +0.4
F3: +0.4
```

For example, if flight `F1` is covered by three pairings with:

```text
x1 = 0.4
x2 = 0.3
x3 = 0.3
```

then:

\[
0.4 + 0.3 + 0.3 = 1
\]

and the LP considers the flight fully covered.

If instead:

\[
0.4 + 0.2 + 0.1 = 0.7
\]

then the constraint is violated.

The fractional solution is only used as an intermediate mathematical tool. It is not the final crew scheduling solution.

---

## 5. What Is a Dual Value?

A dual value belongs to a **constraint**.

In this project there is one main coverage constraint per flight, so it is convenient to say:

```text
dual of flight F1
```

although technically it means:

```text
dual of the coverage constraint associated with flight F1
```

For example:

\[
x_1 + x_3 = 1
\]

may be the coverage constraint for flight `F1`.

After solving the LP, the solver may return:

```text
dual(F1) = 10
dual(F2) = 4
dual(F3) = 7
```

The dual values are obtained **after** solving the LP.

The order is:

```text
build Master Problem
        ↓
solve LP
        ↓
read dual values
```

The solver computes these values automatically.

---

## 6. Intuition Behind a High Dual Value

A high dual value often indicates that a flight is currently expensive or difficult to cover within the current restricted Master Problem.

This does not necessarily mean that the flight appears in only a few pairings.

A flight can receive a high dual value because:

- very few current pairings cover it
- the pairings that cover it are expensive
- the available pairings combine badly with the rest of the schedule
- satisfying its coverage constraint strongly affects the current LP objective

A useful intuition is:

> A high dual means that finding a good new pairing that covers this flight may be valuable.

---

## 7. Reduced Cost

The dual values are used in the Pricing Problem.

For a new candidate pairing `p`, the reduced cost is approximately:

\[
\bar{c}_p = c_p - \sum_{f \in p} \pi_f
\]

where:

- `c_p` is the real cost of the pairing
- `\pi_f` is the dual value of flight `f`

Example:

```text
dual(F1) = 20
dual(F2) = 3
dual(F3) = 5
```

Candidate pairing:

```text
Pnew = [F1, F2, F3]
cost = 25
```

Then:

\[
25 - (20 + 3 + 5) = -3
\]

The reduced cost is negative.

For a minimization problem, a negative reduced cost means that the pairing can potentially improve the current LP solution.

Therefore it should be added to the Master Problem.

---

## 8. What Is the Pricing Problem?

The Pricing Problem is the part that generates new pairings after the Master has been solved.

It receives the dual values from the current Master solution and searches the duty graph for a valid pairing with negative reduced cost.

In this project, a pairing must satisfy operational constraints such as:

- start at a crew base / hub
- end at the same required crew base / hub
- valid duty transitions
- airport continuity
- required rest
- maximum pairing duration
- maximum number of duties
- any other project-specific legality rules

The Pricing Problem should **not** regenerate all pairings.

Instead, it should search for one or several promising pairings.

---

## 9. DFS in Column Generation

The existing pairing generation is based on DFS over the duty graph.

In the original implementation, DFS explores the graph and stores all valid pairings.

With Column Generation, the search should become more selective.

Instead of:

```text
generate every valid pairing
```

the goal becomes:

```text
find a valid pairing with negative reduced cost
```

DFS can still be used, especially for a first implementation.

However, it should be combined with pruning.

---

## 10. What Is Pruning?

Pruning means stopping the exploration of a DFS branch when it is already clear that continuing that branch is useless.

Examples of pruning conditions:

- maximum number of duties reached
- maximum pairing duration exceeded
- invalid airport continuity
- insufficient rest
- repeated duty that is not allowed
- any other feasibility constraint

Example:

```python
if len(path) >= MAX_DUTIES_PER_PAIRING:
    return

if pairing_time(path) > MAX_PAIRING_TIME:
    return
```

Later, pruning can also use reduced-cost bounds.

For example, if it can be proven that even the best possible continuation of the current partial path cannot produce a negative reduced cost, that branch can be stopped.

---

## 11. Full Column Generation Flow

The complete flow discussed for this project is:

```text
Flights
  ↓
Generate duties
  ↓
Build duty graph
  ↓
Generate a small initial set of valid pairings
  ↓
Build Restricted Master Problem
  ↓
Solve LP relaxation
  ↓
Read dual value for each flight constraint
  ↓
Run Pricing Problem on the duty graph
  ↓
Find pairing(s) with negative reduced cost
  ↓
Add them to the Master
  ↓
Solve again
  ↓
Repeat
```

The loop stops when the Pricing Problem cannot find any new pairing with negative reduced cost.

At that point, the LP Column Generation process is finished.

---

## 12. Final Integer Solution

The fractional LP solution is not the final crew pairing solution.

After Column Generation has generated a useful set of columns, solve the final model again with binary variables:

\[
x_p \in \{0,1\}
\]

This produces the actual final selection of pairings.

In practice, full exact integer Column Generation requires Branch-and-Price.

For this project, a simpler practical approach is:

1. Run Column Generation on the LP.
2. Keep all pairings generated during the process.
3. Solve a final binary ILP using only those generated pairings.

This does not necessarily provide the theoretical guarantees of full Branch-and-Price, but it is much simpler to implement.

---

## 13. Artificial Variables

A useful initialization technique is to add an artificial variable for every required flight.

For flight `F7`, the coverage constraint could be:

\[
\sum_{p: F7 \in p} x_p + a_{F7} = 1
\]

where:

```text
a_F7 = artificial variable
```

The artificial variable receives a very large cost.

For example:

```text
ARTIFICIAL_COST = 1_000_000
```

The purpose is to ensure that the Restricted Master Problem is always feasible, even if the initial pairing set cannot cover all flights.

The solver strongly prefers real pairings because the artificial variables are expensive.

As Column Generation finds better real pairings, the artificial variables should move toward zero.

If artificial variables are still positive at the end, this is a warning that the generated real pairings are not sufficient to cover all required flights.

---

## 14. Important Distinction: Initial Pairing Generation vs Pricing

These are two different stages.

### Initial Pairing Generation

The goal is:

```text
create a small valid starting pool
```

It does not use dual values yet.

Possible strategy:

- run a limited DFS
- keep only a bounded number of pairings
- prefer pairings that cover flights that currently have little or no initial coverage
- stop after enough initial pairings have been collected
- rely on artificial variables for remaining uncovered flights

### Pricing

The goal is:

```text
find pairings with negative reduced cost
```

It uses the dual values from the latest Master LP.

So the implementation should ideally have two separate functions:

```python
generate_initial_pairings(...)
```

and:

```python
generate_pricing_pairings(graph, duals, ...)
```

---

## 15. Suggested High-Level Structure

```python
initial_pairings = generate_initial_pairings(
    duty_graph,
    flights,
)

columns = initial_pairings

while True:
    solution, duals = solve_master_lp(
        columns,
        flights,
    )

    new_pairings = generate_pricing_pairings(
        duty_graph,
        duals,
    )

    improving = [
        p for p in new_pairings
        if p.reduced_cost < 0
    ]

    if not improving:
        break

    columns.extend(improving)

final_solution = solve_final_binary_master(
    columns,
    flights,
)
```

This structure separates the responsibilities clearly:

- initial pairing generation
- Master LP
- dual extraction
- Pricing Problem
- final binary solve

---

## 16. Main Idea in One Sentence

> Column Generation avoids generating millions of pairings in advance by repeatedly solving a smaller Master Problem and generating only new pairings that can improve the current solution.
