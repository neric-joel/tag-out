/* Tag Out commons: the mascots live in the world (web/js/world.js); this file turns the broker's public event
   stream (SSE) into what they do, and keeps the roster, log, numbers and (synthetic demo only) the chats. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const PEOPLE = ["ana", "ben", "dev", "priya", "zoe", "marco"];
  const JUDGE = location.pathname.startsWith("/judge");
  const MONDAY = new Date("2026-10-26T00:00:00-07:00");

  const S = {
    debug: false, names: {}, pets: {}, petMeta: [], roster: {}, requested: new Set(), moved: {}, open: new Set(),
    votes: {}, summary: null, committed: [], gathered: new Set(), checks: 0, passed: 0,
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
  const name = (id) => S.names[id] || (id === "steward" ? "the manager" : id);
  const cap = (s) => s[0].toUpperCase() + s.slice(1);
  function listNames(ids) { const n = ids.map(name); return n.length < 2 ? n.join("") : n.slice(0, -1).join(", ") + " and " + n[n.length - 1]; }
  const money = (v) => "$" + Math.round(v).toLocaleString("en-US");
  const clock = (iso) => { const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const store = { get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (_) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* private mode */ } } };

  // ---------- API ----------
  async function get(path) { const r = await fetch(path); if (!r.ok) throw new Error(path + " " + r.status); return r.json(); }
  async function post(path, body) {
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
    switch (ev.type) {
      case "reset":
        Object.assign(S, { requested: new Set(), moved: {}, open: new Set(), votes: {}, summary: null, committed: [], checks: 0, passed: 0 });
        requesters.clear();
        $("#events").innerHTML = ""; $("#logCount").textContent = "0 events";
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
        renderTabs(); renderBoard(); renderCredits(); break;
      case "summary":
        (ev.open_shifts || []).forEach((s) => S.open.add(s));
        if (ev.kind === "callout") {
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
      case "summary": return ev.kind === "callout" ? `Call-out round done: ${ev.fixed ? "covered" : "no safe taker, sent to the manager"}.` : `Week done: ${ev.fixed} of ${ev.asked} fixed, ${money(ev.pay_kept)} of pay kept by trading, ${ev.open} open.`;
      case "reset": return "Demo reset.";
      default: return null;
    }
  }
  function logEvent(ev) {
    const text = sentence(ev);
    if (!text) return;
    const li = document.createElement("li");
    li.innerHTML = `<time>${clock(ev.ts)}</time><span>${text}</span>`;
    $("#events").prepend(li);
    $("#logCount").textContent = `${$("#events").children.length} events`;
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
  function renderBoard() {
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
            const title = { open: "no safe trade", moved: "traded in", covered: "covered", req: "wants a trade" }[cls] || "shift";
            return `<span class="chip ${cls}" title="${span(r)}: ${title}">${S.open.has(id) ? "open" : span(r, true)}</span>`;
          }).join("");
        html.push(`<div class="cell" role="cell">${chips}</div>`);
      }
    }
    $("#board").innerHTML = html.join("");
    $("#board").querySelectorAll("canvas").forEach((c) => Sprites.badge(c, c.dataset.pet || "debug-duck-v2", "idle"));
  }

  // ---------- chats (synthetic demo: the owner channel relayed by the broker) ----------
  function bubbles(msgs, fresh) {
    let lastButtons = -1;
    msgs.forEach((m, i) => { if (m.buttons && m.buttons.length) lastButtons = i; });
    const answered = msgs.slice(lastButtons + 1).some((m) => m.kind === "reply");
    return msgs.map((m, i) => {
      const cls = m.kind === "student" ? "msg me" : m.kind === "reply" ? "msg reply" : "msg";
      const live = i === lastButtons && !answered;
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
    try {
      const f = await get("/forecast");
      const lab = (slot) => { const m = slot.match(/^(\w{3}) (\d+)-(\d+)$/); if (!m) return slot; const h = (x) => (+x % 12) || 12; return `${m[1]} ${h(m[2])}–${h(m[3])} ${+m[3] >= 12 ? "PM" : "AM"}`; };
      const top = f.alerts.slice().sort((a, b) => b.busy - a.busy);
      $("#forecast").innerHTML = `<h3>Crunch forecast for the manager</h3>
        <p class="muted small" style="margin-bottom:8px">Counts only, shown when ${f.k} or more of ${f.staff} staff are busy. No names, no reasons.</p>
        <ul>${top.length ? top.slice(0, 4).map((a) => `<li><span>${lab(a.slot)}</span><span class="num">${a.busy} of ${a.staff} can't work</span></li>`).join("") : "<li><span>No crunch next week.</span><span></span></li>"}</ul>
        ${top.length > 4 ? `<p class="muted small" style="margin-top:6px">${top.length - 4} more slots with ${f.k} or more busy.</p>` : ""}`;
    } catch (_) { /* steward down */ }
  }

  function renderCredits() {
    const used = new Set(Object.values(S.pets));
    const credits = S.petMeta.filter((p) => used.has(p.id)).map((p) => `<a href="${p.page}">${esc(p.name)}</a> by ${esc(p.creator)}`);
    const extra = [...used].filter((id) => !S.petMeta.some((p) => p.id === id)).map((id) => `<a href="https://codex-pets.net/#/pets/${esc(id)}">${esc(id)}</a>`);
    $("#credits").innerHTML = `Mascots from <a href="https://codex-pets.net">Codex Pets</a>: ${credits.concat(extra).join(", ")}. Each student picked their own; the art is downloaded at setup, not stored in the repo.`;
  }

  // ---------- controls ----------
  function wire() {
    $("#btnSunday").addEventListener("click", () => post("/demo/sunday").catch(() => {}));
    $("#btnRun").addEventListener("click", () => post("/demo/run").catch(() => {}));
    $("#btnReset").addEventListener("click", () => post("/admin/reset").catch(() => {}));
    $("#btnBreak").addEventListener("click", () => post("/demo/break").catch(() => {}));
    $("#btnPets").addEventListener("click", () => openPets(chat.who === "manager" ? "ana" : chat.who));
    $("#petSearch").addEventListener("click", searchPets);
    $("#petQuery").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); searchPets(); } });
    $("#petFor").addEventListener("change", searchPets);
    const size = $("#petSize");
    size.value = store.get("tagout.size", 120);
    size.addEventListener("input", () => { if (world) world.setPetHeight(+size.value); store.set("tagout.size", +size.value); });
    $("#compose").addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = $("#composeInput"), text = input.value.trim(); if (!text) return;
      input.value = ""; await post(`/phone/${chat.who}/text`, { text }).catch(() => {}); pollChat();
    });
  }

  function connect() {
    const live = $("#live"), text = $("#liveText");
    const es = new EventSource("/events");
    es.onopen = () => { live.className = "live on"; text.textContent = "Live"; };
    es.onerror = () => { live.className = "live off"; text.textContent = "Reconnecting"; };
    es.onmessage = (m) => { try { onEvent(JSON.parse(m.data)); } catch (err) { console.error(err); } };
  }

  async function boot() {
    const [st, ag] = await Promise.all([get("/state"), get("/agents")]);
    S.debug = !!st.debug; S.names = ag.names; S.petMeta = st.pets;
    Object.values(st.agents).forEach((a) => { S.pets[a.agent_id] = a.pet_id; });
    st.roster.forEach((r) => { S.roster[r.shift_id] = r; });
    document.querySelectorAll("[data-debug]").forEach((el) => { el.hidden = !S.debug; });
    $("#tabJudge").hidden = !S.debug;
    (JUDGE ? $("#tabJudge") : $("#tabArena")).setAttribute("aria-current", "page");

    world = PetWorld.create($("#world"), { petHeight: +store.get("tagout.size", 120), onSelect: (id) => { if (S.debug) openChat(id); } });
    window.tagOutWorld = world; // handy in the console during the demo
    world.setPets(PEOPLE.filter((p) => p in S.names).map((p) => ({ id: p, name: S.names[p], petId: S.pets[p] || "debug-duck-v2" })));

    if (JUDGE && S.debug) { $("#debugBanner").hidden = false; $("#judgePanel").hidden = false; buildPhones(); renderJudge(); setInterval(renderJudge, 4000); }
    renderCredits(); renderKpis(); renderBoard(); renderSim(); wire();
    if (S.debug) { chat.who = store.get("tagout.chat", "ana"); openChat(chat.who); }
    setInterval(() => { if (S.debug) pollChat(); phones.forEach((p) => p.poll()); }, 1200);
    connect();
  }
  boot().catch((e) => { $("#roundStatus").textContent = "Can't reach the broker. Start it with: python -m scripts.run_all"; console.error(e); });
})();
