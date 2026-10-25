"""What crossed between agents, for the live agent graph. Only peer messages (the closed schemas in core/wire.py)
are reported; the owner channel (phone, tap, intake, diary) never is. Ballots are redacted, so a vote can't be
forged from the public stream.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# path -> (request schema, response schema)
SCHEMAS = {
    "/sunday": ("SundayCheck", None),
    "/round/pick": ("PickRequest", "Pick"),
    "/ring/check": ("RingCheck", "Eligibility"),
    "/version": (None, "VersionReport"),
    "/txn/prepare": ("Prepare", "Vote"),
    "/txn/decide": ("Decision", None),
    "/txn/vote": ("Vote", None),
    "/trade": ("TradeRequest", None),
    "/round/none": ("NoTrade", None),
    "/roster": (None, "ShiftRef[]"),
    "/open": ("OpenShift", None),
    "/callout": ("CallOut", None),
    "/busybits": ("SlotQuery", "BusyBits"),
    "/extra": ("ShiftRef", None),
    "/meeting/invite": ("MeetingInvite", None),
    "/meeting/rsvp": ("Rsvp", None),
    "/meeting/request": ("MeetingRequest", "MeetingOptions"),
    "/meeting/book": ("MeetingBook", None),
    "/issue": ("IssueReport", None),
    "/issue/ack": ("IssueAck", None),
    # the campus hierarchy (org/app.py)
    "/escalate": ("Escalation", None),
    "/case": ("CaseUpdate", None),
    "/excused": ("Excused", None),
    "/question": ("Question", None),
    "/question/answer": ("Answer", None),
}
SENDER_IN_BODY = {"/trade", "/txn/vote", "/meeting/rsvp", "/meeting/request", "/meeting/book", "/question"}
FROM_STEWARD = {"/busybits", "/meeting/invite", "/extra", "/issue/ack"}


def is_peer(url: str) -> bool:
    return urlsplit(url).path in SCHEMAS


def redact(obj):
    if isinstance(obj, dict):
        return {k: ("•••" if k in ("ballot", "token") else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def describe(reg: dict, method: str, url: str, payload: dict | None, status: int, response,
             sender: str | None = None) -> dict:
    """One wire event: who sent what to whom, and what came back. `sender` is set by agents whose Net knows who
    they are (the campus hierarchy); otherwise the sender is read from the path."""
    parts = urlsplit(url)
    path, base = parts.path, f"{parts.scheme}://{parts.netloc}"
    owners = ({u: a for a, u in reg["agents"].items()} | {u: a for a, u in reg.get("org", {}).items()}
              | {reg["broker"]: "broker", reg["steward"]: "steward"})
    to = owners.get(base, base)
    if sender:
        pass
    elif path in SENDER_IN_BODY and isinstance(payload, dict):
        sender = payload.get("agent_id") or "?"
    elif path == "/issue":
        sender = (payload or {}).get("agent_id") or "a mascot (anonymous)"
    elif path in FROM_STEWARD:
        sender = "steward"
    else:
        sender = "broker"
    req, resp = SCHEMAS.get(path, (None, None))
    return {"from": sender, "to": to, "method": method, "path": path, "schema": req or method,
            "payload": redact(payload or {}), "status": status, "resp_schema": resp,
            "response": redact(response) if response not in (None, {}, []) or resp else None}
