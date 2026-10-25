"""Two-phase commit is all-or-nothing under any mix of votes, timeouts and stale versions."""

import asyncio

from hypothesis import given, settings
from hypothesis import strategies as st

from broker.cpsat import Proposal, select
from broker.engine import Engine, Timing
from core.events import Bus
from core.wire import Move, ShiftRef

MEMBERS = ["ana", "ben", "dev"]
MOVES = [Move(shift_id="t", from_agent="ana", to_agent="ben"), Move(shift_id="h", from_agent="ben", to_agent="dev"),
         Move(shift_id="f", from_agent="dev", to_agent="ana")]


class FakeNet:
    """Each participant answers PREPARE with an immediate vote, a later vote, or silence."""

    def __init__(self, engine_ref, plan: dict[str, str]):
        self.engine_ref, self.plan = engine_ref, plan
        self.decisions: dict[str, str] = {}

    async def post(self, url: str, body):
        who = url.split("//")[1].split("/")[0]
        if url.endswith("/txn/prepare"):
            v = self.plan[who]
            if v in ("stale", "no"):
                return {"vote": {"txn_id": body.txn_id, "agent_id": who, "vote": v, "ballot": body.ballot}}
            if v == "yes":
                async def later():
                    await asyncio.sleep(0.001)
                    from core.wire import Vote
                    await self.engine_ref[0].vote(Vote(txn_id=body.txn_id, agent_id=who, vote="yes",
                                                       ballot=body.ballot))
                asyncio.get_running_loop().create_task(later())
            return {"vote": None}  # "silent": never votes
        if url.endswith("/txn/decide"):
            self.decisions[who] = body.outcome
        return {}

    async def get(self, url: str):
        return {"version": 1}


@settings(max_examples=60, deadline=None)
@given(st.fixed_dictionaries({a: st.sampled_from(["yes", "no", "stale", "silent"]) for a in MEMBERS + ["steward"]}))
def test_commit_only_if_everyone_says_yes(plan):
    async def run():
        ref = []
        net = FakeNet(ref, plan)
        reg = {"agents": {a: f"http://{a}" for a in MEMBERS}, "steward": "http://steward"}
        eng = Engine(net, reg, Bus(), Timing(0, 0, 0.05, 0))
        ref.append(eng)
        eng.roster = {s: ShiftRef(shift_id=s, employer="library", start="2026-10-27T18:00:00-07:00",
                                  end="2026-10-27T22:00:00-07:00", owner=m.from_agent)
                      for s, m in zip("thf", MOVES, strict=True)}
        p = Proposal("ring-1", "ring", MEMBERS, MOVES, MEMBERS, MEMBERS, versions={a: 1 for a in MEMBERS})
        ok = await eng.two_phase(p)
        return ok, net.decisions, eng

    ok, decisions, eng = asyncio.run(run())
    everyone_yes = all(v == "yes" for v in plan.values())
    assert ok == everyone_yes
    assert set(decisions) == set(MEMBERS) | {"steward"}
    assert len(set(decisions.values())) == 1, "every participant gets the same outcome"
    assert decisions["ana"] == ("commit" if everyone_yes else "abort")
    owners = {s: r.owner for s, r in eng.roster.items()}
    if not everyone_yes:
        assert owners == {"t": "ana", "h": "ben", "f": "dev"}, "an abort leaves the original shifts intact"


def test_cpsat_drops_invalid_and_overlapping_proposals():
    a = Proposal("ring-a", "ring", ["ana", "ben"], MOVES[:1], ["ana"], ["ana"], ok={"ana": True, "ben": True})
    b = Proposal("ring-b", "ring", ["ben", "dev"], MOVES[1:2], ["ben", "dev"], ["ben", "dev"],
                 ok={"ben": True, "dev": True})
    c = Proposal("chain-c", "chain", ["dev", "zoe"], MOVES[2:], ["dev"], [], ok={"dev": True, "zoe": False})
    chosen, status = select([a, b, c])
    assert status == "OPTIMAL"
    assert [p.id for p in chosen] == ["ring-b"]  # b fixes more; a overlaps b on Ben; c has a member who said no


def test_a_forged_vote_without_the_ballot_is_ignored():
    async def run():
        ref = []
        net = FakeNet(ref, {"ana": "silent", "ben": "yes", "dev": "yes", "steward": "yes"})
        reg = {"agents": {a: f"http://{a}" for a in MEMBERS}, "steward": "http://steward"}
        eng = Engine(net, reg, Bus(), Timing(0, 0, 0.2, 0))
        ref.append(eng)
        eng.roster = {s: ShiftRef(shift_id=s, employer="library", start="2026-10-27T18:00:00-07:00",
                                  end="2026-10-27T22:00:00-07:00", owner=m.from_agent)
                      for s, m in zip("thf", MOVES, strict=True)}
        p = Proposal("ring-1", "ring", MEMBERS, MOVES, MEMBERS, MEMBERS, versions={a: 1 for a in MEMBERS})

        async def forge():
            from core.wire import Vote
            await asyncio.sleep(0.01)
            for tid in list(eng.txns):
                await eng.vote(Vote(txn_id=tid, agent_id="ana", vote="yes", ballot="guess"))
        asyncio.get_running_loop().create_task(forge())
        return await eng.two_phase(p)

    assert asyncio.run(run()) is False  # Ana never voted; the forged yes didn't count
