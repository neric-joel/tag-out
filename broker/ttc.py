"""Top Trading Cycles over picks, plus cover chains.

The Broker only ever sees picks: "agent a would take shift x". It never sees why, or hours, or limits.

A cycle [a, b, c] means: a takes b's shift, b takes c's shift, c takes a's shift. Everyone keeps their hours.
A chain [h, o1, o2] means: helper h covers o1's shift, o1 takes o2's shift, o2 just drops theirs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping


def next_agent(a: str, points: Mapping[str, str | None], owner_of: Mapping[str, str]) -> str | None:
    item = points.get(a)
    if item is None:
        return None
    owner = owner_of.get(item)
    return owner if owner in points and owner != a else None  # picking your own shift is a pass


def find_cycles(points: Mapping[str, str | None], owner_of: Mapping[str, str]) -> list[list[str]]:
    """Cycles in the pick graph (each agent points at most once, so it is a functional graph)."""
    state: dict[str, int] = {}  # 0 unseen, 1 on stack, 2 done
    cycles: list[list[str]] = []
    for start in sorted(points):
        if state.get(start):
            continue
        path: list[str] = []
        a: str | None = start
        while a is not None and not state.get(a):
            state[a] = 1
            path.append(a)
            a = next_agent(a, points, owner_of)
        if a is not None and state.get(a) == 1:
            cyc = path[path.index(a):]
            i = cyc.index(min(cyc))  # canonical rotation for stable output
            cycles.append(cyc[i:] + cyc[:i])
        for p in path:
            state[p] = 2
    return cycles


def ttc(
    prefs: Mapping[str, list[str]],
    owner_of: Mapping[str, str],
    picker: Callable[[str, set[str]], str | None] | None = None,
    release_passers: bool = True,
) -> tuple[list[list[str]], list[dict[str, str | None]]]:
    """Run TTC rounds until nothing more can close.

    `prefs[a]` is a's ranked list of acceptable items (used when no `picker` is given). `picker(a, open_items)`
    lets a live mascot answer each round itself. With `release_passers` (standard TTC with outside options), an
    agent who passes keeps their own shift and leaves, so whoever pointed at it can re-point next round.
    Returns (cycles, the picks of every round).
    """
    active = {a for a in prefs if any(o == a for o in owner_of.values())}
    open_items = {i for i, o in owner_of.items() if o in active}
    cycles: list[list[str]] = []
    history: list[dict[str, str | None]] = []
    def pick(a: str, available: set[str]) -> str | None:
        choices = available - {i for i, o in owner_of.items() if o == a}
        if picker is not None:
            return picker(a, choices)
        return next((i for i in prefs[a] if i in choices), None)

    while active:
        points = {a: pick(a, open_items) for a in sorted(active)}
        history.append(points)
        found = find_cycles(points, owner_of)
        if not found:
            passers = {a for a, i in points.items() if i is None}
            if not release_passers or not passers or passers == active:
                break
            active -= passers
            open_items -= {i for i, o in owner_of.items() if o in passers}
            continue
        for cyc in found:
            cycles.append(cyc)
            for a in cyc:
                active.discard(a)
                open_items -= {i for i, o in owner_of.items() if o == a}
    return cycles, history


def chains(
    helper_prefs: Mapping[str, list[str]],
    extend_prefs: Mapping[str, list[str]],
    open_items: set[str],
    owner_of: Mapping[str, str],
) -> list[list[str]]:
    """Cover chains for items left after TTC.

    Each helper (someone with room who wants hours) covers its top open item. The covered owner may then take
    another open item, keeping their hours, and so on until someone just drops their shift.
    """
    open_items = set(open_items)
    out: list[list[str]] = []
    for h in sorted(helper_prefs):
        first = next((i for i in helper_prefs[h] if i in open_items and owner_of[i] != h), None)
        if first is None:
            continue
        chain = [h]
        item: str | None = first
        while item is not None:
            open_items.discard(item)
            owner = owner_of[item]
            chain.append(owner)
            item = next((i for i in extend_prefs.get(owner, []) if i in open_items and owner_of[i] not in chain),
                        None)
        out.append(chain)
    return out
