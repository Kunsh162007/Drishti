"""Ant Colony Optimisation (ACO) patrol unit allocation for DRISHTI.

Replaces the greedy top-N assignment with a bio-inspired swarm approach:
pheromone trails guide ants toward high-risk hexes while evaporation
prevents premature convergence, producing better coverage per unit.

Academic basis:
  Dorigo M & Gambardella LM (1997). Ant colony system: a cooperative
    learning approach to the traveling salesman problem. IEEE Trans
    Evolutionary Computation 1:53-66.
  Weisburd D et al. (2016). Place-based policing. Ideas in American
    Policing 15. Police Foundation.

Pure function. Standard library only.
"""
from __future__ import annotations

import math
import random


def aco_patrol(
    cells: list[dict],
    units: int,
    *,
    n_ants: int = 30,
    n_iter: int = 60,
    alpha: float = 1.2,   # pheromone influence
    beta: float = 2.0,    # heuristic (risk) influence
    rho: float = 0.35,    # evaporation rate
    q: float = 100.0,     # pheromone deposit constant
    seed: int = 42,
) -> list[dict]:
    """Select ``units`` patrol hexes using ACO.

    Each hex is a node; ants greedily choose nodes probabilistically
    (pheromone * risk^beta) and deposit pheromone on good solutions
    (high total risk coverage).  Pheromone evaporates each iteration.

    Args:
        cells: list of hex dicts with ``h3``, ``w`` (risk weight), ``lat``, ``lng``.
        units: number of patrol units to assign.
        n_ants, n_iter: ACO hyperparameters.
        alpha, beta: weight of pheromone vs. heuristic.
        rho: evaporation rate (0-1).
        q: pheromone deposit constant.
        seed: random seed for reproducibility.

    Returns:
        Selected cells (same dicts) sorted by risk descending, annotated with
        ``aco_rank`` and ``aco_pheromone``.
    """
    rng = random.Random(seed)

    if not cells or units <= 0:
        return []

    units = min(units, len(cells))
    risks = [max(1e-6, float(c.get("w", 0) or 0)) for c in cells]
    n = len(cells)

    # Initialise pheromone uniformly
    pheromone = [1.0] * n

    best_solution: list[int] = []
    best_score = -1.0

    for _ in range(n_iter):
        ant_solutions: list[list[int]] = []
        ant_scores: list[float] = []

        for _ant in range(n_ants):
            available = list(range(n))
            chosen: list[int] = []
            remaining_risk = risks[:]  # copy

            for _step in range(units):
                if not available:
                    break
                # Probability proportional to tau^alpha * eta^beta
                weights = [
                    (pheromone[i] ** alpha) * (remaining_risk[i] ** beta)
                    for i in available
                ]
                total = sum(weights)
                if total <= 0:
                    idx = rng.choice(available)
                else:
                    r = rng.random() * total
                    cumulative = 0.0
                    idx = available[-1]
                    for i, w in zip(available, weights):
                        cumulative += w
                        if cumulative >= r:
                            idx = i
                            break
                chosen.append(idx)
                available.remove(idx)

            score = sum(risks[i] for i in chosen)
            ant_solutions.append(chosen)
            ant_scores.append(score)

            if score > best_score:
                best_score = score
                best_solution = chosen[:]

        # Evaporation
        pheromone = [p * (1.0 - rho) for p in pheromone]

        # Deposit: only best ant of this iteration deposits
        best_ant_idx = ant_scores.index(max(ant_scores))
        best_ant = ant_solutions[best_ant_idx]
        deposit = q / max(1e-6, ant_scores[best_ant_idx])
        for i in best_ant:
            pheromone[i] += deposit

    # Annotate and return selected cells
    result = []
    for rank, idx in enumerate(sorted(best_solution, key=lambda i: -risks[i])):
        c = dict(cells[idx])
        c["aco_rank"] = rank + 1
        c["aco_pheromone"] = round(pheromone[idx], 4)
        c["units"] = 1
        result.append(c)

    return result
