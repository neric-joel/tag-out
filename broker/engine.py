"""The Broker's round engine. It holds only shift ids, picks, ok bits and votes.

Week flow: trade requests -> TTC swap rounds (all picks released together at each deadline) -> a counter-offer
window -> another swap round -> cover chains -> every member re-checks the exact final ring -> CP-SAT selection ->
two-phase commit per proposal (mascots + Steward/manager) -> abort releases holds and the engine tries again.
"""

from __future__ import annotations

import asyncio
import itertools
import secrets
from dataclasses import dataclass, field

from broker.cpsat import Proposal, select
from broker.ttc import find_cycles
from core.events import Bus
from core.net import Net
from core.wire import (
    Decision,
    Eligibility,
    Move,
    NoTrade,
    OpenShift,
    Pick,
    PickRequest,
    Prepare,
    RingCheck,
    ShiftRef,
    Vote,
)

WAGE = 16.0


@dataclass
class Timing:
    pick_deadline: float = 1.0  # every reply is held until this deadline, so speed reveals nothing
    ask_window: float = 3.0  # time for mascots that asked their student
    vote_timeout: float = 30.0
    between: float = 0.6  # pacing so the arena is watchable

    @classmethod
    def fast(cls) -> Timing:
        return cls(0.0, 0.3, 5.0, 0.0)

    @classmethod
    def live(cls) -> Timing:
        """Real people: a minute to answer their mascot's question, five minutes to confirm."""
        return cls(2.0, 60.0, 300.0, 1.0)


@dataclass
class Txn:
    id: str
    proposal: Proposal
    votes: dict[str, str] = field(default_factory=dict)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    expected: set[str] = field(default_factory=set)
    ballots: dict[str, str] = field(default_factory=dict)


