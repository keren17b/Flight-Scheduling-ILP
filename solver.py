from mosek.fusion import Model, Domain, Expr, ObjectiveSense
import numpy as np


def simple_model(mat, cost_lst):
    mat = np.array(mat)

    num_pairings = mat.shape[0]
    num_flights = mat.shape[1]

    with Model("flight_model") as M:

        # x[i] = 1 if pairing i is selected
        x = M.variable("x", num_pairings, Domain.binary())

        # Objective: minimize costs
        M.objective(
            "minimize_cost",
            ObjectiveSense.Minimize,
            Expr.dot(cost_lst, x)
        )

        # Constraint: each flight is covered exactly once
        for j in range(num_flights):
            M.constraint(
                f"flight_{j}_covered_once",
                Expr.dot(mat[:, j].tolist(), x),
                Domain.equalsTo(1.0)
            )

        # Important: solve inside the with block
        M.solve()

        # Important: read the solution inside the with block as well
        solution = x.level()

        print("Selected pairings:")

        total_cost = 0

        for i in range(num_pairings):
            if solution[i] > 0.5:
                print(f"we took pairing {i}, cost = {cost_lst[i]}")
                total_cost += cost_lst[i]
            

        return solution, total_cost 


if __name__ == "__main__":
    mat5 = np.array([
        [1, 1, 0, 0, 0],  # pairing 0
        [0, 0, 1, 1, 0],  # pairing 1
        [0, 0, 0, 0, 1],  # pairing 2
        [1, 0, 1, 0, 0],  # pairing 3
        [0, 1, 0, 1, 1],  # pairing 4
    ])

    costs5 = [8, 7, 3, 9, 10]
    import numpy as np

    mat10 = np.array([
    [1, 1, 0, 0, 0, 0, 0, 0, 0, 0],  # pairing 0
    [0, 0, 1, 1, 0, 0, 0, 0, 0, 0],  # pairing 1
    [0, 0, 0, 0, 1, 1, 0, 0, 0, 0],  # pairing 2
    [0, 0, 0, 0, 0, 0, 1, 1, 0, 0],  # pairing 3
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 1],  # pairing 4

    [1, 0, 1, 0, 0, 0, 0, 0, 0, 0],  # pairing 5
    [0, 1, 0, 1, 0, 0, 0, 0, 0, 0],  # pairing 6
    [0, 0, 0, 0, 1, 0, 1, 0, 0, 0],  # pairing 7
    [0, 0, 0, 0, 0, 1, 0, 1, 0, 0],  # pairing 8
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0],  # pairing 9
])

    costs10 = [6, 7, 5, 8, 4, 9, 9, 6, 6, 3]

    simple_model(mat10, costs10)


