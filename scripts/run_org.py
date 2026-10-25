"""The campus hierarchy as one process: the ten Dining and Rec center mascots and every role agent above them
(seeds/org.py), each on its own port, sharing one story clock. scripts/run_all.py starts it; on its own:

    python -m scripts.run_org

Every agent still has its own app, state and (for mascots) its own SQLite file; they just share an event loop.
Their messages and events are copied to the broker, so the commons, the org chart and the agent graph show them.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import uvicorn

from agents.mascot import create_app as mascot_app
from core.net import RUNTIME, Net, registry
from org.app import Clock
from org.app import create_app as org_app
from seeds.org import DEPARTMENTS, ORG_STUDENTS, members


def ports() -> dict[str, int]:
    """Where each campus agent listens: students on 8721+, roles on 8731+ (the Library manager is the Steward)."""
    from seeds.org import ROLES

    out = {s["id"]: 8721 + i for i, s in enumerate(ORG_STUDENTS)}
    out |= {r: 8731 + i for i, r in enumerate(r for r in ROLES if r != "steward")}
    return out


async def main() -> None:
    reg = registry()
    org = reg["org"]
    broker = reg["broker"]
    client = httpx.AsyncClient(timeout=10)
    queue: asyncio.Queue = asyncio.Queue()

    def emit(type_: str, **data) -> dict:
        ev = {"type": type_, **data}
        queue.put_nowait(ev)  # one sender keeps the broker's stream in order
        return ev

    async def sender() -> None:
        while True:
            ev = await queue.get()
            try:
                await client.post(f"{broker}/admin/event", json=ev)
            except httpx.HTTPError:
                pass

    clock = Clock()
    apps = {}
    for s in ORG_STUDENTS:
        d = DEPARTMENTS[s["dept"]]
        dreg = {"agents": {m: org.get(m) or reg["agents"][m] for m in members(s["dept"])}, "broker": org[d["lead"]],
                "steward": org[d["manager"]], "bot": reg["bot"], "org": org, "coordinators": reg["coordinators"]}
        net = Net()
        net.report_to(broker)
        apps[s["id"]] = mascot_app(s["id"], RUNTIME / f"mascot_{s['id']}.db", net, dreg)
    for r in ports():
        if r in apps:
            continue
        net = Net()
        net.report_to(broker, sender=r)
        apps[r] = org_app(r, net, reg, emit, clock)

    servers = []
    for who, port in ports().items():
        server = uvicorn.Server(uvicorn.Config(apps[who], host="127.0.0.1", port=port, log_level="warning"))
        server.install_signal_handlers = lambda: None  # one process, many servers: Ctrl+C stops them together
        servers.append(server)
    await asyncio.gather(sender(), *(s.serve() for s in servers))


if __name__ == "__main__":
    os.environ.setdefault("TAGOUT_DEBUG", "1")
    asyncio.run(main())