class Engine:
    def __init__(self, net: Net, reg: dict, bus: Bus, timing: Timing | None = None):
        self.net, self.reg, self.bus = net, reg, bus
        self.timing = timing or Timing()
        self.requests: dict[str, str] = {}  # shift_id -> owner (from trade requests)
        self.resolved: dict[str, str] = {}  # shift_id -> how ("ring-1", "chain-2")
        self.roster: dict[str, ShiftRef] = {}
        self.txns: dict[str, Txn] = {}
        self.proposals: list[Proposal] = []
        self.summary: dict = {}
        self.committed: list[Proposal] = []
        self.ids = itertools.count(1)
        self.running = False

    # ---------- inputs ----------
    def request(self, agent: str, shift_id: str) -> None:
        if shift_id not in self.resolved:
            self.requests[shift_id] = agent
            self.bus.emit("trade_request", agent=agent, shift_id=shift_id)

    async def vote(self, v: Vote) -> None:
        t = self.txns.get(v.txn_id)
        if t is None or t.done.is_set():
            return
        if v.agent_id not in t.expected or v.ballot != t.ballots.get(v.agent_id):
            return  # not a member, or not holding this member's ballot: a forged vote changes nothing
        t.votes[v.agent_id] = v.vote
        self.bus.emit("vote", txn_id=t.id, agent=v.agent_id, vote=v.vote)
        if v.vote != "yes" or set(t.votes) >= t.expected:
            t.done.set()

    # ---------- helpers ----------
    async def load_roster(self) -> None:
        refs = await self.net.get(f"{self.reg['steward']}/roster")
        self.roster = {r["shift_id"]: ShiftRef(**r) for r in refs}

    def ref(self, sid: str) -> ShiftRef:
        return self.roster[sid]

    async def ask_picks(self, reqs: dict[str, PickRequest]) -> dict[str, str | None]:
        async def one(agent: str, req: PickRequest) -> tuple[str, str | None]:
            try:
                p = Pick(**await self.net.post(f"{self.reg['agents'][agent]}/round/pick", req))
                valid = p.shift_id is None or any(i.shift_id == p.shift_id for i in req.items)
                return agent, p.shift_id if valid else None
            except Exception:
                return agent, None  # a silent or broken mascot is a pass

        deadline = asyncio.sleep(self.timing.pick_deadline)
        results, _ = await asyncio.gather(asyncio.gather(*(one(a, r) for a, r in reqs.items())), deadline)
        return dict(sorted(results))

    def open_items(self) -> dict[str, str]:
        """Conflicted shifts still waiting, one per owner per round (earliest first)."""
        out: dict[str, str] = {}
        for sid, owner in sorted(self.requests.items(), key=lambda kv: self.ref(kv[0]).start):
            if sid not in self.resolved and owner not in out.values() and self.ref(sid).owner == owner:
                out[sid] = owner
        return out

    # ---------- phases ----------
    async def swap_rounds(self, round_id: str, items: dict[str, str], it: int) -> tuple[list[list[str]], int]:
        cycles: list[list[str]] = []
        while True:
            active = {o for o in items.values()}
            if len(active) < 2:
                return cycles, it
            refs = [self.ref(s) for s in items]
            item_of = {o: s for s, o in items.items()}
            reqs = {o: PickRequest(round_id=round_id, iteration=it, phase="swap", items=refs, you_give=item_of[o])
                    for o in sorted(active)}
            self.bus.emit("round", round_id=round_id, iteration=it, phase="swap", agents=sorted(active),
                          items=[r.shift_id for r in refs])
            picks = await self.ask_picks(reqs)
            self.bus.emit("picks", round_id=round_id, iteration=it, phase="swap", picks=picks)
            found = find_cycles(picks, items)
            it += 1
            if not found:
                # standard TTC: a passer keeps their own shift and leaves; whoever pointed at it re-points
                passers = {a for a, i in picks.items() if i is None}
                if not passers or passers == active:
                    return cycles, it
                self.bus.emit("released", round_id=round_id, agents=sorted(passers))
                for a in passers:
                    items.pop(item_of[a], None)
                continue
            for c in found:
                cycles.append(c)
                self.bus.emit("cycle", round_id=round_id, members=c,
                              moves=[m.model_dump() for m in self.cycle_moves(c, items)])
                for a in c:
                    items.pop(item_of[a], None)
            await asyncio.sleep(self.timing.between)

    def cycle_moves(self, c: list[str], items: dict[str, str]) -> list[Move]:
        item_of = {o: s for s, o in items.items()}
        return [Move(shift_id=item_of[c[(j + 1) % len(c)]], from_agent=c[(j + 1) % len(c)], to_agent=a)
                for j, a in enumerate(c)]

    async def chain_round(self, round_id: str, items: dict[str, str], it: int) -> tuple[list[list[Move]], int]:
        owners = set(items.values())
        helpers = sorted(a for a in self.reg["agents"] if a not in owners)
        refs = [self.ref(s) for s in items]
        reqs = {h: PickRequest(round_id=round_id, iteration=it, phase="cover", items=refs) for h in helpers}
        self.bus.emit("round", round_id=round_id, iteration=it, phase="cover", agents=helpers,
                      items=[r.shift_id for r in refs])
        picks = await self.ask_picks(reqs)
        self.bus.emit("picks", round_id=round_id, iteration=it, phase="cover", picks=picks)
        it += 1
        chains: list[list[Move]] = []
        for h, sid in picks.items():
            if sid is None or sid not in items:
                continue
            chain = [Move(shift_id=sid, from_agent=items.pop(sid), to_agent=h)]
            members = {h, chain[0].from_agent}
            while items:
                giver = chain[-1].from_agent
                refs_left = [self.ref(s) for s, o in items.items() if o not in members]
                if not refs_left:
                    break
                req = PickRequest(round_id=round_id, iteration=it, phase="extend", items=refs_left,
                                  you_give=chain[-1].shift_id)
                self.bus.emit("round", round_id=round_id, iteration=it, phase="extend", agents=[giver],
                              items=[r.shift_id for r in refs_left])
                got = (await self.ask_picks({giver: req}))[giver]
                self.bus.emit("picks", round_id=round_id, iteration=it, phase="extend", picks={giver: got})
                it += 1
                if got is None or got not in items:
                    break
                chain.append(Move(shift_id=got, from_agent=items.pop(got), to_agent=giver))
                members.add(chain[-1].from_agent)
            chains.append(chain)
            self.bus.emit("chain", round_id=round_id, moves=[m.model_dump() for m in chain])
        return chains, it

    # ---------- validation ----------
    async def validate(self, p: Proposal) -> None:
        async def check(a: str) -> tuple[str, bool, int]:
            url = self.reg["agents"][a]
            try:
                e = Eligibility(**await self.net.post(f"{url}/ring/check", RingCheck(ring_id=p.id, moves=p.moves)))
                v = (await self.net.get(f"{url}/version"))["version"]
                return a, e.ok, v
            except Exception:
                return a, False, -1

        res = await asyncio.gather(*(check(a) for a in p.members))
        p.ok = {a: ok for a, ok, _ in res}
        p.versions = {a: v for a, _, v in res}
        p.versions["steward"] = (await self.net.get(f"{self.reg['steward']}/version"))["version"]
        self.bus.emit("validated", proposal=p.id, kind=p.kind, ok=p.valid, checks=len(p.ok),
                      passed=sum(1 for v in p.ok.values() if v))

    # ---------- two-phase commit ----------
    async def two_phase(self, p: Proposal) -> bool:
        tid = f"txn-{next(self.ids)}"
        t = Txn(tid, p, expected=set(p.members) | {"steward"})
        t.ballots = {a: secrets.token_urlsafe(12) for a in t.expected}
        self.txns[tid] = t
        self.bus.emit("prepare", txn_id=tid, proposal=p.id, members=p.members,
                      moves=[m.model_dump() for m in p.moves])
        targets = {a: self.reg["agents"][a] for a in p.members} | {"steward": self.reg["steward"]}

        async def prep(a: str, url: str) -> None:
            try:
                r = await self.net.post(f"{url}/txn/prepare", Prepare(txn_id=tid, ring_id=p.id, moves=p.moves,
                                                                       seen_version=p.versions.get(a, -1),
                                                                       ballot=t.ballots[a]))
                if r.get("vote"):
                    await self.vote(Vote(**r["vote"]))
            except Exception:
                await self.vote(Vote(txn_id=tid, agent_id=a, vote="no", ballot=t.ballots[a]))

        await asyncio.gather(*(prep(a, u) for a, u in targets.items()))
        try:
            await asyncio.wait_for(t.done.wait(), timeout=self.timing.vote_timeout)
        except TimeoutError:
            for a in t.expected - set(t.votes):
                t.votes[a] = "timeout"
                self.bus.emit("vote", txn_id=tid, agent=a, vote="timeout")
        commit = set(t.votes) >= t.expected and all(v == "yes" for v in t.votes.values())
        t.done.set()
        outcome = "commit" if commit else "abort"
        await asyncio.gather(*(self.net.post(f"{u}/txn/decide", Decision(txn_id=tid, outcome=outcome))
                               for u in targets.values()), return_exceptions=True)
        self.bus.emit(outcome, txn_id=tid, proposal=p.id, members=p.members,
                      moves=[m.model_dump() for m in p.moves])
        if commit:
            self.committed.append(p)
            for mv in p.moves:
                if mv.shift_id in self.requests:
                    self.resolved[mv.shift_id] = p.id
                self.roster[mv.shift_id] = self.roster[mv.shift_id].model_copy(update={"owner": mv.to_agent})
        return commit

    # ---------- the week ----------
    async def run(self, max_attempts: int = 3) -> dict:
        if self.running:
            return {"busy": True}
        self.running = True
        try:
            await self.load_roster()
            asked = len(self.requests)
            for attempt in range(1, max_attempts + 1):
                aborted = await self.attempt(attempt)
                if not aborted:
                    break
            return await self.finish(asked)
        finally:
            self.running = False

    async def attempt(self, attempt: int) -> bool:
        items = self.open_items()
        if not items:
            return False
        rid = f"round-{attempt}"
        self.bus.emit("round_open", round_id=rid, attempt=attempt, items=[self.ref(s).model_dump(mode="json")
                                                                         for s in items])
        cycles, it = await self.swap_rounds(rid, dict(items), 1)
        remaining = {s: o for s, o in items.items() if not any(o in c for c in cycles)}
        if len(remaining) >= 2 and self.timing.ask_window > 0:
            self.bus.emit("counter_window", round_id=rid, seconds=self.timing.ask_window)
            await asyncio.sleep(self.timing.ask_window)
            more, it = await self.swap_rounds(rid, dict(remaining), it)
            cycles += more
            remaining = {s: o for s, o in remaining.items() if not any(o in c for c in more)}
        chains, it = await self.chain_round(rid, dict(remaining), it) if remaining else ([], it)
        covered = {m.shift_id for ch in chains for m in ch}
        left = {s: o for s, o in remaining.items() if s not in covered}
        if left and self.timing.ask_window > 0:
            # a helper near a limit asks its student first; give the answers the same window as a swap round
            self.bus.emit("counter_window", round_id=rid, seconds=self.timing.ask_window, phase="cover")
            await asyncio.sleep(self.timing.ask_window)
            more, it = await self.chain_round(rid, left, it)
            chains += more

        proposals = []
        for c in cycles:
            moves = self.cycle_moves(c, items)
            proposals.append(Proposal(f"ring-{next(self.ids)}", "ring", list(c), moves, list(c), list(c)))
        for ch in chains:
            members = [ch[0].to_agent] + [m.from_agent for m in ch]
            keeps = [m.to_agent for m in ch[1:]]
            proposals.append(Proposal(f"chain-{next(self.ids)}", "chain", members, ch,
                                      [m.from_agent for m in ch], keeps))
        await asyncio.gather(*(self.validate(p) for p in proposals))
        chosen, status = select(proposals)
        self.proposals += proposals
        self.bus.emit("selected", status=status, proposals=[p.id for p in chosen],
                      dropped=[p.id for p in proposals if p not in chosen])
        aborted = False
        for p in chosen:
            await asyncio.sleep(self.timing.between)
            if not await self.two_phase(p):
                aborted = True
        return aborted

    async def finish(self, asked: int) -> dict:
        fixed = [s for s in self.requests if s in self.resolved]
        open_ = [s for s in self.requests if s not in self.resolved]
        for s in open_:
            try:
                await self.net.post(f"{self.reg['steward']}/open", OpenShift(shift_id=s))
                await self.net.post(f"{self.reg['agents'][self.requests[s]]}/round/none", NoTrade(shift_id=s))
            except Exception:
                pass
        by_kind = {"ring": 0, "chain": 0}
        pay_kept = 0.0
        for p in self.committed:
            by_kind[p.kind] += len(p.fixes)
            kept = {mv.shift_id for mv in p.moves if mv.from_agent in p.keeps_pay}
            pay_kept += sum(self.hours(s) * WAGE for s in kept)
        self.summary = {"asked": asked, "fixed": len(fixed), "open": len(open_), "by_ring": by_kind["ring"],
                        "by_chain": by_kind["chain"], "pay_kept": pay_kept, "open_shifts": open_}
        self.bus.emit("summary", **self.summary)
        return self.summary

    def hours(self, sid: str) -> float:
        r = self.roster[sid]
        return (r.end - r.start).total_seconds() / 3600

    def reset(self) -> None:
        self.committed.clear()
        self.requests.clear()
        self.resolved.clear()
        self.txns.clear()
        self.proposals.clear()
        self.summary = {}
        self.ids = itertools.count(1)
