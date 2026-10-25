"""The campus hierarchy above the mascots (seeds/org.py): shift leads, department managers, each employer's backup
manager, Environmental Health and Safety, Student Employment and ISSC. Each role is its own agent with its own inbox
and talks only in core.wire schemas.

A case starts at the lowest rung that can act and climbs one rung each time that rung's timer runs out. Silence
counts as no: a timeout moves a case up and never approves anything. What climbs is the shift id and the rule
that moved it; the reason a student called out stays in their mascot.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core.net import Net
from core.timeutil import PHX, fmt_span, planning_monday
from core.wire import (
    Answer,
    CallOut,
    CaseUpdate,
    Decision,
    Escalation,
    Excused,
    IssueAck,
    IssueReport,
    Move,
    NoTrade,
    Pick,
    PickRequest,
    Prepare,
    Question,
    ShiftRef,
    TradeRequest,
    VersionReport,
    Vote,
)
from ingest.ics import read, shifts_from_ics
from rulebook.quotes import quote_for, rules_text
from seeds.org import CAMPUS_START, DEPARTMENTS, ORG_STUDENTS, ROLES, everyone, members, with_profile

ICS = Path(__file__).resolve().parent.parent / "seeds" / "ics"
VOTE_TIMEOUT = 20.0  # real seconds to wait for every confirmation before a cover is called off


class Tap(BaseModel):
    data: str


class Clock:
    """The hierarchy's story clock. `minute` is real seconds per minute of story time, so a two-hour timer takes
    a few seconds in the demo. It starts at CAMPUS_START the first time a case needs it."""

    def __init__(self, minute: float | None = None):
        self.minute = minute if minute is not None else float(os.environ.get("TAGOUT_ORG_MINUTE", "0.05"))
        self.t0: float | None = None

    def now(self) -> datetime:
        if self.t0 is None:
            self.t0 = time.monotonic()
        return CAMPUS_START + timedelta(minutes=(time.monotonic() - self.t0) / self.minute)

    async def until(self, when: datetime) -> None:
        await asyncio.sleep(max(0.0, (when - self.now()).total_seconds() / 60 * self.minute))

    def reset(self) -> None:
        self.t0 = None


def dept_roster(dept: str) -> dict[str, ShiftRef]:
    """A department's shifts, from each student's own shift export (the Library keeps its own in the Steward)."""
    d, monday = DEPARTMENTS[dept], planning_monday()
    out: dict[str, ShiftRef] = {}
    for s in (x for x in ORG_STUDENTS if x["dept"] == dept):
        for sh in shifts_from_ics(read(ICS / f"{s['id']}_{dept}.ics"), d["employer"], monday - timedelta(days=7),
                                  monday + timedelta(days=14)):
            out[sh.id] = ShiftRef(shift_id=sh.id, employer=d["employer"], start=sh.start, end=sh.end, owner=s["id"],
                                  role=d["role"])
    return out


def create_app(role: str, net: Net, reg: dict, emit: Callable[..., dict] | None = None,
               clock: Clock | None = None) -> FastAPI:
    spec = ROLES[role]
    app = FastAPI(title=f"Tag Out campus hierarchy: {spec['name']}")
    clock = clock or Clock()
    names = everyone()
    tasks: set[asyncio.Task] = set()
    state: dict = {}

    def fresh() -> None:
        # in the demo each person who answers does so a few story minutes after a card lands
        state.update(phone=[], cases={}, txns={}, n=0,
                     auto=os.environ.get("TAGOUT_MODE", "auto") == "auto" and spec.get("answers", True),
                     delay=spec.get("reply_minutes", 5) * clock.minute)
        state["roster"] = {k: v for d in DEPARTMENTS if d != "library" for k, v in dept_roster(d).items()}

    fresh()
    app.state.s = state

    def spawn(coro) -> None:
        t = asyncio.create_task(coro)
        tasks.add(t)
        t.add_done_callback(tasks.discard)

    def event(type_: str, **data) -> None:
        if emit:
            emit(type_, by=role, sim=clock.now().isoformat(timespec="minutes"), minute=clock.minute, **data)

    def url(who: str) -> str:
        return reg.get("org", {}).get(who) or reg["agents"][who]

    def when(ref: ShiftRef) -> str:
        return fmt_span(ref.start, ref.end)

    def at(dt: datetime) -> str:
        return f"{dt:%a} {dt.hour % 12 or 12}:{dt:%M} {'PM' if dt.hour >= 12 else 'AM'}"

    def phone_add(text: str, buttons: list[tuple[str, str]] | None = None, kind: str = "info") -> None:
        msg = {"ts": datetime.now(PHX).isoformat(timespec="seconds"), "sim": clock.now().isoformat(timespec="minutes"),
               "kind": kind, "text": text, "buttons": [{"label": a, "data": b} for a, b in buttons or []]}
        state["phone"].append(msg)
        if state["auto"] and buttons:
            async def later() -> None:
                await asyncio.sleep(state["delay"])
                if any(b["data"] == buttons[0][1] for b in msg["buttons"]):
                    await handle_tap(buttons[0][1])
            spawn(later())

    def case_of(cid: str) -> dict | None:
        return state["cases"].get(cid)

    def due(minutes: float, shift_id: str | None = None) -> datetime:
        """A rung's deadline: its usual wait, but never past the start of the shift (a cover after that is no use)."""
        d = clock.now() + timedelta(minutes=minutes)
        ref = state["roster"].get(shift_id or "")
        return max(clock.now(), min(d, ref.start)) if ref else d

    def offer_crew(dept: str) -> list[str]:
        """People outside the department who already hold a job there with the same employer."""
        return [a for a in with_profile(DEPARTMENTS[dept]["role"]) if a not in members(dept)]

    # ---------- asking mascots: one shift id out, a pick or a pass back ----------
    async def ask(case: dict, who: list[str], iteration: int) -> str | None:
        ref = state["roster"][case["shift_id"]]
        req = PickRequest(round_id=f"{case['id']}-r{iteration}", iteration=iteration, phase="cover", items=[ref])
        event("org_ask", case_id=case["id"], asked=who, iteration=iteration)

        async def one(a: str) -> tuple[str, str | None]:
            try:
                return a, Pick(**await net.post(f"{url(a)}/round/pick", req)).shift_id
            except Exception:
                return a, None  # no answer is a pass
        picks = dict(await asyncio.gather(*(one(a) for a in who)))
        event("org_picks", case_id=case["id"], picks=picks)
        return next((a for a in who if picks.get(a)), None)

    async def cover(case: dict, taker: str) -> bool:
        """Two-phase commit with the student giving the shift and the one taking it; this rung approves."""
        ref = state["roster"][case["shift_id"]]
        state["n"] += 1
        txn = f"org-{role}-{state['n']}"
        moves = [Move(shift_id=ref.shift_id, from_agent=ref.owner, to_agent=taker)]
        crew = [ref.owner, taker]
        t = {"votes": {}, "ballots": {a: secrets.token_hex(4) for a in crew}, "done": asyncio.Event(), "crew": crew,
             "case": case["id"]}
        state["txns"][txn] = t
        event("org_hold", case_id=case["id"], txn_id=txn, members=crew)
        for a in crew:
            try:
                seen = VersionReport(**await net.get(f"{url(a)}/version")).version
                r = await net.post(f"{url(a)}/txn/prepare", Prepare(txn_id=txn, ring_id=case["id"], moves=moves,
                                                                     seen_version=seen, ballot=t["ballots"][a]))
                if r.get("vote"):
                    record(Vote(**r["vote"]))
            except Exception:
                record(Vote(txn_id=txn, agent_id=a, vote="no", ballot=t["ballots"][a]))  # no answer is a no
        try:
            await asyncio.wait_for(t["done"].wait(), VOTE_TIMEOUT)
        except TimeoutError:
            pass
        ok = all(t["votes"].get(a) == "yes" for a in crew)
        outcome = "commit" if ok else "abort"
        await asyncio.gather(*(net.post(f"{url(a)}/txn/decide", Decision(txn_id=txn, outcome=outcome,
                                                                          ballot=t["ballots"][a]))
                               for a in crew), return_exceptions=True)
        state["txns"].pop(txn, None)
        if ok:
            state["roster"][ref.shift_id] = ref.model_copy(update={"owner": taker})
            await close(case, "covered", taker=taker)
            phone_add(f"Covered: {names[taker]} takes {names[ref.owner]}'s {when(ref)}. {names[taker]}'s mascot "
                      "checked their classes and every work-hour limit in private, and both students confirmed.")
        return ok

    def record(v: Vote) -> None:
        t = state["txns"].get(v.txn_id)
        if not t or v.agent_id not in t["crew"] or v.ballot != t["ballots"][v.agent_id]:
            return  # a vote that doesn't echo its ballot doesn't count
        t["votes"][v.agent_id] = v.vote
        event("org_vote", case_id=t["case"], txn_id=v.txn_id, agent=v.agent_id, vote=v.vote)
        if v.vote != "yes" or set(t["votes"]) == set(t["crew"]):
            t["done"].set()

    # ---------- the ladder ----------
    async def climb(case: dict, rule: str) -> None:
        """Hand the case to the next rung up, with a fresh deadline for them."""
        up = spec["up"]
        if up is None or up not in reg.get("org", {}):
            case["status"] = "overdue"
            event("org_overdue", case_id=case["id"])
            phone_add("This is past its deadline and there's nobody above me in the chain. It stays open on my "
                      "list until someone closes it.", kind="info")
            await tell_owner(case)
            return
        deadline = due(ROLES[up]["minutes"], case.get("shift_id"))
        esc = Escalation(case_id=case["id"], kind=case["kind"], level=case["level"] + 1, rule=rule,
                         shift_id=case.get("shift_id"), deadline=deadline, token=case["token"])
        case["status"] = "moved up"
        case["holder"] = up
        event("org_escalate", case_id=case["id"], frm=role, to=up, level=case["level"] + 1, rule=rule,
              deadline=deadline.isoformat(timespec="minutes"))
        try:
            await net.post(f"{reg['org'][up]}/escalate", esc)
        except Exception:  # the rung above never got it: it stays on my list, not "moved up" to nobody
            case["status"], case["holder"] = "overdue", role
            event("org_overdue", case_id=case["id"])
            phone_add(f"I couldn't hand this up to the {names[up].lower()}. It stays open on my list until "
                      "someone closes it.", kind="info")
            await tell_owner(case)

    async def tell_owner(case: dict) -> None:
        """The student hears once when nobody covers their call-out (a shift id only, no reason)."""
        if case["kind"] != "uncovered_callout" or not case.get("owner") or case.get("told"):
            return
        case["told"] = True
        try:
            await net.post(f"{url(case['owner'])}/round/none", NoTrade(shift_id=case["shift_id"]))
        except Exception:
            pass  # their mascot is down: the case is still on the list above them

    async def wait_then_climb(case: dict, rule: str) -> None:
        # a timer can wake a little early, and "acting" means this rung is mid-cover: keep waiting until the
        # deadline has really passed with the case still open here
        while case["status"] in ("open", "acting"):
            await clock.until(case["deadline"])
            if case["status"] == "open" and clock.now() >= case["deadline"]:
                await climb(case, rule)
                return
            await asyncio.sleep(clock.minute)

    async def close(case: dict, outcome: str, taker: str | None = None) -> None:
        case["status"] = outcome
        event("org_done", case_id=case["id"], outcome=outcome, taker=taker)
        dept = case.get("dept") or spec.get("dept")
        if DEPARTMENTS.get(dept, {}).get("asu") and "se" in reg.get("org", {}):
            # Student Employment keeps a weekly count of ASU cases: a department and an outcome, nothing else
            spawn(net.post(f"{reg['org']['se']}/case", CaseUpdate(case_id=f"{dept}-weekly", outcome=outcome)))
        # every rung that held it stops its timer
        for holder in case.get("chain", []):
            if holder != role and holder in ROLES and holder != "steward":  # the Library Steward has its own flow
                spawn(net.post(f"{reg['org'][holder]}/case", CaseUpdate(case_id=case["id"], outcome=outcome,
                                                                        token=case["token"])))
        if outcome == "excused" and case.get("owner"):
            try:
                await net.post(f"{url(case['owner'])}/excused", Excused(shift_id=case["shift_id"]))
            except Exception:
                pass
        elif outcome == "closed":
            await tell_owner(case)

    def open_case(cid: str, kind: str, level: int, deadline: datetime, chain: list[str], token: str = "",
                  **extra) -> dict:
        # the token travels up with each Escalation; only a CaseUpdate that echoes it closes a rung's copy
        case = {"id": cid, "kind": kind, "level": level, "status": "open", "holder": role, "deadline": deadline,
                "chain": chain + [role], "token": token or secrets.token_hex(8), **extra}
        state["cases"][cid] = case
        ref = state["roster"].get(extra.get("shift_id") or "")
        label = f"{when(ref)} at {DEPARTMENTS[extra['dept']]['name'].split(' (')[0]}" if ref and extra.get("dept") else None
        event("org_case", case_id=cid, kind=kind, level=level, holder=role, shift_label=label,
              deadline=deadline.isoformat(timespec="minutes"),
              **{k: v for k, v in extra.items() if k in ("shift_id", "owner", "dept")})
        return case

    # ---------- shift lead: a same-day call-out from a mascot in this department ----------
    @app.post("/trade")
    async def trade(t: TradeRequest) -> dict:
        ref = state["roster"].get(t.shift_id)
        if (spec["kind"] != "lead" or ref is None or ref.owner != t.agent_id
                or ref.employer != DEPARTMENTS[spec["dept"]]["employer"]):
            raise HTTPException(404, "not a shift of yours that this shift lead runs")
        if case_of(f"case-{t.shift_id}"):
            return {}  # already on it: the same request twice opens one case
        deadline = due(spec["minutes"], t.shift_id)
        case = open_case(f"case-{t.shift_id}", "uncovered_callout", 1, deadline, [], shift_id=t.shift_id,
                         owner=ref.owner, dept=spec["dept"])
        spawn(net.post(f"{reg['org'][spec['up']]}/callout", CallOut(shift_id=t.shift_id)))  # the manager hears now
        phone_add(f"{names[ref.owner]} called out of {when(ref)}, no reason given. I'm asking everyone in "
                  f"{DEPARTMENTS[spec['dept']]['name']} now. If nobody can take it by {at(deadline)}, it goes to "
                  f"the {names[spec['up']].lower()}.")
        spawn(lead_round(case))
        return {}

    async def lead_round(case: dict) -> None:
        crew = [a for a in members(spec["dept"]) if a != case["owner"]]
        half = case["deadline"] - (case["deadline"] - clock.now()) / 2
        for i in (1, 2):  # ask now, and again halfway to the deadline (weeks change)
            taker = await ask(case, crew, i)
            if case["status"] != "open":
                return
            if taker and await cover(case, taker):
                return
            if i == 1:
                await clock.until(half)
        await wait_then_climb(case, "no_cover_2h")

    @app.post("/callout")
    async def callout(body: CallOut) -> dict:
        """A copy of a call-out another agent is handling: the Library's broker runs its own round, and a
        department's shift lead tells its manager the moment one comes in."""
        ref = state["roster"].get(body.shift_id)
        if spec["kind"] == "manager" and ref:
            lead = DEPARTMENTS[spec["dept"]]["lead"]
            phone_add(f"Same-day call-out: {names[ref.owner]} can't work {when(ref)}, no reason given. {names[lead]} "
                      f"is asking the {DEPARTMENTS[spec['dept']]['name']} team now; if nobody can take it, it comes "
                      "to you.", kind="info")
        else:
            event("org_note", text=f"Saw a same-day call-out for {body.shift_id}; the Library broker is running the "
                                   "cover round and the Library manager approves.")
        return {}

    # ---------- managers, the backup manager and Student Employment: a case from the rung below ----------
    @app.post("/escalate")
    async def escalate(e: Escalation) -> dict:
        prev = case_of(e.case_id)
        ref = state["roster"].get(e.shift_id or "")
        case = open_case(e.case_id, e.kind, e.level, e.deadline, (prev or {}).get("chain", []), token=e.token,
                         shift_id=e.shift_id, owner=ref.owner if ref else None,
                         dept=e.shift_id.split("-")[0] if e.shift_id else None)
        case["chain"] = sorted({*case["chain"], *lower_rungs(e)})
        why = {"no_cover_2h": "nobody could take it in 2 hours", "no_answer_30m": "the rung below didn't answer in "
               "30 minutes", "safety_first": "it's a safety report"}[e.rule]
        if e.kind == "uncovered_callout" and ref:
            company = DEPARTMENTS[case["dept"]]["company"]
            buttons = ([(f"Offer it to {company} student workers at other locations", f"offer:{e.case_id}")]
                       if offer_crew(case["dept"]) else []) + [("Excuse them; staff covers it", f"excuse:{e.case_id}")]
            nxt = f"it goes to the {names[spec['up']].lower()}" if spec["up"] else "it stays open on your list"
            phone_add(f"Moved up to you because {why}: {names[ref.owner]}'s same-day call-out, {when(ref)} at "
                      f"{DEPARTMENTS[case['dept']]['name']}. No reason was given and none is shared. Act by "
                      f"{at(e.deadline)}, or {nxt}.", buttons, kind="approve")
        spawn(wait_then_climb(case, "no_answer_30m"))
        return {}

    def lower_rungs(e: Escalation) -> list[str]:
        """Everyone below this rung who held the case, so they hear when it closes."""
        dept = e.shift_id.split("-")[0] if e.shift_id else None
        chain = []
        if dept in DEPARTMENTS:
            chain += [DEPARTMENTS[dept]["lead"], DEPARTMENTS[dept]["manager"]]
        return [r for r in chain if r != role]

    @app.post("/case")
    async def case_update(u: CaseUpdate) -> dict:
        if spec["kind"] == "se":  # Student Employment's weekly count: a department and an outcome, nothing else
            dept = u.case_id.split("-")[0]
            state.setdefault("weekly", {}).setdefault(dept, {}).setdefault(u.outcome, 0)
            state["weekly"][dept][u.outcome] += 1
            counts = ", ".join(f"{n} {o}" for o, n in state["weekly"][dept].items())
            phone_add(f"Weekly report, {DEPARTMENTS.get(dept, {}).get('name', dept)}: {counts}. No names, shifts "
                      "or reasons.", kind="info")
            return {}
        case = case_of(u.case_id)
        # only a rung above that held it can close my copy: the rung holding a case closes it itself
        if case and case["status"] == "moved up" and u.token == case["token"]:
            case["status"] = u.outcome
            phone_add(f"Closed above you ({u.outcome}). Nothing more to do.", kind="info")
        return {}

    @app.post("/txn/vote")
    async def vote(v: Vote) -> dict:
        record(v)
        return {}

    async def offer(case: dict) -> str:
        crew = offer_crew(case["dept"])
        if not crew:
            return f"Nobody else works for {DEPARTMENTS[case['dept']]['company']} at another location."
        taker = await ask(case, crew, 3)
        if taker and await cover(case, taker):
            return f"{names[taker]} took it."
        phone_add("Nobody else could take it safely. It stays open until the deadline, then it moves up.")
        return "Nobody else could take it safely."

    # ---------- Student Employment and managers: issue reports ----------
    @app.post("/issue")
    async def issue(r: IssueReport) -> dict:
        who = names.get(r.agent_id, "anonymous") if r.agent_id else "anonymous"
        cid = f"case-{r.issue_id}"
        if spec["kind"] == "ehs":
            cid = f"{cid}-ehs"  # EHS keeps its own case: its acknowledgment doesn't close the department's
        elif spec["kind"] == "manager" and r.category == "safety" and "ehs" in reg.get("org", {}):
            # safety doesn't wait for a ladder: ASU Environmental Health and Safety gets it at once, and the
            # manager on duty keeps its own case for the department
            event("org_escalate", case_id=f"{cid}-ehs", frm=role, to="ehs", level=2, rule="safety_first",
                  deadline=(clock.now() + timedelta(minutes=ROLES["ehs"]["minutes"])).isoformat(timespec="minutes"))
            await net.post(f"{reg['org']['ehs']}/issue", r)
        deadline = clock.now() + timedelta(minutes=spec["minutes"])
        case = open_case(cid, "safety" if r.category == "safety" else "issue", 2, deadline, [],
                         dept=spec.get("dept"))
        case.update(issue_id=r.issue_id, reporter=r.agent_id)
        also = "\nSafety reports go to Environmental Health and Safety at the same time." if (
            r.category == "safety" and spec["kind"] == "manager") else ""
        phone_add(f"{r.category.title()} report from {who}: \"{r.text}\"{also}\nAcknowledge by {at(deadline)}.",
                  [("Acknowledge", f"ack:{cid}")], kind="issue")
        spawn(wait_then_climb(case, "no_answer_30m"))
        return {}

    # ---------- ISSC: an F-1 question the student chose to send ----------
    @app.post("/question")
    async def question(q: Question) -> dict:
        if spec["kind"] != "issc":
            raise HTTPException(404)
        cid = f"case-{q.question_id}"
        deadline, left = clock.now(), 2
        while left:  # two business days, the way an office counts them
            deadline += timedelta(days=1)
            left -= deadline.weekday() < 5
        case = open_case(cid, "f1_question", 1, deadline, [], dept=None)
        case.update(question_id=q.question_id, asker=q.agent_id)
        phone_add(f"F-1 question from {names.get(q.agent_id, q.agent_id)}: \"{q.text}\"\nNo hours or calendar "
                  f"came with it. An advisor (DSO) replies by {at(deadline)}.",
                  [("Send the rule and book an advisor", f"answer:{cid}")], kind="issue")
        return {}

    def issc_answer(case: dict) -> str:
        quote, link = quote_for("f1_break_40")
        rule = f" The break limit ASU publishes: \"{quote}\" ({link})." if quote else ""
        last = ("If fall 2025 is your last semester, however, you won\u2019t be able to work on campus after your "
                "program completion date.")
        end = f" ISSC's note on last year's break also said: \"{last}\"" if last in rules_text() else ""
        return ("ISSC here (synthetic demo). Thanks for asking before scheduling the hours. Break hours depend on "
                "your enrollment for next term and on your program completion date." + rule + end + " So please "
                "don't schedule any break hours until an advisor (DSO) has checked your dates; they'll reply by "
                f"{at(case['deadline'])}. Not legal or immigration advice.")

    # ---------- the inbox ----------
    async def handle_tap(data: str) -> str:
        verb, _, cid = data.partition(":")
        case = case_of(cid)
        if not case or case["status"] not in ("open", "overdue"):  # overdue stays open until someone closes it
            return "That's already handled."
        for m in state["phone"]:  # one answer per card
            if any(b["data"] == data for b in m["buttons"]):
                m["buttons"] = []
        if verb == "offer":
            was, case["status"] = case["status"], "acting"
            reply = await offer(case)
            if case["status"] == "acting":
                case["status"] = was  # open: this rung's timer moves it up at the deadline; overdue stays overdue
        elif verb == "excuse":
            await close(case, "excused")
            reply = (f"Excused: {names.get(case.get('owner'), 'the student')} doesn't need to find cover, and staff "
                     "covers the shift. Their mascot lets them know; nobody is told why.")
        elif verb == "close":
            await close(case, "closed")
            reply = "Closed. The shift is marked open."
        elif verb == "ack":
            await close(case, "acknowledged")
            if case.get("reporter"):
                await net.post(f"{url(case['reporter'])}/issue/ack", IssueAck(
                    issue_id=case["issue_id"], office="ehs" if spec["kind"] == "ehs" else "manager"))
            reply = "Acknowledged." + (" Their mascot lets them know." if case.get("reporter") else "")
        elif verb == "answer":
            await net.post(f"{url(case['asker'])}/question/answer",
                           Answer(question_id=case["question_id"], text=issc_answer(case)))
            await close(case, "answered")
            reply = "Sent the rule and booked an advisor reply."
        else:
            return "?"
        phone_add(reply, kind="reply")
        return reply

    @app.post("/tap")
    async def tap(t: Tap) -> dict:
        return {"reply": await handle_tap(t.data)}

    @app.get("/phone")
    async def phone() -> dict:
        return {"student": spec["name"], "messages": [{"n": i + 1, **m} for i, m in enumerate(state["phone"])]}

    @app.get("/state")
    async def get_state() -> dict:
        return {"id": role, **{k: spec.get(k) for k in ("name", "title", "kind", "dept", "pet_id", "up", "minutes")},
                "answers": state["auto"],
                "cases": [{k: (v.isoformat(timespec="minutes") if isinstance(v, datetime) else v)
                           for k, v in c.items() if k != "token"} for c in state["cases"].values()],
                "phone": [{"n": i + 1, **m} for i, m in enumerate(state["phone"])]}

    @app.post("/admin/reset")
    async def reset() -> dict:
        if os.environ.get("TAGOUT_DEBUG") != "1":
            raise HTTPException(403)
        for t in list(tasks):
            t.cancel()
        fresh()
        clock.reset()
        return {"ok": True}

    @app.post("/admin/auto")
    async def auto(body: dict) -> dict:
        state["auto"] = bool(body.get("enabled", True)) and spec.get("answers", True)
        state["delay"] = float(body.get("delay", state["delay"]))
        return {"auto": state["auto"]}

    return app
