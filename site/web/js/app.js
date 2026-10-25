/* Tag Out commons: the mascots live in the world (web/js/world.js); this file turns the broker's public event
   stream (SSE) into what they do, and keeps the roster, log, numbers and (synthetic demo only) the chats. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const PEOPLE = ["ana", "ben", "dev", "priya", "zoe", "marco"];
  const JUDGE = location.pathname.startsWith("/judge");
  const MONDAY = new Date("2026-10-26T00:00:00-07:00");
  const ROLE_KEY = "tagout.as";
  const QUICK = ["I'm sick, can't make it today", "dentist Thu 3pm", "I want more hours this week",
    "set up a meeting with my supervisor", "the printer at the desk is broken"];
  // every field name the closed schemas in core/wire.py allow; anything else crossing would be a leak
  const ALLOWED = new Set(["agent_id", "badges", "ballot", "case_id", "category", "deadline", "employer", "end", "from_agent",
    "going", "issue_id", "items", "iteration", "kind", "level", "meeting_id", "minutes", "monday", "moves", "name", "ok",
    "outcome", "owner", "pet_id", "phase", "question_id", "request_id", "ring_id", "role", "round_id", "rule",
    "seen_version", "shift_id", "slots", "start", "state", "text", "title", "to_agent", "trades_made", "txn_id", "urgent",
    "version", "vote", "you_give", "agent_id"]);
  const leak = { msgs: 0, fields: 0, hits: 0, labels: null };
  const wireLog = []; // recent wire events, so the graph can list what crossed before it was opened
  let flow = null;

  const S = {
    debug: false, names: {}, pets: {}, petMeta: [], roster: {}, requested: new Set(), moved: {}, open: new Set(),
    votes: {}, summary: null, committed: [], gathered: new Set(), checks: 0, passed: 0, view: null,
  };
  let world = null;
  const BOOT = Date.now();
  const requesters = new Set(); // mascots whose student asked for a trade this week
  let live = false; // events replayed from history update state but don't animate

  // ---------- formatting ----------
  const pad = (n) => String(n).padStart(2, "0");
  const hourLabel = (d) => { const h = d.getHours() % 12 || 12; return d.getMinutes() ? `${h}:${pad(d.getMinutes())}` : `${h}`; };
  const dayOf = (d) => DAYS[(d.getDay() + 6) % 7];
  function span(ref, short) {
    const s = new Date(ref.start), e = new Date(ref.end), ap = (d) => (d.getHours() >= 12 ? "PM" : "AM");
    if (short) return `${hourLabel(s)}–${hourLabel(e)}${ap(e) === "PM" ? "p" : "a"}`;
    if (ap(s) !== ap(e) && e.getHours() !== 12) return `${dayOf(s)} ${hourLabel(s)} ${ap(s)}–${hourLabel(e)} ${ap(e)}`;
    return `${dayOf(s)} ${hourLabel(s)}–${hourLabel(e)} ${ap(e)}`;
  }
  const shiftLabel = (id) => (S.roster[id] ? span(S.roster[id]) : id);
  const shortLabel = (id) => { const r = S.roster[id]; return r ? `${dayOf(new Date(r.start))} ${span(r, true)}` : id; };
  const ORGN = {}; // the campus hierarchy's people (seeds/org.py), filled from /org
  const name = (id) => S.names[id] || ORGN[id] || (id === "steward" ? "the manager" : id);
  const cap = (s) => s[0].toUpperCase() + s.slice(1);
  function listNames(ids) { const n = ids.map(name); return n.length < 2 ? n.join("") : n.slice(0, -1).join(", ") + " and " + n[n.length - 1]; }
  const money = (v) => "$" + Math.round(v).toLocaleString("en-US");
  const clock = (iso) => { const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const store = { get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (_) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* private mode */ } } };

  // ---------- hosted replay: a recording of the real system (scripts/record.py) instead of a live broker ----------
  const STATIC = !!window.TAGOUT_STATIC;
  const R = { recs: {}, cur: null, i: 0, clock: "", timer: 0, stop: Infinity };
  async function loadRec(name) {
    if (!R.recs[name]) R.recs[name] = await fetch(`data/${name}.json`).then((r) => r.json());
    return R.recs[name];
  }
  function staticGet(path) {
    const p = path.split("?")[0];
    const m = p.match(/^\/phone\/(\w+)$/);
    if (m) {
      const all = (R.cur && R.cur.phones[m[1]]) || [], now = R.clock ? Date.parse(R.clock) + 999 : -1;
      return { messages: all.filter((x) => Date.parse(x.ts) <= now) };
    }
    let snap = R.cur.checkpoints[0].snap;
    R.cur.checkpoints.forEach((c) => { if (c.n <= R.i) snap = c.snap; });
    if (!(p in snap)) throw new Error(p + " is not in the recording");
    return snap[p];
  }
  // what a judge's action replays: the recorded real run of that same action
  // [recording, replay from this step, up to this step, note]: each action replays just its own segment
  const REPLAY = { "/demo/sunday": ["tour", null, "week"], "/demo/run": ["tour", null, "week"], "/demo/break": ["breakit"],
    "/demo/snoop": ["tour", "supervisor-meeting", "snoop"],
    "/manager/extra": ["tour", "callout", "extra", "Replaying the recorded run: the manager posted Thu 6-10 PM and every mascot was offered it."],
    "/manager/meeting": ["tour", "issue", "team-meeting", "Replaying the recorded run: the manager looked for a team meeting time."],
    "/demo/org/morning": ["org", null, null, "Replaying the recorded morning: a call-out nobody could cover, a safety report and an F-1 question."],
    "/demo/org/safety": ["org", "callout", "safety", "Replaying the recorded safety report: Tess told her mascot the fire exit was blocked."],
    "/demo/org/question": ["org", "safety", "question", "Replaying the recorded question: Kofi asked his mascot about winter-break hours on his F-1."] };
  const CHIP = { sick: ["tour", "week", "callout", "Replaying the recorded call-out: Ben texted that he woke up sick."],
    printer: ["tour", "extra", "issue", "Replaying the recorded report: Ana told her mascot the printer was broken."],
    supervisor: ["tour", "team-meeting", "supervisor-meeting", "Replaying the recorded request: Priya asked for a meeting with her supervisor."] };
  function staticPost(path, body) {
    if (REPLAY[path]) { const [name, from, until, note] = REPLAY[path]; if (note) toast(note); return play(name, from, until); }
    if (path === "/admin/reset") return play(null);
    const text = ((body && body.text) || "").toLowerCase();
    const chip = text.includes("sick") ? CHIP.sick : text.includes("printer") || text.includes("broken") ? CHIP.printer : text.includes("supervisor") ? CHIP.supervisor : null;
    if (chip) { toast(chip[3]); return play(chip[0], chip[1], chip[2]); }
    const typed = path.match(/^\/phone\/(\w+)\/text$/);
    if (typed && text) return liveTry(typed[1], body.text);
    toast("This hosted page replays a recording of the real agents. Type a message to a student's mascot to run them live.");
    return {};
  }
  // your own message: the real system runs once on the server (site/api/try.py) and the page replays what it did
  async function liveTry(who, text) {
    toast(`Running the real agents with your message to ${name(who)}'s mascot. This takes about 10 seconds.`);
    let rec;
    try {
      const r = await fetch("/api/try", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ who, text }) });
      if (!r.ok) throw new Error(String(r.status));
      rec = await r.json();
    } catch (e) { toast("Couldn't reach the live agents just now. The recorded replay still works."); return {}; }
    R.recs.try = rec;
    toast(`Done: the agents handled your message live (${rec.events.length} events this run). Replaying what happened.`);
    return play("try", "week", "try");
  }
  async function play(name, from, until) {
    clearTimeout(R.timer);
    if (name) R.cur = await loadRec(name);
    const at = (label) => (R.cur.checkpoints.find((c) => c.label === label) || {}).n;
    const evs = R.cur.events, start = from ? at(from) || 0 : 0;
    R.stop = until ? at(until) || evs.length : evs.length;
    R.i = 0; R.clock = "";
    live = false;
    onEvent({ type: "reset", n: 0, ts: evs[0] ? evs[0].ts : new Date().toISOString() });
    for (; R.i < start; R.i++) { R.clock = evs[R.i].ts; onEvent(evs[R.i]); } // fast-forward without animation
    live = true;
    if (name) tick();
    return {};
  }
  function tick() {
    const evs = R.cur.events;
    if (R.i >= Math.min(evs.length, R.stop)) return;
    const ev = evs[R.i]; R.clock = ev.ts; R.i++;
    onEvent(ev);
    const next = evs[R.i];
    if (next) R.timer = setTimeout(tick, Math.min(2200, Math.max(25, Date.parse(next.ts) - Date.parse(ev.ts))));
  }
  let toastTimer = 0;
  function toast(text) {
    let el = $("#toast");
    if (!el) { el = document.createElement("div"); el.id = "toast"; el.className = "toast"; el.setAttribute("role", "status"); document.body.appendChild(el); }
    el.textContent = text; el.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 6000);
  }

  // ---------- API ----------
  async function get(path) {
    if (STATIC) return staticGet(path);
    const r = await fetch(path); if (!r.ok) throw new Error(path + " " + r.status); return r.json();
  }
  async function post(path, body) {
    if (STATIC) return staticPost(path, body);
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(data.detail || path + " " + r.status), { status: r.status });
    return data;
  }

  // ---------- the world ----------
  const on = () => world && live;
  const W = {
    say: (a, t, ms) => on() && world.say(a, `${name(a)}: ${t}`, ms), status: (a, t) => on() && world.status(a, t),
    play: (a, st, o) => on() && world.play(a, st, o), face: (a, b) => on() && world.face(a, b),
    link: (f, t, o) => on() && world.link(f, t, o), clear: (st) => world && world.clearLinks(st),
    badge: (a, v) => world && (live || v === null) && world.badge(a, v),
    gather(ids) { if (!on()) return; ids.forEach((i) => S.gathered.add(i)); world.gather([...S.gathered].sort((x, y) => PEOPLE.indexOf(x) - PEOPLE.indexOf(y))); },
    release(ids) { if (!world) return; (ids || [...S.gathered]).forEach((i) => S.gathered.delete(i)); world.release(ids); },
  };
  function setStatus(html) { $("#roundStatus").innerHTML = html; }

  function onEvent(ev) {
    live = live || Date.parse(ev.ts) > BOOT - 1500;
    if (ev.type === "wire") { feedWire(ev); return; }
    if (ev.type.startsWith("org_")) { orgFeed(ev); return; }
    if (flow && live) flowState(ev);
    switch (ev.type) {
      case "reset":
        orgLog.length = 0; if (org) org.reset();
        Object.assign(S, { requested: new Set(), moved: {}, open: new Set(), votes: {}, summary: null, committed: [], checks: 0, passed: 0 });
        requesters.clear();
        $("#events").innerHTML = ""; $("#logCount").textContent = "0 items";
        W.clear(); W.release(PEOPLE); PEOPLE.forEach((a) => { W.badge(a, null); W.status(a, ""); W.face(a, null); });
        refreshRoster(); setStatus("Reset. The mascots are hanging out until Sunday's check."); setFinding(null); renderKpis(); break;
      case "sunday_check":
        ev.agents.forEach((a, i) => setTimeout(() => { W.play(a, "review"); W.say(a, "Checking next week…", 2600); }, i * 180));
        setTimeout(() => { if (world) world.release(PEOPLE.filter((a) => !S.gathered.has(a) && !requesters.has(a))); }, 3400);
        setStatus("Sunday check: each mascot compares next week with its own student's calendar."); break;
      case "trade_request":
        S.requested.add(ev.shift_id); requesters.add(ev.agent); W.status(ev.agent, ev.urgent ? "called out" : "wants a trade"); W.play(ev.agent, "waiting");
        if (ev.urgent) { W.say(ev.agent, "Can someone take my shift today?", 3200); setStatus(`${name(ev.agent)} called out of ${shiftLabel(ev.shift_id)}. The round opens now, not on Sunday.`); }
        renderKpis(); scheduleBoard(); break;
      case "round_open":
        ev.items.forEach((r) => { S.roster[r.shift_id] = S.roster[r.shift_id] || r; });
        W.clear("pick");
        setStatus(`<b>${ev.items.length} shifts</b> up for trade. The mascots who asked walk to the table.`); break;
      case "round":
        W.gather(ev.agents); W.clear("pick");
        ev.agents.forEach((a) => { W.status(a, "thinking"); W.play(a, "review"); });
        setStatus(`${cap(ev.phase)} round ${ev.iteration}: ${ev.agents.length} answering. Replies are held to the deadline and shown together.`); break;
      case "picks": {
        const picks = Object.entries(ev.picks);
        picks.forEach(([a, sid]) => {
          const owner = sid && S.roster[sid] ? S.roster[sid].owner : null;
          if (owner) { W.play(a, "jumping", { then: "idle" }); W.status(a, "picked " + shortLabel(sid)); W.face(a, owner); W.link(a, owner, { style: "pick", label: shortLabel(sid) }); }
          else { W.play(a, "waiting"); W.status(a, JUDGE && S.debug ? "passed" : ""); }
        });
        const n = picks.filter(([, s]) => s).length;
        setStatus(`Round ${ev.iteration}: <b>${n} pick${n === 1 ? "" : "s"}</b>, ${picks.length - n} pass${picks.length - n === 1 ? "" : "es"}. A pass looks the same whatever the reason.`);
        break;
      }
      case "released": ev.agents.forEach((a) => W.status(a, "keeps own shift")); break;
      case "counter_window":
        setStatus(`No ring yet. <b>Counter-offer window</b>: ${ev.seconds} s for any mascot that asked its student.`); break;
      case "cycle":
        W.clear("pick");
        ev.moves.forEach((m) => { W.link(m.to_agent, m.from_agent, { style: "ring", label: shortLabel(m.shift_id) }); W.face(m.to_agent, m.from_agent); });
        ev.members.forEach((a) => { W.status(a, "in a ring"); W.play(a, "idle"); });
        W.say(ev.members[0], "That works for all of us!", 2600);
        setStatus(`A <b>${ev.members.length}-way ring</b> closed: ${listNames(ev.members)}. Everyone keeps their hours.`); break;
      case "chain": {
        W.clear("pick");
        const helper = ev.moves[0].to_agent;
        W.gather([helper]);
        ev.moves.forEach((m) => W.link(m.to_agent, m.from_agent, { style: "chain", label: shortLabel(m.shift_id) }));
        W.say(helper, ev.moves.length === 1 ? "I can cover that one." : "I'll start a chain.", 2400);
        setStatus(ev.moves.length === 1 ? `${name(helper)} offers to cover ${name(ev.moves[0].from_agent)}'s ${shiftLabel(ev.moves[0].shift_id)}.`
          : `A cover chain formed through ${listNames([helper, ...ev.moves.map((m) => m.from_agent)])}.`);
        break;
      }
      case "validated":
        S.checks += ev.checks || 0; S.passed += ev.passed || 0; renderKpis(); break;
      case "selected":
        setStatus(`Every member re-checked the exact trade privately. CP-SAT kept <b>${ev.proposals.length}</b> (${ev.status.toLowerCase()}).`); break;
      case "prepare":
        S.votes[ev.txn_id] = {};
        ev.members.forEach((a) => { W.status(a, "asked to confirm"); W.badge(a, null); W.play(a, "waiting"); });
        setStatus(`Waiting for ${listNames(ev.members)} and the manager to confirm. Shifts are on hold.`); break;
      case "vote":
        (S.votes[ev.txn_id] = S.votes[ev.txn_id] || {})[ev.agent] = ev.vote;
        if (ev.agent === "steward" || (ev.vote === "no" && !(JUDGE && S.debug))) break;  // a "no" stays anonymous on the commons
        W.badge(ev.agent, ev.vote === "yes" ? "yes" : "no");
        W.status(ev.agent, { yes: "confirmed", no: "declined", stale: "week changed", timeout: "no answer" }[ev.vote]);
        if (ev.vote === "yes") W.play(ev.agent, "jumping", { then: "idle" });
        break;
      case "commit": {
        const ring = ev.proposal.startsWith("ring");
        ev.moves.forEach((m, i) => {
          S.moved[m.shift_id] = ring || i > 0 ? "moved" : "covered"; S.requested.delete(m.shift_id);
          if (S.roster[m.shift_id]) S.roster[m.shift_id] = { ...S.roster[m.shift_id], owner: m.to_agent };
        });
        ev.members.forEach((a, i) => setTimeout(() => { W.play(a, "waving", { then: "idle" }); W.status(a, "traded"); }, i * 120));
        W.say(ev.members[ev.members.length - 1], ring ? "Trade done, pay kept." : "Covered!", 2600);
        S.committed.push(ev);
        setStatus(`<b>Committed.</b> Every student and the manager said yes. ${ev.moves.length} shift${ev.moves.length > 1 ? "s" : ""} moved.`);
        setTimeout(() => { ev.members.forEach((a) => { W.badge(a, null); W.face(a, null); }); W.release(ev.members); }, 3200);
        renderBoard(); break;
      }
      case "abort":
        W.clear(); ev.moves.forEach((m) => W.link(m.to_agent, m.from_agent, { style: "abort", label: shortLabel(m.shift_id) }));
        ev.members.forEach((a) => { W.play(a, "failed", { then: "idle" }); W.status(a, "nothing moved"); W.badge(a, null); });
        setStatus("<b>Aborted.</b> A week changed before commit, so nothing moved. Trying again with fresh data.");
        setTimeout(() => W.clear("abort"), 2600); break;
      case "schedule_edited":
        W.status(ev.agent, "week changed"); W.say(ev.agent, "My week just changed.", 2400); break;
      case "pet_changed":
        S.pets[ev.agent] = ev.pet_id; if (world) world.setPet(ev.agent, ev.pet_id);
        renderTabs(); renderBoard(); break;
      case "summary":
        (ev.open_shifts || []).forEach((s) => S.open.add(s));
        if (ev.kind === "extra") {
          setStatus(ev.taker ? `Extra shift taken by <b>${name(ev.taker)}</b>, whose mascot checked every limit in private.` : "Nobody could take the extra shift safely.");
          renderBoard();
        } else if (ev.kind === "callout") {
          setStatus(ev.fixed ? `Call-out covered: <b>${ev.fixed} of ${ev.asked}</b>, confirmed by everyone and the manager.` : "Nobody could take the call-out safely. It went to the manager as an open shift.");
          renderBoard();
        } else {
          S.summary = ev;
          setStatus(`Week done: <b>${ev.fixed} of ${ev.asked}</b> fixed.`);
          renderKpis(); setFinding(ev); renderBoard();
        }
        setTimeout(() => { W.clear(); W.release(PEOPLE); requesters.clear(); PEOPLE.forEach((a) => W.status(a, "")); }, 4500); break;
    }
    logEvent(ev);
  }

  function setFinding(sum) {
    const el = $("#finding");
    if (!sum) { el.textContent = "Every student has a mascot that knows their week. On Sunday the mascots check for collisions and trade shifts so nobody loses pay or breaks a limit their employer can't see."; return; }
    const parts = [];
    S.committed.filter((c) => c.proposal.startsWith("ring")).forEach((c) => parts.push(`${listNames(c.members)} traded in a <b>${c.members.length}-way ring</b> and kept their pay`));
    S.committed.filter((c) => c.proposal.startsWith("chain")).forEach((c) => {
      if (c.moves.length === 1) parts.push(`${name(c.moves[0].to_agent)} covered ${name(c.moves[0].from_agent)}'s ${shiftLabel(c.moves[0].shift_id)}`);
      else parts.push(`a chain through ${listNames(c.members)} fixed ${c.moves.length}`);
    });
    let text = parts.length ? cap(parts.join("; ")) + "." : "No trade went through this week.";
    (sum.open_shifts || []).forEach((s) => { const r = S.roster[s]; text += ` ${r ? name(r.owner) + "'s " : ""}${shiftLabel(s)} has no safe trade, so the manager sees it as an open shift.`; });
    el.innerHTML = text;
  }

  function renderKpis() {
    const s = S.summary;
    $("#kFixed").innerHTML = `${s ? s.fixed : 0}<small> of ${s ? s.asked : S.requested.size}</small>`;
    $("#kPay").textContent = money(s ? s.pay_kept : 0);
    $("#kChecks").innerHTML = S.checks ? `${S.passed}<small> of ${S.checks} passed</small>` : "0";
    const open = s ? s.open : 0;
    $("#kOpen").textContent = String(open); $("#kOpen").classList.toggle("bad", open > 0);
  }

  // ---------- log ----------
  function sentence(ev) {
    const m = (x) => `${name(x.to_agent)} takes ${name(x.from_agent)}'s ${shiftLabel(x.shift_id)}`;
    switch (ev.type) {
      case "sunday_check": return "Sunday check sent to every mascot.";
      case "trade_request": return ev.urgent ? `${name(ev.agent)} called out of ${shiftLabel(ev.shift_id)} (same day). No reason attached.` : `${name(ev.agent)} asked for a trade on ${shiftLabel(ev.shift_id)}. No reason attached.`;
      case "picks": {
        const p = Object.entries(ev.picks);
        const picked = p.filter(([, s]) => s).map(([a, s]) => `${name(a)} → ${shiftLabel(s)}`);
        const passed = p.filter(([, s]) => !s).map(([a]) => name(a));
        // the commons only counts passes: who passed is judge-view detail, so a coworker can't read a "no" off the log
        const passes = JUDGE && S.debug ? `passed: ${passed.join(", ")}` : `${passed.length} passed`;
        return `${cap(ev.phase)} round ${ev.iteration}: ${picked.length ? picked.join(", ") : "no picks"}${passed.length ? `; ${passes}` : ""}.`;
      }
      case "counter_window": return `No ring closed. Counter-offer window, ${ev.seconds} s.`;
      case "cycle": return `<span class="tr">Ring closed</span>: ${ev.moves.map(m).join("; ")}.`;
      case "chain": return `<span class="tr">Chain</span>: ${ev.moves.map(m).join("; ")}.`;
      case "selected": return `CP-SAT kept ${ev.proposals.length} of ${ev.proposals.length + ev.dropped.length} proposals (${ev.status}).`;
      case "prepare": return `Prepare ${ev.txn_id}: holds placed, asking ${listNames(ev.members)} and the manager.`;
      case "vote": {
        const word = { yes: "confirmed", no: "declined", stale: "week changed (stale)", timeout: "timed out" }[ev.vote];
        const who = ev.vote !== "no" || (JUDGE && S.debug) ? cap(name(ev.agent)) : "Someone in the trade";
        return `${who} <span class="${ev.vote === "yes" ? "ok" : "bad"}">${word}</span>.`;
      }
      case "commit": return `<span class="ok">Committed</span> ${ev.txn_id}: ${ev.moves.map(m).join("; ")}.`;
      case "abort": return `<span class="bad">Aborted</span> ${ev.txn_id}. Holds released, shifts unchanged.`;
      case "schedule_edited": return `${name(ev.agent)}'s week changed while the trade waited for confirmations.`;
      case "pet_changed": return `${name(ev.agent)} picked a new mascot.`;
      case "summary":
        if (ev.kind === "callout") return `Call-out round done: ${ev.fixed ? "covered" : "no safe taker, sent to the manager"}.`;
        if (ev.kind === "extra") return ev.taker ? `Extra shift ${shiftLabel(ev.shift_id)} taken by ${name(ev.taker)}.` : `Nobody could take the extra shift ${shiftLabel(ev.shift_id)} safely.`;
        return `Week done: ${ev.fixed} of ${ev.asked} fixed, ${money(ev.pay_kept)} of pay kept by trading, ${ev.open} open.`;
      case "extra_open": return `The manager posted an extra shift. Every mascot is offered it.`;
      case "snoop": if (ev.results) showSnoop(ev.results); return `A nosy broker asked every mascot why it passed. The schemas rejected every question.`;
      case "reset": return "Demo reset.";
      case "org_escalate": return `<span class="tr">Moved up</span>: ${name(ev.frm)} → ${name(ev.to)} (${{ no_cover_2h: "no cover in 2 h", no_answer_30m: "no answer in 30 min", safety_first: "safety report" }[ev.rule] || ev.rule}).`;
      case "org_done": return ev.outcome === "covered" ? `<span class="ok">Covered</span> by ${name(ev.taker)}, approved by ${name(ev.by)}.` : `${name(ev.by)}: <span class="ok">${ev.outcome}</span>.`;
      default: return null;
    }
  }
  function meta(ev) {
    const pub = JUDGE && S.debug;
    const movers = (moves) => listNames([...new Set((moves || []).flatMap((x) => [x.from_agent, x.to_agent]).filter((a) => a !== "open"))]);
    switch (ev.type) {
      case "sunday_check": return ["Broker", "Sent"];
      case "trade_request": return [name(ev.agent), ev.urgent ? "Call-out" : "Asked"];
      case "picks": return ["Mascots", "Answered"];
      case "counter_window": return ["Broker", "Waiting"];
      case "cycle": return [movers(ev.moves), "Proposed"];
      case "chain": return [movers(ev.moves), "Proposed"];
      case "selected": return ["CP-SAT", `Kept ${ev.proposals.length}`];
      case "prepare": return [listNames(ev.members), "Waiting"];
      case "vote": return [ev.agent === "steward" ? "Manager" : ev.vote !== "no" || pub ? name(ev.agent) : "Someone",
        { yes: "Confirmed", no: "Declined", stale: "Stale", timeout: "Timed out" }[ev.vote]];
      case "commit": return [movers(ev.moves), "Committed"];
      case "abort": return [listNames(ev.members), "Aborted"];
      case "summary": return ["Broker", "Done"];
      case "extra_open": return ["Manager", "Posted"];
      case "snoop": return ["Judge", "Refused"];
      case "org_escalate": return [name(ev.to), "Moved up"];
      case "org_done": return [name(ev.by), "Done"];
      case "schedule_edited": return [name(ev.agent), "Changed"];
      default: return ["", ""];
    }
  }
  function logEvent(ev) {
    const text = sentence(ev);
    if (!text) return;
    const [who, status] = meta(ev);
    const tone = /Confirmed|Committed|Done|Refused/.test(status) ? "ok" : /Declined|Aborted|Stale|Timed/.test(status) ? "bad" : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="t">${clock(ev.ts)}</td><td>${text}</td><td class="who">${esc(who)}</td><td class="st ${tone}">${esc(status)}</td>`;
    $("#events").prepend(tr);
    $("#logCount").textContent = `${$("#events").children.length} items`;
  }

  // ---------- roster board ----------
  let boardTimer = 0;
  const scheduleBoard = () => { clearTimeout(boardTimer); boardTimer = setTimeout(renderBoard, 150); };
  async function refreshRoster() {
    try {
      const st = await get("/state");
      S.roster = {}; st.roster.forEach((r) => { S.roster[r.shift_id] = r; });
      Object.values(st.agents).forEach((a) => { S.pets[a.agent_id] = a.pet_id; });
      renderBoard();
    } catch (_) { /* broker restarting */ }
  }
  function renderBoard(target = "#board") {
    const html = ['<div class="day" role="columnheader"></div>'];
    DAYS.forEach((d, i) => html.push(`<div class="day" role="columnheader">${d} ${new Date(MONDAY.getTime() + i * 864e5).getDate()}</div>`));
    const end = new Date(MONDAY.getTime() + 7 * 864e5);
    for (const p of PEOPLE) {
      if (!(p in S.names)) continue;
      html.push(`<div class="who" role="rowheader"><canvas data-pet="${esc(S.pets[p] || "")}"></canvas><span>${S.names[p]}</span></div>`);
      for (let i = 0; i < 7; i++) {
        const chips = Object.values(S.roster).filter((r) => { const s = new Date(r.start); return r.owner === p && (s.getDay() + 6) % 7 === i && s >= MONDAY && s < end; })
          .sort((a, b) => new Date(a.start) - new Date(b.start)).map((r) => {
            const id = r.shift_id, cls = S.open.has(id) ? "open" : S.moved[id] || (S.requested.has(id) ? "req" : "");
            const title = { open: "no safe trade; still scheduled", moved: "traded in", covered: "covered", req: "wants a trade" }[cls] || "shift";
            return `<span class="chip ${cls}" title="${span(r)}: ${title}">${S.open.has(id) ? "no trade" : span(r, true)}</span>`;
          }).join("");
        html.push(`<div class="cell" role="cell">${chips}</div>`);
      }
    }
    $(target).innerHTML = html.join("");
    $(target).querySelectorAll("canvas").forEach((c) => Sprites.badge(c, c.dataset.pet || "debug-duck-v2", "idle"));
    if (target === "#board" && S.view === "manager") renderBoard("#mgrBoard");
  }

  // ---------- chats (synthetic demo: the owner channel relayed by the broker) ----------
  function bubbles(msgs, fresh) {
    let lastButtons = -1;
    msgs.forEach((m, i) => { if (m.buttons && m.buttons.length) lastButtons = i; });
    const answered = msgs.slice(lastButtons + 1).some((m) => m.kind === "reply");
    return msgs.map((m, i) => {
      const cls = m.kind === "student" ? "msg me" : m.kind === "reply" ? "msg reply" : "msg";
      const live = !STATIC && i === lastButtons && !answered;
      const btns = (m.buttons || []).length ? `<div class="btns">${m.buttons.map((b) => `<button type="button" data-data="${esc(b.data)}"${live ? "" : " disabled"}>${esc(b.label)}</button>`).join("")}</div>` : "";
      return `<div class="${cls}${fresh && i === msgs.length - 1 ? " flash" : ""}">${esc(m.text)}${btns}</div>`;
    }).join("");
  }
  function wireButtons(container, who, refresh) {
    container.querySelectorAll("button[data-data]").forEach((b) => b.addEventListener("click", async () => {
      b.closest(".btns").querySelectorAll("button").forEach((x) => (x.disabled = true));
      await post(`/phone/${who}/tap`, { data: b.dataset.data }).catch(() => {});
      refresh();
    }));
  }
  const chat = { count: -1, who: "ana" };
  function renderTabs() {
    const tabs = $("#whoTabs");
    tabs.innerHTML = PEOPLE.filter((p) => p in S.names).map((p) => `<button type="button" role="tab" data-who="${p}" aria-selected="${p === chat.who}"><canvas data-pet="${esc(S.pets[p] || "")}"></canvas>${S.names[p]}</button>`).join("")
      + `<button type="button" role="tab" class="mgr" data-who="manager" aria-selected="${chat.who === "manager"}">Manager</button>`;
    tabs.querySelectorAll("canvas").forEach((c) => Sprites.badge(c, c.dataset.pet || "debug-duck-v2", "idle"));
    tabs.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => openChat(b.dataset.who)));
  }
  function openChat(who) {
    chat.who = who; chat.count = -1; store.set("tagout.chat", who);
    $("#assistantSub").textContent = who === "manager" ? "Demo: the Library manager's approval cards." : `Demo with synthetic students: you're viewing ${S.names[who]}'s private chat. In real use only ${S.names[who]} can open it (on Telegram or through Cubbie).`;
    $("#compose").hidden = who === "manager";
    renderTabs(); pollChat();
  }
  async function pollChat() {
    let data;
    try { data = await get(`/phone/${chat.who}`); } catch (_) { return; }
    const msgs = data.messages || [];
    if (msgs.length === chat.count) return;
    const fresh = chat.count >= 0 && msgs.length > chat.count;
    chat.count = msgs.length;
    const thread = $("#thread");
    thread.innerHTML = msgs.length ? bubbles(msgs, fresh) : `<p class="empty">${chat.who === "manager" ? "Trade requests land here." : "Nothing yet. The mascot only texts when something in the week collides."}</p>`;
    wireButtons(thread, chat.who, pollChat);
    thread.scrollTop = thread.scrollHeight;
  }

  // phones row (judge view): four threads side by side
  const phones = [];
  function buildPhones() {
    $("#phonesRow").hidden = false;
    const wrap = $("#phones"); wrap.innerHTML = "";
    ["ana", "ben", "dev", "manager"].forEach((who) => {
      const el = document.createElement("article");
      el.className = "phone";
      el.innerHTML = `<header class="phone-head"><div><div class="who">${who === "manager" ? "Library manager" : S.names[who] + "'s phone"}</div><div class="sub">Telegram</div></div></header><div class="thread"></div>`;
      wrap.appendChild(el);
      const st = { who, el, count: -1 };
      st.poll = async () => {
        let d; try { d = await get(`/phone/${who}`); } catch (_) { return; }
        const msgs = d.messages || []; if (msgs.length === st.count) return;
        const fresh = st.count >= 0 && msgs.length > st.count; st.count = msgs.length;
        const t = el.querySelector(".thread"); t.innerHTML = msgs.length ? bubbles(msgs, fresh) : '<p class="empty">No messages.</p>';
        wireButtons(t, who, st.poll); t.scrollTop = t.scrollHeight;
      };
      phones.push(st);
    });
  }

  // ---------- pet gallery ----------
  async function searchPets() {
    const q = $("#petQuery").value.trim();
    $("#petGrid").innerHTML = '<p class="muted">Searching codex-pets.net…</p>';
    let d;
    try { d = await get(`/pets/search?q=${encodeURIComponent(q)}`); } catch (_) { $("#petGrid").innerHTML = '<p class="muted">Couldn\'t reach codex-pets.net.</p>'; return; }
    const taken = new Map(Object.entries(S.pets).map(([a, p]) => [p, a]));
    $("#petGrid").innerHTML = d.pets.map((p) => {
      const owner = taken.get(p.id), mine = owner === $("#petFor").value;
      return `<button type="button" class="pet-card" data-id="${esc(p.id)}" data-sheet="${esc(p.sheet || "")}" ${owner && !mine ? 'aria-disabled="true"' : ""}>
        <img src="${esc(p.poster)}" alt="" loading="lazy"><span class="n">${esc(p.name)}</span>
        <span class="c">${owner ? (mine ? "current pick" : `${esc(name(owner))}'s`) : "by " + esc(p.creator || "unknown")}</span></button>`;
    }).join("") || '<p class="muted">No pets found.</p>';
    $("#petGrid").querySelectorAll(".pet-card").forEach((b) => b.addEventListener("click", () => usePet(b)));
  }
  async function usePet(card) {
    if (card.getAttribute("aria-disabled") === "true") return;
    const agent = $("#petFor").value;
    $("#petNote").textContent = `Getting ${card.querySelector(".n").textContent} for ${name(agent)}…`;
    try {
      await post("/pets/use", { agent, pet_id: card.dataset.id, sheet: card.dataset.sheet });
      $("#petNote").textContent = `${name(agent)} now has ${card.querySelector(".n").textContent}.`;
      searchPets();
    } catch (e) { $("#petNote").textContent = e.message; }
  }
  function openPets(forWho) {
    $("#petFor").innerHTML = PEOPLE.map((p) => `<option value="${p}"${p === forWho ? " selected" : ""}>${S.names[p]}</option>`).join("");
    $("#petDialog").showModal();
    if (!$("#petGrid").children.length) { $("#petQuery").value = "goku"; searchPets(); }
  }

  // ---------- simulation ----------
  async function renderSim() {
    let d;
    try { d = await get("/sim"); } catch (_) { $("#sim").innerHTML = '<p class="muted">Run <code>python -m sim.simulate</code> to fill this in.</p>'; return; }
    $("#simMeta").textContent = `${d.weeks.toLocaleString("en-US")} synthetic weeks, ${Math.round(d.conflict_rate * 100)}% of shifts collide`;
    const rows = [["Plain covers only", d.plain_pct, d.plain_pay_lost, ""],
      ["Group chat that also swaps, every volunteer checking all of their own limits", d.swap_pct ?? d.plain_pct, d.swap_pay_lost ?? d.plain_pay_lost, ""],
      ["Tag Out, automatically every Sunday", d.tagout_pct, d.tagout_pay_lost, "hue"]];
    const maxPay = Math.max(...rows.map((r) => r[2]));
    const bars = (i, max, fmt) => rows.map((r) => `<span class="muted">${r[0]}</span><span class="track"><span class="fill ${r[3]}" style="width:${100 * r[i] / max}%"></span></span><span class="v num">${fmt(r[i])}</span>`).join("");
    $("#sim").innerHTML = `
      <div><div class="bars wide" role="img" aria-label="Collisions fixed">
        <span>Collisions fixed</span><span></span><span></span>${bars(1, 100, (v) => v.toFixed(1) + "%")}
      </div>
      <p class="sim-note">Most of the gain over plain covers comes from two-person swaps; Tag Out adds ${d.extra_vs_swap != null ? d.extra_vs_swap.toFixed(1) : "–"} points over a chat where every volunteer checks all of their own limits correctly. What it adds is doing it privately and on its own, and checking each move: volunteers who check their hours by hand still make about ${(d.rule_breaks_hand_checked_per_week ?? d.rule_breaks_prevented_per_week ?? 1.4).toFixed(1)} limit-breaking covers a week on this roster, mostly from hours at other jobs, the 25-hour average and Work-Study dollars.</p></div>
      <div><div class="bars wide" role="img" aria-label="Pay lost per week">
        <span>Pay lost a week</span><span></span><span></span>${bars(2, maxPay, money)}
      </div>
      <p class="sim-note">Winter break (F-1 limit 40 h): ${d.winter.handed.toFixed(1)} of ${d.winter.wanted.toFixed(0)} shifts handed off a week, ${money(d.winter.kept)} kept on campus, ${d.winter.rule_breaks} rule breaks. <a href="https://github.com/neric-joel/tag-out/blob/main/docs/SIMULATION.md">Method and assumptions</a>.</p></div>`;
  }

  // ---------- judge view ----------
  async function renderJudge() {
    let d;
    try { d = await get("/admin/judge"); } catch (_) { return; }
    const ruleName = { f1_weekly_20: "F-1 20 h a week, on-campus jobs", f1_break_40: "F-1 40 h (break)", aca_25_avg: "ASU 25 h average", weekly_40: "40 h a week", fws_award: "Work-Study award" };
    const rows = Object.values(d).map((s) => {
      const hrs = (r) => (r.unit === "$" ? r.room / 16 : r.room);
      const bind = s.rooms.reduce((a, b) => (hrs(b) < hrs(a) ? b : a));
      const cover = hrs(bind) - 4;
      const other = Object.entries(s.other_employers).map(([k, v]) => `${v} h ${k}`).join(", ");
      return `<tr><td>${s.name}<span class="sub">${s.f1 ? "F-1" : "domestic"}${s.fws ? ", Work-Study" : ""}</span></td>
        <td class="num">${s.week_hours.toFixed(0)} h<span class="sub">${other ? "incl. " + other : "Library only"}</span></td>
        <td>${ruleName[bind.rule_id] || bind.rule_id}</td><td class="num">${bind.unit === "$" ? money(bind.room) : bind.room.toFixed(1) + " h"}</td>
        <td class="${cover < 0 ? "over" : ""}">${cover < 0 ? "would break it" : "fits"}</td></tr>`;
    }).join("");
    $("#limits").innerHTML = `<thead><tr><th>Student</th><th class="num">This week</th><th>Limit that binds first</th><th class="num">Room left</th><th>One more 4 h shift</th></tr></thead><tbody>${rows}</tbody>`;
    try {
      const b = await get("/admin/baseline");
      const rule = { f1_weekly_20: "F-1 20 h", aca_25_avg: "pushes 25 h average over", fws_award: "Work-Study award", weekly_40: "40 h" };
      $("#baseline").innerHTML = b.rows.length ? `<h3>The same week with a Library-only scheduler</h3>
        <p class="muted small">It sees availability and Library hours, like a typical shift app, but not other jobs or anyone's limits. It covers each shift with the free coworker who has the fewest Library hours.</p>
        <table class="limits"><thead><tr><th>Shift</th><th>Covered by</th><th class="num">Library sees</th><th class="num">Really</th><th>Breaks</th></tr></thead><tbody>
        ${b.rows.map((r) => `<tr><td>${name(r.owner)}'s ${shiftLabel(r.shift_id)}</td><td>${r.to ? name(r.to) : "nobody free"}</td>
          <td class="num">${r.library_view != null ? r.library_view + " h" : "–"}</td><td class="num">${r.real != null ? r.real + " h" : "–"}</td>
          <td class="${r.breaks && r.breaks.length ? "over" : ""}">${r.breaks && r.breaks.length ? r.breaks.map((x) => rule[x] || x).join(", ") : r.to ? "fits" : "–"}</td></tr>`).join("")}
        </tbody></table>
        <p class="sim-note">Library-only scheduler: ${b.violations} limit break${b.violations === 1 ? "" : "s"}, ${money(b.pay_lost)} of pay moved off the students who asked. Tag Out: 0 breaks found by any private re-check${S.summary ? `, ${money(S.summary.pay_kept)} of pay kept by trading` : ""}.</p>` : "";
    } catch (_) { /* not yet */ }
    renderForecast("#forecast");
  }

  async function renderForecast(sel) {
    try {
      const f = await get("/forecast");
      const lab = (slot) => { const m = slot.match(/^(\w{3}) (\d+)-(\d+)$/); if (!m) return slot; const h = (x) => (+x % 12) || 12; return `${m[1]} ${h(m[2])}–${h(m[3])} ${+m[3] >= 12 ? "PM" : "AM"}`; };
      const top = f.alerts.slice().sort((a, b) => b.busy - a.busy);
      $(sel).innerHTML = `<h3>Crunch forecast for the manager</h3>
        <p class="muted small" style="margin-bottom:8px">Counts only, shown when ${f.k} or more of ${f.staff} staff are busy. No names, no reasons.</p>
        <ul>${top.length ? top.slice(0, 4).map((a) => `<li><span>${lab(a.slot)}</span><span class="num">${a.busy} of ${a.staff} can't work</span></li>`).join("") : "<li><span>No crunch next week.</span><span></span></li>"}</ul>
        ${top.length > 4 ? `<p class="muted small" style="margin-top:6px">${top.length - 4} more slots with ${f.k} or more busy.</p>` : ""}`;
    } catch (_) { /* steward down */ }
  }

  // ---------- pages: sign in, a student's own page, the manager's page, how the agents talk ----------
  const VIEWS = { commons: "#viewCommons", me: "#viewStudent", manager: "#viewManager", org: "#viewOrg", agents: "#viewAgents" };
  const TAB = { commons: "#tabArena", me: "#tabMe", manager: "#tabMgr", org: "#tabOrg", agents: "#tabAgents" };
  const role = () => store.get(ROLE_KEY, null);
  function route() {
    let v = (location.hash || "#commons").slice(1);
    if (!(v in VIEWS) || JUDGE) v = "commons";
    // hosted replay: pages that show a week's results start from the finished week, not a blank one
    if (STATIC && R.i === 0 && (v === "me" || v === "manager" || JUDGE)) { play("tour", "week", "week").then(route); return; }
    if (v === "me" && !PEOPLE.includes(role())) { openSignIn(); v = S.view || "commons"; }
    if (v === "manager") store.set(ROLE_KEY, "manager");
    Object.entries(VIEWS).forEach(([k, sel]) => { $(sel).hidden = k !== v; });
    document.querySelectorAll(".tabs a").forEach((a) => a.removeAttribute("aria-current"));
    $(JUDGE ? "#tabJudge" : TAB[v]).setAttribute("aria-current", "page");
    S.view = v;
    renderPill();
    if (v === "me") { meChat.reset(role()); renderMe(); }
    if (v === "manager") renderMgr();
    if (v === "agents") ensureFlow();
    if (v === "org") ensureOrg();
    if (v === "commons" && world) world.setPetHeight(+store.get("tagout.size", 96));
  }
  function renderPill() {
    const r = role();
    $("#whoPill").textContent = r ? `${r === "manager" ? "Library manager" : S.names[r]} · switch` : "Sign in";
  }
  function openSignIn() {
    const wrap = $("#people");
    wrap.innerHTML = PEOPLE.filter((p) => p in S.names).map((p) => `<button type="button" data-who="${p}">
        <canvas data-pet="${esc(S.pets[p] || "")}" width="96" height="104"></canvas>${S.names[p]}<span class="sub">${esc(SUBTITLE[p] || "student worker")}</span></button>`).join("")
      + `<button type="button" data-who="manager"><svg class="mgr-mark" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9"/><path d="M9 11h14M16 11v12"/><circle cx="23.5" cy="21.5" r="3"/></svg>Library manager<span class="sub">approves trades, posts shifts</span></button>`;
    wrap.querySelectorAll("canvas").forEach((c) => Sprites.badge(c, c.dataset.pet || "debug-duck-v2", "idle"));
    wrap.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      store.set(ROLE_KEY, b.dataset.who); $("#signIn").close();
      location.hash = b.dataset.who === "manager" ? "#manager" : "#me"; route();
    }));
    $("#signIn").showModal();
  }

  // a chat thread that polls one phone (the owner channel, relayed in the synthetic demo)
  function threadPoller(sel, emptyText) {
    const st = { who: null, count: -1 };
    st.reset = (who) => { st.who = who; st.count = -1; };
    st.poll = async () => {
      if (!st.who) return;
      let d; try { d = await get(`/phone/${st.who}`); } catch (_) { return; }
      const msgs = d.messages || []; if (msgs.length === st.count) return;
      const fresh = st.count >= 0 && msgs.length > st.count; st.count = msgs.length;
      const t = $(sel);
      t.innerHTML = msgs.length ? bubbles(msgs, fresh) : `<p class="empty">${typeof emptyText === "function" ? emptyText(st.who) : emptyText}</p>`;
      wireButtons(t, st.who, st.poll); t.scrollTop = t.scrollHeight;
    };
    return st;
  }
  const meChat = threadPoller("#meThread", (who) => `Nothing yet. ${S.names[who]}'s mascot only texts when something in the week collides. Try a message below.`);
  const mgrChat = threadPoller("#mgrThread", "Trade approvals, call-outs and reports land here.");

  const SUBTITLE = { ana: "Work-Study, Canvas exams", ben: "F-1, also works at Dining", dev: "two ASU jobs, 25 h average",
    priya: "F-1, wants more hours", zoe: "weekend trip coming up", marco: "Work-Study, career fair" };
  const RULE = { f1_weekly_20: "On-campus hours this week (F-1 limit, all jobs together)", f1_break_40: "On-campus hours this break week (F-1)",
    aca_25_avg: "ASU 25-hour average", weekly_40: "Hours this week (40 h cap)", fws_award: "Work-Study award left this week" };

  async function renderMe() {
    const who = role(); if (!PEOPLE.includes(who)) return;
    $("#meTitle").textContent = `${S.names[who]}'s week`;
    $("#meChatTitle").textContent = `${S.names[who]}'s mascot`;
    Sprites.badge($("#meAvatar"), S.pets[who] || "debug-duck-v2", "waving");
    Sprites.badge($("#meChatPet"), S.pets[who] || "debug-duck-v2", "idle");
    $("#meChips").innerHTML = QUICK.map((q) => `<button type="button">${esc(q)}</button>`).join("");
    $("#meChips").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => sendMe(b.textContent)));
    meChat.poll();
    let d; try { d = await get(`/me/${who}`); } catch (_) { return; }
    const items = d.shifts.map((s) => ({ ...s, label: "Library shift", kind: "shift" })).concat(d.busy.map((b) => ({ ...b })));
    const clash = (a, b) => new Date(a.start) < new Date(b.end) && new Date(b.start) < new Date(a.end);
    items.forEach((it) => { if (it.kind === "shift") it.clash = d.busy.some((b) => b.kind !== "due" && clash(it, b)); });
    const html = DAYS.map((day, i) => {
      const date = new Date(MONDAY.getTime() + i * 864e5);
      const today = items.filter((it) => (new Date(it.start).getDay() + 6) % 7 === i).sort((a, b) => new Date(a.start) - new Date(b.start));
      const rows = today.map((it) => `<div class="week-item ${it.kind === "shift" ? "shift" : ""} ${it.clash ? "clash" : ""}">
          <time>${it.kind === "due" ? "due " + hourLabel(new Date(it.start)) : span(it).replace(/^\w{3} /, "")}</time>
          <span class="what"><b>${esc(it.label)}</b>${it.clash ? " · collides" : ""}${it.source && it.kind !== "shift" ? `<span class="src"> · from ${esc({ canvas: "Canvas", calendar: "your calendar", gmail: "an email", text: "your text", asu: "ASU calendar" }[it.source] || it.source)}</span>` : ""}</span></div>`).join("");
      return `<div class="week-day"><h3>${day} ${date.getDate()}</h3>${rows || '<p class="week-empty">Nothing.</p>'}</div>`;
    }).join("");
    $("#meWeek").innerHTML = html + (d.classes.length ? `<p class="muted small">Classes every week: ${d.classes.map(esc).join(", ")}.</p>` : "");
    const meters = d.rooms.filter((r) => r.unit === "$" || r.rule_id.startsWith("f1") || (r.rule_id === "aca_25_avg" && r.room < 16)).map((r) => {
      const pct = Math.max(0, Math.min(100, 100 * r.used / r.cap));
      const val = r.unit === "$" ? `${money(r.room)} left` : `${r.used.toFixed(0)} of ${r.cap.toFixed(0)} h`;
      const other = r.rule_id.startsWith("f1") && Object.keys(d.other_jobs).length ? `Includes ${Object.entries(d.other_jobs).map(([k, v]) => `${v} h at ${k}`).join(", ")} that the Library can't see.` : "";
      return `<div class="meter"><div class="top"><span>${RULE[r.rule_id] || r.rule_id}</span><b>${val}</b></div>
        <span class="track"><span class="fill ${r.room < 4 ? "tight" : ""}" style="width:${pct}%"></span></span>${other ? `<span class="note">${other}</span>` : ""}</div>`;
    }).join("");
    const runway = d.runway ? `<div class="meter"><span class="note">At this week's schedule your Work-Study award lasts about ${d.runway[0].toFixed(1)} more weeks; the next break is ${d.runway[2]} weeks away.</span></div>` : "";
    $("#mePrivate").innerHTML = `<div class="priv">${meters || '<p class="muted small">No hour limit is close this week.</p>'}${runway}
      <div class="seen-box"><h3>What others see</h3><ul><li>Coworkers and the manager: that you're busy at some times, which shift you want to trade, and your yes or no.</li>
      <li>Never: your calendar, your reasons, or your hours at other jobs. Coworkers never see your visa or Work-Study status (your manager knows those from hiring).</li></ul></div>
      <p class="muted small">${d.wants_more_hours ? "You asked for more hours: your mascot picks extra shifts that fit every limit, and you confirm each one." : "Want more hours? Tell your mascot, and it will pick extra shifts that fit every limit."}</p></div>`;
  }
  async function sendMe(text) {
    const who = role(); if (!PEOPLE.includes(who) || !text) return;
    await post(`/phone/${who}/text`, { text }).catch(() => {});
    meChat.poll(); setTimeout(renderMe, 600);
  }

  async function renderMgr() {
    mgrChat.who !== "manager" && mgrChat.reset("manager");
    mgrChat.poll();
    if (!$("#exDay").options.length) {
      $("#exDay").innerHTML = DAYS.map((d, i) => { const dt = new Date(MONDAY.getTime() + i * 864e5); return `<option value="${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}"${i === 3 ? " selected" : ""}>${d} ${dt.getDate()}</option>`; }).join("");
      const hrs = (sel) => Array.from({ length: 16 }, (_, k) => k + 7).map((h) => `<option value="${h}"${h === sel ? " selected" : ""}>${(h % 12) || 12} ${h >= 12 ? "PM" : "AM"}</option>`).join("");
      $("#exStart").innerHTML = hrs(18); $("#exEnd").innerHTML = hrs(22);
    }
    renderBoard("#mgrBoard");
    renderForecast("#mgrForecast");
    let m; try { m = await get("/manager/state"); } catch (_) { return; }
    $("#mgrSwapRule").checked = !!m.swap_rule;
    m.roster.forEach((r) => { S.roster[r.shift_id] = r; });
    const li = (t, sub) => `<li>${t}${sub ? `<span class="sub">${sub}</span>` : ""}</li>`;
    const open = m.open.map((s) => li(`${name(S.roster[s] ? S.roster[s].owner : "")}'s ${shiftLabel(s)}`, "no safe trade; still scheduled, no reason given"));
    const extras = m.extras.map((s) => { const r = S.roster[s]; return li(`Extra: ${shiftLabel(s)}`, r && r.owner !== "open" ? `taken by ${name(r.owner)}` : "offered to every mascot"); });
    const issues = m.issues.map((i) => li(`${esc(i.text)}`, `${i.category} · from ${esc(i.from)} · ${i.status}`));
    const meets = Object.entries(m.meetings).map(([, mt]) => { const c = mt.chosen; const going = Object.values(mt.rsvp).filter(Boolean).length;
      return li(c == null ? "Team meeting: pick a time in your inbox" : `Team meeting ${span({ start: mt.options[c].slot[0], end: mt.options[c].slot[1] })}`, c == null ? `${mt.options.length} options` : `${going} coming, ${Object.keys(mt.rsvp).length - going} can't`); });
    const block = (title, rows, empty) => `<ul class="mgr-list"><h3>${title}</h3>${rows.length ? rows.join("") : `<li class="muted">${empty}</li>`}</ul>`;
    $("#mgrLists").innerHTML = block("Open shifts", open.concat(extras), "None.") + block("Reports", issues, "No reports.") + block("Meetings", meets, "None scheduled.");
  }

  // the org chart (web/js/org.js), fed by the hierarchy's events and its wire messages
  let org = null, orgData = null;
  const orgLog = []; // events from before the chart was opened, replayed into it without animation
  function orgFeed(ev) {
    orgLog.push(ev); if (orgLog.length > 600) orgLog.shift();
    if (org) org.event(ev, live);
    logEvent(ev);
  }
  async function ensureOrg() {
    if (org || !window.TagOutOrg) return;
    let d = orgData;
    if (!d) { try { d = orgData = await get("/org"); } catch (_) { $("#org").innerHTML = '<p class="muted">The campus hierarchy is not running here. Start it with <code>python -m scripts.run_all</code>.</p>'; return; } }
    d.students.forEach((p) => { ORGN[p.id] = p.name; });
    Object.values(d.roles).forEach((r) => { ORGN[r.id] = r.name; });
    $("#org").innerHTML = "";
    org = TagOutOrg.create($("#org"), { data: d, judge: JUDGE && S.debug, name, shift: (id) => id,
      phoneOf: async (id) => ((await get(`/phone/${id === "steward" ? "manager" : id}`)).messages || []) });
    orgLog.forEach((ev) => org.event(ev, false));
  }

  // the agent graph, fed by the broker's wire events
  const NODE = (id) => (PEOPLE.includes(id) || id === "broker" || id === "steward" ? id : null);
  function ensureFlow() {
    if (flow || !window.TagOutFlow) return;
    flow = TagOutFlow.create($("#flow"), { students: PEOPLE.filter((p) => p in S.names).map((p) => ({ id: p, name: S.names[p] })), manager: "Library manager" });
    const msgs = leak.msgs;
    wireLog.forEach((ev) => feedWire({ ...ev, quiet: true }));
    leak.msgs = msgs; // already counted
    renderLedger();
    if (S.debug) Promise.all(PEOPLE.map((p) => get(`/me/${p}`).catch(() => null))).then((all) => {
      leak.labels = new Set(all.filter(Boolean).flatMap((d) => d.busy.map((b) => b.label).concat(d.classes)).filter((l) => l && l.length > 3));
    });
  }
  function flowState(ev) {
    const st = (id, t, tone) => flow.state(id, t, tone);
    switch (ev.type) {
      case "sunday_check": PEOPLE.forEach((a) => st(a, "checking next week", "wait")); st("broker", "Sunday check sent"); break;
      case "trade_request": st(ev.agent, ev.urgent ? "called out" : "wants a trade", "wait"); break;
      case "round": st("broker", `${cap(ev.phase)} round ${ev.iteration}: asking ${ev.agents.length}`, "wait"); break;
      case "picks": Object.entries(ev.picks).forEach(([a, s]) => st(a, s ? `picked ${shortLabel(s)}` : "passed", s ? "ok" : "")); break;
      case "counter_window": st("broker", `counter-offer window, ${ev.seconds} s`, "wait"); break;
      case "selected": st("broker", `CP-SAT kept ${ev.proposals.length}`, "ok"); break;
      case "prepare": st("broker", `holding ${ev.txn_id}`, "wait"); st("steward", "asked to approve", "wait"); break;
      case "vote": st(ev.agent === "steward" ? "steward" : ev.agent, { yes: "confirmed", no: "declined", stale: "week changed", timeout: "no answer" }[ev.vote], ev.vote === "yes" ? "ok" : "bad"); break;
      case "commit": st("broker", `committed ${ev.txn_id}`, "ok"); (ev.members || []).forEach((a) => st(a, "traded", "ok")); break;
      case "abort": st("broker", `aborted ${ev.txn_id}`, "bad"); break;
      case "summary": st("broker", ev.kind === "week" || !ev.kind ? `week done: ${ev.fixed} of ${ev.asked}` : `${ev.kind} done`, "ok"); break;
      default: break;
    }
  }
  function countKeys(o) {
    if (Array.isArray(o)) return o.reduce((n, v) => n + countKeys(v), 0);
    // a slot map's keys are slot labels ("Mon 10"), not field names: count its values only
    if (o && typeof o === "object") return Object.entries(o).reduce((n, [k, v]) => n + (ALLOWED.has(k) ? 0 : 1) + (k === "slots" ? 0 : countKeys(v)), 0);
    return 0;
  }
  function feedWire(ev) {
    if (org) org.wire(ev, live && !ev.quiet);
    if (ev.status < 400) {
      leak.msgs++;
      leak.fields += countKeys(ev.payload) + countKeys(ev.response);
      const blob = JSON.stringify([ev.payload, ev.response]);
      if (leak.labels instanceof Set) leak.labels.forEach((l) => { if (blob.includes(l)) leak.hits++; });
    }
    $("#lkMsgs").textContent = leak.msgs.toLocaleString("en-US");
    $("#lkFields").textContent = String(leak.fields);
    $("#lkLabels").textContent = String(leak.hits);
    const from = NODE(ev.from), to = NODE(ev.to);
    if (from && to && !ev.quiet) { wireLog.push(ev); if (wireLog.length > 300) wireLog.shift(); }
    if (!flow || !from || !to) return;
    const quiet = !live || ev.quiet;
    flow.message({ from, to, schema: ev.schema, path: ev.path, payload: ev.payload, dir: "req", ts: ev.ts }, quiet);
    if (ev.status >= 400) flow.message({ from: to, to: from, schema: `${ev.status} rejected`, payload: ev.response || {}, dir: "resp", ts: ev.ts }, quiet);
    else if (ev.response != null) {
      const held = ev.schema === "Prepare" && ev.response && ev.response.vote === null;
      flow.message({ from: to, to: from, schema: held ? "Held: asking student" : ev.resp_schema || "OK", payload: ev.response, dir: "resp", ts: ev.ts }, quiet);
    }
    if (!quiet && PEOPLE.includes(to) && (ev.schema === "RingCheck" || ev.schema === "PickRequest" || ev.schema === "Prepare")) flow.rule(to);
  }
  // the owner channel: private packets between each phone and its mascot (judge view data, never on the wire)
  const owners = {};
  async function pollOwners() {
    if (!flow || !S.debug) return;
    await Promise.all(PEOPLE.concat(["manager"]).map(async (who) => {
      let d; try { d = await get(`/phone/${who}`); } catch (_) { return; }
      const msgs = d.messages || [], seen = owners[who] ?? msgs.length;
      owners[who] = msgs.length;
      msgs.slice(seen).forEach((m) => {
        const phone = `phone:${who}`, agent = who === "manager" ? "steward" : who;
        const toPhone = m.kind !== "student";
        if (m.kind === "reply" && m.from === "auto") return;
        flow.message({ from: toPhone ? agent : phone, to: toPhone ? phone : agent, schema: toPhone ? "Message" : "Text", private: true, text: m.text, dir: "req" });
      });
    }));
  }

  async function snoop() {
    const note = $("#snoopNote");
    note.hidden = false; note.textContent = "Asking every mascot why it passed, and probing for room it never offered…";
    let r; try { r = await post("/demo/snoop"); } catch (e) { note.textContent = "Snoop needs the synthetic demo (debug) mode."; return; }
    if (!STATIC) showSnoop(r); // the hosted replay shows it when the recorded snoop event arrives
  }
  function showSnoop(r) {
    const note = $("#snoopNote");
    note.hidden = false;
    const v = Object.values(r), refused = v.filter((x) => x.why === 422).length, nos = v.filter((x) => x.room_probe === false).length;
    note.innerHTML = `<b>${refused} of ${v.length}</b> mascots never saw "why did you pass?": the closed schema rejected the request before any code ran (HTTP 422), because no message has a field for a reason. <b>${nos} of ${v.length}</b> mascots answered no about a shift they never picked, so a nosy broker learns nothing about anyone's room. Watch the red replies in the graph.`;
  }

  async function renderLedger() {
    let d = {}, q = {};
    try { [d, q] = await Promise.all([get("/sim"), get("/quotes")]); } catch (_) { /* fill what we can */ }
    const gh = (p) => `https://github.com/neric-joel/tag-out/blob/main/${p}`;
    const src = (kind, path, extra) => `<span class="src">${kind}</span> <a href="${gh(path)}"><code>${path}</code></a>${extra ? `<span class="sub">${extra}</span>` : ""}`;
    const quote = (id) => q[id] ? `<span class="src">Rule</span> <code>${id}</code><blockquote>"${esc(q[id].quote)}"</blockquote><a class="sub" href="${esc(q[id].url)}">${esc(q[id].url.replace(/^https:\/\//, "").split("/")[0])}</a>` : `<span class="src">Rule</span> <code>${id}</code>`;
    const rows = [
      ["21 of 20 h", "What a Library-only scheduler would do to Ben (F-1): it can't see his 9 Aramark hours.", src("Test", "tests/test_baseline.py")],
      ["17 of 20 h", "Ben's hours after the ring. Only Ben sees this line.", src("Test", "tests/test_flow.py")],
      ["20 h a week", "The F-1/J-1 on-campus limit during the fall and spring semesters.", quote("f1_weekly_20")],
      ["…across all jobs", "The same page says the 20 hours are combined across every on-campus employer.", quote("f1_break_40")],
      ["25 h average", "Every ASU student worker, averaged over the measurement period.", quote("aca_25_avg")],
      ["Up to the award", "Work-Study can pay only up to the award; after that the department decides whether the job continues on regular pay.", quote("fws_award")],
      [d.tagout_pct != null ? `${d.tagout_pct}% vs ${d.swap_pct}%` : "–", "Collisions fixed: Tag Out vs a group chat where every volunteer checks all of their own limits correctly.", src("Simulation", "docs/simulation.json", "1,000 synthetic weeks, seed 7, 40-person roster")],
      [d.rule_breaks_hand_checked_per_week != null ? `${d.rule_breaks_hand_checked_per_week} a week` : "–", "Limit-breaking covers a group chat still makes when volunteers check this job's hours by hand.", src("Simulation", "docs/simulation.json", d.rule_breaks_by_rule ? Object.entries(d.rule_breaks_by_rule).map(([k, v]) => `${k} ${v}`).join(", ") : "")],
      ["10,000", "Students who work at ASU each year.", quote("stats")],
      ["0", "Private values in any agent-to-agent message (also counted live above).", src("Test", "tests/test_privacy.py")],
      ["0", "Decisions made by an LLM. Rules are code; Claude only reads students' texts.", src("Code", "rulebook/rules.py")],
    ];
    $("#ledger").innerHTML = `<thead><tr><th>Number</th><th>What it says</th><th>Source</th></tr></thead><tbody>${rows.map((r) => `<tr><td class="fig">${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td></tr>`).join("")}</tbody>`;
  }

  // ---------- controls ----------
  function wire() {
    $("#btnSunday").addEventListener("click", () => post("/demo/sunday").catch(() => {}));
    $("#btnRun").addEventListener("click", () => post("/demo/run").catch(() => {}));
    $("#btnReset").addEventListener("click", () => post("/admin/reset").catch(() => {}));
    $("#btnBreak").addEventListener("click", () => post("/demo/break").catch(() => {}));
    if ($("#btnPets")) $("#btnPets").addEventListener("click", () => openPets(chat.who === "manager" ? "ana" : chat.who));
    $("#petSearch").addEventListener("click", searchPets);
    $("#petQuery").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); searchPets(); } });
    $("#petFor").addEventListener("change", searchPets);
    const size = $("#petSize");
    size.value = store.get("tagout.size", 96);
    size.addEventListener("input", () => { if (world) world.setPetHeight(+size.value); store.set("tagout.size", +size.value); });
    $("#whoPill").addEventListener("click", openSignIn);
    window.addEventListener("hashchange", route);
    $("#meCompose").addEventListener("submit", (e) => { e.preventDefault(); const i = $("#meInput"); const t = i.value.trim(); i.value = ""; sendMe(t); });
    $("#mgrExtra").addEventListener("submit", async (e) => {
      e.preventDefault();
      await post("/manager/extra", { date: $("#exDay").value, start: +$("#exStart").value, end: +$("#exEnd").value }).catch(() => {});
      setTimeout(renderMgr, 400);
    });
    $("#mgrMeeting").addEventListener("click", async () => { await post("/manager/meeting", {}).catch(() => {}); setTimeout(renderMgr, 400); });
    $("#mgrSwapRule").addEventListener("change", (e) => post("/manager/tap", { data: e.target.checked ? "rule:swaps:on" : "rule:swaps:off" }).then(renderMgr).catch(() => {}));
    $("#agSunday").addEventListener("click", () => post("/demo/sunday").catch(() => {}));
    $("#agRun").addEventListener("click", () => post("/demo/run").catch(() => {}));
    $("#agSnoop").addEventListener("click", snoop);
    $("#orgPlay").addEventListener("click", () => post("/demo/org/morning").catch(() => {}));
    $("#orgSafety").addEventListener("click", () => post("/demo/org/safety").catch(() => {}));
    $("#orgQuestion").addEventListener("click", () => post("/demo/org/question").catch(() => {}));
    $("#compose").addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = $("#composeInput"), text = input.value.trim(); if (!text) return;
      input.value = ""; await post(`/phone/${chat.who}/text`, { text }).catch(() => {}); pollChat();
    });
  }

  function connect() {
    const live = $("#live"), text = $("#liveText");
    if (STATIC) { live.className = "live on"; text.textContent = "Recording"; return; }
    const es = new EventSource("/events");
    es.onopen = () => { live.className = "live on"; text.textContent = "Live"; };
    es.onerror = () => { live.className = "live off"; text.textContent = "Reconnecting"; };
    es.onmessage = (m) => { try { onEvent(JSON.parse(m.data)); } catch (err) { console.error(err); } };
  }

  async function boot() {
    if (STATIC) {
      R.cur = await loadRec("tour");
      $("#btnSunday").textContent = $("#agSunday").textContent = "Play the week";
      $("#btnRun").textContent = $("#agRun").textContent = "Break it";
      $("#btnReset").textContent = "Restart";
      $("#btnPets").remove();
      const note = document.createElement("div");
      note.className = "static-banner";
      note.innerHTML = 'Hosted demo: a recording of the real system, where 16 student mascots, a broker, the Library Steward and the campus hierarchy really traded these messages. Press <b>Play the week</b>, then sign in as a student or the manager, or open the <b>Org chart</b>. Run it live with one command: <a href="https://github.com/neric-joel/tag-out">github.com/neric-joel/tag-out</a>.';
      document.body.prepend(note);
    }
    const [st, ag] = await Promise.all([get("/state"), get("/agents")]);
    S.debug = !!st.debug; S.names = ag.names; S.petMeta = st.pets;
    Object.values(st.agents).forEach((a) => { S.pets[a.agent_id] = a.pet_id; });
    st.roster.forEach((r) => { S.roster[r.shift_id] = r; });
    document.querySelectorAll("[data-debug]").forEach((el) => { el.hidden = !S.debug; });
    $("#tabJudge").hidden = !S.debug;
    $("#tabMe").hidden = $("#tabMgr").hidden = $("#whoPill").hidden = !S.debug; // role pages need the synthetic demo
    world = PetWorld.create($("#world"), { petHeight: +store.get("tagout.size", 96), onSelect: (id) => { if (S.debug) openChat(id); } });
    window.tagOutWorld = world; // handy in the console during the demo
    world.setPets(PEOPLE.filter((p) => p in S.names).map((p) => ({ id: p, name: S.names[p], petId: S.pets[p] || "debug-duck-v2" })));
    // the rest of campus wanders the commons too: Dining and Rec center student workers, each with their own pet
    get("/org").then((o) => {
      orgData = o;
      o.students.forEach((p) => { ORGN[p.id] = p.name; });
      Object.values(o.roles).forEach((r) => { ORGN[r.id] = r.name; });
      const more = o.students.filter((p) => !PEOPLE.includes(p.id)).map((p) => ({ id: p.id, name: p.name, petId: p.pet_id }));
      if (more.length) world.setPets(PEOPLE.filter((p) => p in S.names).map((p) => ({ id: p, name: S.names[p], petId: S.pets[p] || "debug-duck-v2" })).concat(more));
    }).catch(() => { /* no hierarchy running (live mode without it) */ });
    if (JUDGE) document.querySelectorAll('.tabs a[href^="#"]').forEach((a) => { a.href = "/" + a.getAttribute("href"); }); // tabs lead out of the judge view

    if (JUDGE && S.debug) { $("#debugBanner").hidden = false; $("#judgePanel").hidden = false; buildPhones(); renderJudge(); setInterval(renderJudge, 4000); }
    renderKpis(); renderBoard(); renderSim(); wire(); route();
    if (S.debug) { chat.who = store.get("tagout.chat", "ana"); openChat(chat.who); }
    setInterval(() => {
      if (S.debug && S.view === "commons") pollChat();
      phones.forEach((p) => p.poll());
      if (S.view === "me") meChat.poll();
      if (S.view === "manager") mgrChat.poll();
      if (S.view === "agents") pollOwners();
    }, 1200);
    setInterval(() => { if (S.view === "me") renderMe(); if (S.view === "manager") renderMgr(); }, 5000);
    connect();
  }
  boot().catch((e) => { $("#roundStatus").textContent = "Can't reach the broker. Start it with: python -m scripts.run_all"; console.error(e); });
})();
