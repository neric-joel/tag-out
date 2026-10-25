"""CP-SAT picks which proposed rings and chains to run.

Inputs are public: each proposal's moves and every member's ok bit from their own Rulebook check. The model picks a
set of proposals with no shared person and no shared shift, maximising conflicts fixed, then pay kept, then fewest
changed shifts. "No safe trade" is a valid answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from core.wire import Move


@dataclass
class Proposal:
    id: str
    kind: str  # ring | chain
    members: list[str]
    moves: list[Move]
    fixes: list[str]  # owners whose conflicted shift moves
    keeps_pay: list[str]  # owners who also take a shift back
    ok: dict[str, bool] = field(default_factory=dict)
    versions: dict[str, int] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return bool(self.ok) and all(self.ok.get(m, False) for m in self.members)


def select(proposals: list[Proposal], time_limit: float = 2.0) -> tuple[list[Proposal], str]:
    if not proposals:
        return [], "EMPTY"
    m = cp_model.CpModel()
    x = {p.id: m.new_bool_var(p.id) for p in proposals}
    for p in proposals:
        if not p.valid:
            m.add(x[p.id] == 0)
    people = {a for p in proposals for a in p.members}
    for a in people:
        m.add_at_most_one(x[p.id] for p in proposals if a in p.members)
    shifts = {mv.shift_id for p in proposals for mv in p.moves}
    for s in shifts:
        m.add_at_most_one(x[p.id] for p in proposals if any(mv.shift_id == s for mv in p.moves))
    m.maximize(sum(x[p.id] * (1000 * len(p.fixes) + 100 * len(p.keeps_pay) - len(p.moves)) for p in proposals))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 7
    status = solver.solve(m)
    name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], name
    return [p for p in proposals if solver.value(x[p.id])], name
