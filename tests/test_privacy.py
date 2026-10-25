"""Privacy is enforced by schema and checked by scanning every message of a full run."""

import json
import re

import pytest
from pydantic import ValidationError

from core.models import BusyBlock
from core.wire import Eligibility, Pick, PublicFace, Vote, Wire
from scripts.inproc import System


def test_a_pick_cannot_carry_hours_or_a_reason():
    with pytest.raises(ValidationError):
        Pick(round_id="r", iteration=1, agent_id="ben", shift_id=None, hours=17)
    with pytest.raises(ValidationError):
        Pick.model_validate({"round_id": "r", "iteration": 1, "agent_id": "ben", "shift_id": None,
                             "reason": "F-1 limit"})
    with pytest.raises(ValidationError):
        Eligibility(ring_id="x", agent_id="ben", ok=False, rule="f1_weekly_20")
    with pytest.raises(ValidationError):
        Vote(txn_id="t", agent_id="ben", vote="no", why="interview")


def test_public_badges_cannot_describe_limits():
    with pytest.raises(ValidationError):
        PublicFace(agent_id="b", name="B", pet_id="p", state="idle", trades_made=0, badges=["Max Hours"])
    with pytest.raises(ValidationError):
        PublicFace(agent_id="b", name="B", pet_id="p", state="idle", trades_made=0, badges=["F-1"])


def wire_fields() -> set[str]:
    out = set()
    for cls in Wire.__subclasses__():
        out |= set(cls.model_fields)
    return out | {"vote"}  # the PREPARE reply envelope: {"vote": Vote | None}


def keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | set().union(*(keys(v) for v in obj.values())) if obj else set()
    if isinstance(obj, list):
        return set().union(*(keys(v) for v in obj)) if obj else set()
    return set()


@pytest.fixture
async def ran(tmp_path):
    s = System(tmp=tmp_path)
    await s.post("/admin/auto", {"enabled": False, "agents": ["dev"], "delay": 0.05})
    await s.post("/demo/sunday")
    await s.post("/phone/dev/tap", {"data": "trade:yes:library-fri-1030-1000-d1"})
    await s.settle(0.3)
    await s.post("/demo/run")
    await s.wait_for("prepare")
    await s.post("/demo/break")
    await s.wait_for("abort")
    await s.post("/admin/auto", {"enabled": True, "agents": ["dev"], "delay": 0.05})
    await s.wait_for("summary", timeout=30)
    yield s
    await s.close()


async def test_no_private_value_crosses_between_agents(ran):
    s = ran
    secrets: set[str] = set()
    for sid in s.apps:
        st = s.store(sid).student()
        for b in s.store(sid).busy():
            secrets.add(b.label)
            secrets.update(w for w in re.findall(r"[A-Za-z][A-Za-z.']{4,}", b.label)
                           if w.lower() not in {"shift", "front", "desk", "with", "your"})
        secrets.update(a.label for a in st.prefs.soft_avoid)
        secrets.update(st.limits.other_employer_hours)
    secrets |= {"F-1", "f1_or_j1", "visa", "fws_award", "hours_history", "aca_25_avg", "f1_weekly_20", "Aramark"}
    assert len(secrets) > 25

    allowed = wire_fields()
    frames = s.tap.frames
    assert len(frames) > 100
    for f in frames:
        if not f["body"]:
            continue
        body = json.loads(f["body"])
        extra = keys(body) - allowed - {"agent_id", "version"} - set(s.reg["agents"]) - {"steward"}
        extra -= {k for k in keys(body) if re.fullmatch(r"[A-Z][a-z]{2} \d{1,2}-\d{1,2}", k)}  # forecast slots
        assert not extra, f"unexpected field(s) {extra} in {f['url']}"
        low = f["body"].lower()
        for secret in secrets:
            assert secret.lower() not in low, f"{secret!r} leaked in {f['url']}"

    public = json.dumps(s.bus.history) + json.dumps(s.steward.state.s["phone"])
    for secret in secrets:
        assert secret.lower() not in public.lower(), f"{secret!r} leaked to the public stream or manager"


async def test_owner_phone_does_get_the_reason(ran):
    texts = " ".join(m["text"] for m in ran.phone("ana"))
    assert "CSE 310" in texts  # the reason stays with its owner, and only there


def test_busy_labels_are_private_models():
    assert BusyBlock.model_config.get("extra") == "forbid"
