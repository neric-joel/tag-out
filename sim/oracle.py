"""Brute-force reference implementations used as test oracles for broker/ttc.py and the simulator."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations, permutations


def cycles_by_subsets(points: Mapping[str, str | None], owner_of: Mapping[str, str]) -> set[frozenset[str]]:
    """Every agent set that forms one closed pointing cycle. Exponential; fine for n <= 9."""
    def nxt(a: str) -> str | None:
        item = points.get(a)
        o = owner_of.get(item) if item else None
        return o if o in points and o != a else None

    agents = sorted(points)
    found: set[frozenset[str]] = set()
    for k in range(2, len(agents) + 1):
        for subset in combinations(agents, k):
            s = set(subset)
            if any(nxt(a) not in s for a in subset):
                continue
            # one cycle covering the whole subset: from every member, k steps visit all and come back home
            def orbit(start: str, k: int = k) -> tuple[set[str], str | None]:
                seen, a = set(), start
                for _ in range(k):
                    seen.add(a)
                    a = nxt(a)
                return seen, a

            if all(orbit(m) == (s, m) for m in subset):
                found.add(frozenset(s))
    return found


def max_conflicts_solved(acceptable: Mapping[str, set[str]], owner_of: Mapping[str, str],
                         max_len: int = 4) -> int:
    """Upper bound: most owners whose shift can move inside disjoint acceptable cycles (any length <= max_len)."""
    owners = sorted({o for o in owner_of.values() if o in acceptable})
    item_of = {o: i for i, o in owner_of.items()}
    cycles: list[frozenset[str]] = []
    for k in range(2, min(max_len, len(owners)) + 1):
        for combo in combinations(owners, k):
            for perm in permutations(combo[1:]):
                order = (combo[0],) + perm
                if all(item_of[order[(j + 1) % k]] in acceptable[order[j]] for j in range(k)):
                    cycles.append(frozenset(order))
                    break
    best = 0

    def search(idx: int, used: frozenset[str], total: int) -> None:
        nonlocal best
        best = max(best, total)
        for j in range(idx, len(cycles)):
            if not (cycles[j] & used):
                search(j + 1, used | cycles[j], total + len(cycles[j]))

    search(0, frozenset(), 0)
    return best
