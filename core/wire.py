"""Closed message schemas: the only things that may cross between agents.

Every model forbids extra fields and is frozen. A mascot can send a shift id, a pass, a vote or an ok bit.
There is no field for hours, reasons, rule names or labels, so a message carrying one is rejected at parse time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ShiftRef(Wire):
    """Public roster facts about a shift (the employer already shares these with its staff)."""

    shift_id: str
    employer: str
    start: datetime
    end: datetime
    owner: str


class TradeRequest(Wire):
    agent_id: str
    shift_id: str


class PickRequest(Wire):
    round_id: str
    iteration: int
    phase: Literal["swap", "cover", "extend"]
    items: list[ShiftRef]
    you_give: str | None = None  # the shift this agent hands over if a ring closes


class Pick(Wire):
    round_id: str
    iteration: int
    agent_id: str
    shift_id: str | None  # None means pass. A pass looks the same whatever the reason.


class Move(Wire):
    shift_id: str
    from_agent: str
    to_agent: str


class RingCheck(Wire):
    ring_id: str
    moves: list[Move]


class Eligibility(Wire):
    ring_id: str
    agent_id: str
    ok: bool


class Prepare(Wire):
    txn_id: str
    ring_id: str
    moves: list[Move]
    seen_version: int


class Vote(Wire):
    txn_id: str
    agent_id: str
    vote: Literal["yes", "no", "stale", "timeout"]


class Decision(Wire):
    txn_id: str
    outcome: Literal["commit", "abort"]


class VersionReport(Wire):
    agent_id: str
    version: int


class BusyBits(Wire):
    """For the manager's crunch forecast: one bit per roster slot, no labels."""

    agent_id: str
    slots: dict[str, bool]


class PublicFace(Wire):
    agent_id: str
    name: str
    pet_id: str
    state: Literal["idle", "thinking", "shrug", "covering", "relieved", "walking", "failed"]
    trades_made: int
    badges: list[Literal["Clutch", "Chain Link", "Streak"]]
