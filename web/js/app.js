/* Tag Out arena: renders the broker's public event stream (SSE) and, in the synthetic demo, each phone. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const ORDER = ["ana", "priya", "ben", "zoe", "dev", "marco"]; // around the table
  const ANGLE = { ana: 180, priya: 240, ben: 300, zoe: 0, dev: 60, marco: 120 };
  const JUDGE = location.pathname.startsWith("/judge");

  const S = {
    debug: false, names: {}, pets: {}, petMeta: [], roster: {}, faces: {}, status: {},
    edges: [], requested: new Set(), moved: {}, open: new Set(), votes: {}, txnMembers: {},
    summary: null, committed: [], lastRound: null, ringNames: [],
  };

  // ---------- formatting ----------
  const pad = (n) => String(n).padStart(2, "0");
  function hourLabel(d) { const h = d.getHours() % 12 || 12; return d.getMinutes() ? `${h}:${pad(d.getMinutes())}` : `${h}`; }
  function phx(iso) { return new Date(iso); } // ISO strings carry -07:00; displayed in the viewer's clock for the demo machine
  function span(ref, short) {
    const s = phx(ref.start), e = phx(ref.end);
    const day = DAYS[(s.getDay() + 6) % 7];
    const ap = (d) => (d.getHours() >= 12 ? "PM" : "AM");
    if (short) return `${hourLabel(s)}–${hourLabel(e)}${ap(e) === "PM" ? "p" : "a"}`;
    if (ap(s) !== ap(e) && e.getHours() !== 12) return `${day} ${hourLabel(s)} ${ap(s)}–${hourLabel(e)} ${ap(e)}`;
    return `${day} ${hourLabel(s)}–${hourLabel(e)} ${ap(e)}`;
  }
  const shiftLabel = (id) => (S.roster[id] ? span(S.roster[id]) : id);
  const name = (id) => S.names[id] || (id === "steward" ? "the manager" : id);
  function listNames(ids) {
    const n = ids.map(name);
    return n.length < 2 ? n.join("") : n.slice(0, -1).join(", ") + " and " + n[n.length - 1];
  }
  const money = (v) => "$" + Math.round(v).toLocaleString("en-US");
  const clock = (iso) => { const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };

  // ---------- API ----------
  async function get(path) { const r = await fetch(path); if (!r.ok) throw new Error(path + " " + r.status); return r.json(); }
  async function post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    if (!r.ok) throw new Error(path + " " + r.status);
    return r.json().catch(() => ({}));
  }

  // ---------- faces ----------
  function setFace(a, face, ms) { S.faces[a] = { face, until: ms ? performance.now() + ms : 0, after: "idle" }; }
  function faceOf(a, now) {
    const f = S.faces[a];
    if (!f) return "idle";
    if (f.until && now > f.until) { S.faces[a] = { face: f.after, until: 0 }; return f.after; }
    return f.face;
  }

  // ---------- events ----------
  function onEvent(ev, live) {
    const t = ev.type;
    switch (t) {
      case "reset":
        Object.assign(S, { faces: {}, status: {}, edges: [], requested: new Set(), moved: {}, open: new Set(),
          votes: {}, txnMembers: {}, summary: null, committed: [], ringNames: [] });
        $("#events").innerHTML = "";
        refreshRoster(); setStatus("Reset. Waiting for the Sunday check.");
        setFinding(null); renderKpis(); break;
      case "sunday_check":
        ev.agents.forEach((a) => setFace(a, "thinking", 1800));
        setStatus("Sunday check sent. Each mascot compares next week with its own student's calendar."); break;
      case "trade_request":
        S.requested.add(ev.shift_id); S.status[ev.agent] = "wants a trade"; break;
      case "round_open":
        S.edges = S.edges.filter((e) => e.state === "commit");
        ev.items.forEach((r) => { S.roster[r.shift_id] = S.roster[r.shift_id] || r; });
        setStatus(`<b>${ev.items.length} shifts</b> up for trade. Attempt ${ev.attempt}.`); break;
      case "round":
        ev.agents.forEach((a) => { setFace(a, "thinking"); S.status[a] = "thinking"; });
        S.edges = S.edges.filter((e) => e.kind !== "pick");
        setStatus(`${cap(ev.phase === "swap" ? "Swap" : ev.phase === "cover" ? "Cover" : "Extend")} round ${ev.iteration}: ` +
          `${ev.agents.length} answering. Replies are held to the deadline and shown together.`); break;
      case "picks": {
        const picks = Object.entries(ev.picks);
        picks.forEach(([a, sid]) => {
          if (sid) {
            const owner = S.roster[sid] ? S.roster[sid].owner : null;
            setFace(a, "covering", 1400); S.status[a] = "picked " + shiftLabel(sid);
            if (owner) S.edges.push({ from: a, to: owner, shift: sid, kind: "pick", state: "pick" });
          } else { setFace(a, "shrug"); S.status[a] = "passed"; }
        });
        const n = picks.filter(([, s]) => s).length;
        setStatus(`Round ${ev.iteration}: <b>${n} pick${n === 1 ? "" : "s"}</b>, ${picks.length - n} pass${picks.length - n === 1 ? "" : "es"}.`);
        break;
      }
      case "released":
        setStatus(`${listNames(ev.agents)} passed and keep their own shifts; the rest pick again.`); break;
      case "counter_window":
        setStatus(`No ring yet. <b>Counter-offer window</b>: ${ev.seconds} s for any mascot that asked its student.`); break;
      case "cycle": {
        S.edges = S.edges.filter((e) => e.kind !== "pick");
        ev.moves.forEach((m) => S.edges.push({ from: m.to_agent, to: m.from_agent, shift: m.shift_id, kind: "ring", state: "proposed", members: ev.members }));
        ev.members.forEach((a) => { setFace(a, "walking", 1500); S.status[a] = "in a ring"; });
        setStatus(`A <b>${ev.members.length}-way ring</b> closed: ${listNames(ev.members)}. Everyone keeps their hours.`); break;
      }
      case "chain":
        S.edges = S.edges.filter((e) => e.kind !== "pick");
        ev.moves.forEach((m, i) => S.edges.push({ from: m.to_agent, to: m.from_agent, shift: m.shift_id, kind: i === 0 ? "cover" : "chain", state: "proposed" }));
        setStatus(ev.moves.length === 1 ? `${name(ev.moves[0].to_agent)} offers to cover ${name(ev.moves[0].from_agent)}'s ${shiftLabel(ev.moves[0].shift_id)}.`
          : `A cover chain formed through ${listNames([ev.moves[0].to_agent, ...ev.moves.map((m) => m.from_agent)])}.`); break;
      case "selected":
        setStatus(`Every member re-checked the exact trade privately. CP-SAT kept <b>${ev.proposals.length}</b> (${ev.status.toLowerCase()}).`); break;
      case "prepare":
        S.txnMembers[ev.txn_id] = ev.members; S.votes[ev.txn_id] = {};
        ev.members.forEach((a) => { S.status[a] = "asked to confirm"; });
        setStatus(`Waiting for ${listNames(ev.members)} and the manager to confirm. Shifts are on hold.`); break;
      case "vote":
        (S.votes[ev.txn_id] = S.votes[ev.txn_id] || {})[ev.agent] = ev.vote;
        if (ev.agent !== "steward") S.status[ev.agent] = { yes: "confirmed", no: "declined", stale: "week changed", timeout: "no answer" }[ev.vote];
        break;
      case "commit": {
        const ring = ev.proposal.startsWith("ring");
        S.edges.forEach((e) => { if (ev.moves.some((m) => m.shift_id === e.shift)) e.state = "commit"; });
        ev.moves.forEach((m, i) => {
          S.moved[m.shift_id] = ring || i > 0 ? "moved" : "covered";
          S.requested.delete(m.shift_id);
          if (S.roster[m.shift_id]) S.roster[m.shift_id] = { ...S.roster[m.shift_id], owner: m.to_agent };
        });
        ev.members.forEach((a) => { setFace(a, "relieved", 3200); S.status[a] = "traded"; });
        S.committed.push(ev);
        setStatus(`<b>Committed.</b> Every student and the manager said yes. ${ev.moves.length} shift${ev.moves.length > 1 ? "s" : ""} moved.`);
        renderBoard(); break;
      }
      case "abort":
        S.edges.forEach((e) => { if (ev.moves.some((m) => m.shift_id === e.shift)) e.state = "abort"; });
        ev.members.forEach((a) => { setFace(a, "failed", 3000); S.status[a] = "nothing moved"; });
        setStatus(`<b>Aborted.</b> A week changed before commit, so nothing moved. Trying again with fresh data.`);
        setTimeout(() => { S.edges = S.edges.filter((e) => e.state !== "abort"); }, 2600); break;
      case "schedule_edited":
        S.status[ev.agent] = "week changed"; break;
      case "summary":
        S.summary = ev; (ev.open_shifts || []).forEach((s) => S.open.add(s));
        setStatus(`Week done: <b>${ev.fixed} of ${ev.asked}</b> fixed.`);
        renderKpis(); setFinding(ev); renderBoard(); break;
    }
    if (live || t === "summary" || t === "reset") logEvent(ev);
    else logEvent(ev);
  }
  const cap = (s) => s[0].toUpperCase() + s.slice(1);

  function setStatus(html) { $("#roundStatus").innerHTML = html; }

  function setFinding(sum) {
    const el = $("#finding");
    if (!sum) { el.textContent = "Mascots check every student's week on Sunday and trade shifts so nobody loses pay or breaks a limit their employer can't see."; return; }
    const rings = S.committed.filter((c) => c.proposal.startsWith("ring"));
    const parts = [];
    if (rings.length) parts.push(`${listNames(rings[0].members)} traded in a ${rings[0].members.length}-way ring and kept their pay`);
    const chains = S.committed.filter((c) => c.proposal.startsWith("chain"));
    chains.forEach((c) => {
      if (c.moves.length === 1) parts.push(`${name(c.moves[0].to_agent)} covered ${name(c.moves[0].from_agent)}'s ${shiftLabel(c.moves[0].shift_id)}`);
      else parts.push(`a chain through ${listNames(c.members)} fixed ${c.moves.length}`);
    });
    let text = parts.length ? cap(parts.join("; ")) + "." : "No trade went through this week.";
    (sum.open_shifts || []).forEach((s) => {
      const r = S.roster[s];
      text += ` ${r ? name(r.owner) + "'s " : ""}${shiftLabel(s)} has no safe trade, so the manager sees it as an open shift.`;
    });
    el.innerHTML = text.replace(/(\d+-way ring)/, "<b>$1</b>");
  }

  function renderKpis() {
    const s = S.summary;
    $("#kFixed").innerHTML = `${s ? s.fixed : 0}<small> of ${s ? s.asked : S.requested.size}</small>`;
    $("#kPay").textContent = money(s ? s.pay_kept : 0);
    $("#kBreaks").textContent = "0";
    const open = s ? s.open : 0;
    $("#kOpen").textContent = String(open);
    $("#kOpen").classList.toggle("bad", open > 0);
  }

  // ---------- log ----------
  function sentence(ev) {
    const m = (x) => `${name(x.to_agent)} takes ${name(x.from_agent)}'s ${shiftLabel(x.shift_id)}`;
    switch (ev.type) {
      case "sunday_check": return "Sunday check sent to every mascot.";
      case "trade_request": return `${name(ev.agent)} asked for a trade on ${shiftLabel(ev.shift_id)}. No reason attached.`;
      case "picks": {
        const p = Object.entries(ev.picks);
        const picked = p.filter(([, s]) => s).map(([a, s]) => `${name(a)} → ${shiftLabel(s)}`);
        const passed = p.filter(([, s]) => !s).map(([a]) => name(a));
        return `${cap(ev.phase)} round ${ev.iteration}: ${picked.length ? picked.join(", ") : "no picks"}${passed.length ? `; passed: ${passed.join(", ")}` : ""}.`;
      }
      case "counter_window": return `No ring closed. Counter-offer window, ${ev.seconds} s.`;
      case "cycle": return `<span class="tr">Ring closed</span>: ${ev.moves.map(m).join("; ")}.`;
      case "chain": return `<span class="tr">Chain</span>: ${ev.moves.map(m).join("; ")}.`;
      case "selected": return `CP-SAT kept ${ev.proposals.length} of ${ev.proposals.length + ev.dropped.length} proposals (${ev.status}).`;
      case "prepare": return `Prepare ${ev.txn_id}: holds placed, asking ${listNames(ev.members)} and the manager.`;
      case "vote": {
        const cls = ev.vote === "yes" ? "ok" : "bad";
        const word = { yes: "confirmed", no: "declined", stale: "week changed (stale)", timeout: "timed out" }[ev.vote];
        return `${cap(name(ev.agent))} <span class="${cls}">${word}</span>.`;
      }
      case "commit": return `<span class="ok">Committed</span> ${ev.txn_id}: ${ev.moves.map(m).join("; ")}.`;
      case "abort": return `<span class="bad">Aborted</span> ${ev.txn_id}. Holds released, shifts unchanged.`;
      case "schedule_edited": return `${name(ev.agent)}'s week changed while the trade waited for confirmations.`;
      case "summary": return `Week done: ${ev.fixed} of ${ev.asked} fixed, ${money(ev.pay_kept)} of pay kept by trading, ${ev.open} open.`;
      case "reset": return "Demo reset.";
      default: return null;
    }
  }
  function logEvent(ev) {
    const text = sentence(ev);
    if (!text) return;
    const li = document.createElement("li");
    li.innerHTML = `<time>${clock(ev.ts)}</time><span>${text}</span>`;
    const list = $("#events");
    list.prepend(li);
    $("#logCount").textContent = `${list.children.length} events`;
  }

  // ---------- arena ----------
  const canvas = $("#arenaCanvas");
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0;
  function resize() {
    const r = $("#stage").getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    W = r.width; H = r.height;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function pos(a) {
    const th = (ANGLE[a] ?? 0) * Math.PI / 180;
    const narrow = W < 560;
    const rx = W * (narrow ? 0.33 : 0.34), ry = H * (narrow ? 0.30 : 0.31);
    return { x: W / 2 + rx * Math.cos(th), y: H / 2 - 8 + ry * Math.sin(th) };
  }
  function petBox() { const h = Math.max(64, Math.min(104, H * 0.25, W * 0.15)); return { w: h * 192 / 208, h }; }

  function arrow(x1, y1, x2, y2, color, width, dash, label, labelColor) {
    const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len;
    const trim = petBox().h * 0.5;
    const sx = x1 + ux * trim, sy = y1 + uy * trim, ex = x2 - ux * trim, ey = y2 - uy * trim;
    // slight bend so A->B and B->A don't overlap
    const nx = -uy, ny = ux, bend = 18;
    const cx = (sx + ex) / 2 + nx * bend, cy = (sy + ey) / 2 + ny * bend;
    ctx.save();
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash || []);
    ctx.beginPath(); ctx.moveTo(sx, sy); ctx.quadraticCurveTo(cx, cy, ex, ey); ctx.stroke();
    ctx.setLineDash([]);
    const ang = Math.atan2(ey - cy, ex - cx), ah = 6 + width * 2;
    ctx.beginPath(); ctx.moveTo(ex, ey);
    ctx.lineTo(ex - ah * Math.cos(ang - 0.42), ey - ah * Math.sin(ang - 0.42));
    ctx.lineTo(ex - ah * Math.cos(ang + 0.42), ey - ah * Math.sin(ang + 0.42));
    ctx.closePath(); ctx.fill();
    if (label) {
      const lx = (sx + ex) / 2 + nx * (bend * 0.55), ly = (sy + ey) / 2 + ny * (bend * 0.55);
      ctx.font = `500 12px ${getComputedStyle(document.body).fontFamily}`;
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = "#ffffff"; ctx.fillRect(lx - tw / 2 - 5, ly - 9, tw + 10, 18);
      ctx.fillStyle = labelColor || color; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(label, lx, ly);
    }
    ctx.restore();
  }

  function frame(t) {
    if (!W) resize();
    ctx.clearRect(0, 0, W, H);
    const font = getComputedStyle(document.body).fontFamily;
    // the table: a quiet ellipse the pets stand around
    ctx.save(); ctx.strokeStyle = "#e4e2dd"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.ellipse(W / 2, H / 2 - 8, W * 0.34, H * 0.31, 0, 0, Math.PI * 2); ctx.stroke(); ctx.restore();

    const hue = "#1d5fbf", grey = "#8c8a86", neg = "#c4242a";
    for (const e of S.edges) {
      if (!(e.from in ANGLE) || !(e.to in ANGLE)) continue;
      const a = pos(e.from), b = pos(e.to);
      const label = shiftLabel(e.shift);
      if (e.state === "abort") arrow(a.x, a.y, b.x, b.y, neg, 2, [6, 5], label, neg);
      else if (e.kind === "pick") arrow(a.x, a.y, b.x, b.y, grey, 1.5, null, label, "#5d5b57");
      else if (e.kind === "ring") arrow(a.x, a.y, b.x, b.y, hue, e.state === "commit" ? 3.5 : 3, null, label, hue);
      else arrow(a.x, a.y, b.x, b.y, hue, 2, [7, 5], label, hue);
    }
    const box = petBox();
    for (const a of ORDER) {
      if (!(a in S.names)) continue;
      const p = pos(a), face = faceOf(a, performance.now());
      const flip = p.x > W / 2 + 4;
      const x = p.x - box.w / 2, y = p.y - box.h / 2 - 6;
      if (!Sprites.draw(ctx, S.pets[a] || "debug-duck-v2", face, t, x, y, box.w, box.h, flip)) {
        ctx.fillStyle = "#cfccc6"; ctx.beginPath(); ctx.arc(p.x, p.y - 6, box.h / 3, 0, 7); ctx.fill();
      }
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      ctx.fillStyle = "#121212"; ctx.font = `600 13px ${font}`;
      ctx.fillText(S.names[a], p.x, y + box.h + 2);
      ctx.fillStyle = "#5d5b57"; ctx.font = `400 12px ${font}`;
      ctx.fillText(S.status[a] || "", p.x, y + box.h + 18);
      // the vote, once asked
      const txn = Object.keys(S.votes).pop();
      const v = txn && S.votes[txn][a];
      if (v) {
        const ok = v === "yes", cx = x + box.w - 4, cy = y + 10;
        ctx.fillStyle = ok ? "#24753a" : neg; ctx.beginPath(); ctx.arc(cx, cy, 9, 0, 7); ctx.fill();
        ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.beginPath();
        if (ok) { ctx.moveTo(cx - 4, cy); ctx.lineTo(cx - 1, cy + 3); ctx.lineTo(cx + 4, cy - 3); }
        else { ctx.moveTo(cx - 3.5, cy - 3.5); ctx.lineTo(cx + 3.5, cy + 3.5); ctx.moveTo(cx + 3.5, cy - 3.5); ctx.lineTo(cx - 3.5, cy + 3.5); }
        ctx.stroke();
      }
    }
    // the manager's approval, bottom centre
    const txn = Object.keys(S.votes).pop();
    if (txn && S.txnMembers[txn]) {
      const v = S.votes[txn].steward;
      ctx.textAlign = "center"; ctx.textBaseline = "alphabetic"; ctx.font = `500 12px ${font}`;
      ctx.fillStyle = v === "yes" ? "#24753a" : v ? neg : "#5d5b57";
      ctx.fillText(v === "yes" ? "Manager approved" : v ? "Manager: " + v : "Manager: waiting", W / 2, H - 12);
    }
    requestAnimationFrame(frame);
  }

  // ---------- roster board ----------
  async function refreshRoster() {
    try {
      const st = await get("/state");
      S.roster = {}; st.roster.forEach((r) => { S.roster[r.shift_id] = r; });
      Object.values(st.agents).forEach((a) => { S.pets[a.agent_id] = a.pet_id; });
      renderBoard();
    } catch (_) { /* broker restarting */ }
  }
  function renderBoard() {
    const el = $("#board");
    const people = ORDER.slice().sort((a, b) => ["ana", "ben", "dev", "priya", "zoe", "marco"].indexOf(a) - ["ana", "ben", "dev", "priya", "zoe", "marco"].indexOf(b));
    const monday = new Date("2026-10-26T00:00:00-07:00");
    const html = ['<div class="day" role="columnheader"></div>'];
    DAYS.forEach((d, i) => { const day = new Date(monday.getTime() + i * 864e5); html.push(`<div class="day" role="columnheader">${d} ${day.getDate()}</div>`); });
    for (const p of people) {
      if (!(p in S.names)) continue;
      html.push(`<div class="who" role="rowheader"><canvas data-pet="${S.pets[p] || ""}"></canvas><span>${S.names[p]}</span></div>`);
      for (let i = 0; i < 7; i++) {
        const shifts = Object.values(S.roster).filter((r) => r.owner === p && (phx(r.start).getDay() + 6) % 7 === i
          && phx(r.start) >= monday && phx(r.start) < new Date(monday.getTime() + 7 * 864e5))
          .sort((a, b) => phx(a.start) - phx(b.start));
        const chips = shifts.map((r) => {
          const id = r.shift_id;
          const cls = S.open.has(id) ? "open" : S.moved[id] || (S.requested.has(id) ? "req" : "");
          const title = { open: "no safe trade", moved: "traded in", covered: "covered", req: "wants a trade" }[cls] || "shift";
          return `<span class="chip ${cls}" title="${span(r)}: ${title}">${S.open.has(id) ? "open" : span(r, true)}</span>`;
        }).join("");
        html.push(`<div class="cell" role="cell">${chips}</div>`);
      }
    }
    el.innerHTML = html.join("");
    el.querySelectorAll("canvas").forEach((c) => Sprites.badge(c, c.dataset.pet || "debug-duck-v2", "idle"));
  }

  // ---------- phones (synthetic demo only) ----------
  const phoneState = {};
  function buildPhones() {
    const wrap = $("#phones");
    const slots = ["ana", "ben", "dev", "manager"];
    wrap.innerHTML = "";
    slots.forEach((who, i) => {
      const el = document.createElement("article");
      el.className = "phone"; el.dataset.ui = "";
      const options = who === "manager" ? "" : `<select aria-label="Whose phone">${Object.keys(S.names).map((s) => `<option value="${s}"${s === who ? " selected" : ""}>${S.names[s]}</option>`).join("")}</select>`;
      el.innerHTML = `<header class="phone-head">${who === "manager" ? "" : '<canvas></canvas>'}<div><div class="who"></div><div class="sub"></div></div>${options}</header>
        <div class="thread" aria-live="polite"></div>
        ${who === "manager" ? "" : '<form class="compose"><input type="text" placeholder="Text your mascot, e.g. dentist Thu 3pm" aria-label="Message"><button type="submit">Send</button></form>'}`;
      wrap.appendChild(el);
      const state = phoneState[i] = { who, el, count: -1 };
      const sel = el.querySelector("select");
      if (sel) sel.addEventListener("change", () => { state.who = sel.value; state.count = -1; dress(state); poll(state); });
      const form = el.querySelector("form");
      if (form) form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = form.querySelector("input"); const text = input.value.trim(); if (!text) return;
        input.value = ""; await post(`/phone/${state.who}/text`, { text }).catch(() => {}); poll(state);
      });
      dress(state);
    });
    setInterval(() => Object.values(phoneState).forEach(poll), 1200);
  }
  function dress(state) {
    const head = state.el.querySelector(".phone-head");
    head.querySelector(".who").textContent = state.who === "manager" ? "Library manager" : `${S.names[state.who]}'s phone`;
    head.querySelector(".sub").textContent = state.who === "manager" ? "approves trades with one tap" : "Telegram, private to " + S.names[state.who];
    const c = head.querySelector("canvas");
    if (c) Sprites.badge(c, S.pets[state.who] || "debug-duck-v2", "idle");
  }
  async function poll(state) {
    let data;
    try { data = await get(`/phone/${state.who}`); } catch (_) { return; }
    const msgs = data.messages || [];
    if (msgs.length === state.count) return;
    const fresh = state.count >= 0 && msgs.length > state.count;
    state.count = msgs.length;
    const thread = state.el.querySelector(".thread");
    if (!msgs.length) { thread.innerHTML = `<p class="empty">No messages. ${state.who === "manager" ? "Trade requests land here." : "The mascot only texts when something collides."}</p>`; return; }
    let lastButtons = -1;
    msgs.forEach((m, i) => { if (m.buttons && m.buttons.length) lastButtons = i; });
    const answered = msgs.slice(lastButtons + 1).some((m) => m.kind === "reply");
    thread.innerHTML = msgs.map((m, i) => {
      const cls = m.kind === "student" ? "msg me" : m.kind === "reply" ? "msg reply" : "msg";
      const live = i === lastButtons && !answered;
      const btns = (m.buttons || []).length ? `<div class="btns">${m.buttons.map((b) => `<button type="button" data-data="${b.data}"${live ? "" : " disabled"}>${b.label}</button>`).join("")}</div>` : "";
      return `<div class="${cls}${fresh && i === msgs.length - 1 ? " flash" : ""}">${escapeHtml(m.text)}${btns}</div>`;
    }).join("");
    thread.querySelectorAll("button[data-data]").forEach((b) => b.addEventListener("click", async () => {
      b.closest(".btns").querySelectorAll("button").forEach((x) => (x.disabled = true));
      await post(`/phone/${state.who}/tap`, { data: b.dataset.data }).catch(() => {});
      poll(state);
    }));
    thread.scrollTop = thread.scrollHeight;
  }
  function escapeHtml(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  // ---------- simulation ----------
  async function renderSim() {
    let d;
    try { d = await get("/sim"); } catch (_) { $("#sim").innerHTML = '<p class="muted">Run <code>python -m sim.simulate</code> to fill this in.</p>'; return; }
    $("#simMeta").textContent = `${d.weeks.toLocaleString("en-US")} synthetic weeks, ${Math.round(d.conflict_rate * 100)}% of shifts collide`;
    const maxPay = Math.max(d.plain_pay_lost, d.tagout_pay_lost);
    $("#sim").innerHTML = `
      <div class="sim-figs">
        <div><span class="label">Conflicts fixed by plain covers</span><span class="value num">${d.plain_pct.toFixed(1)}%</span></div>
        <div><span class="label">With Tag Out's trades</span><span class="value num">${d.tagout_pct.toFixed(1)}%<small> +${d.extra_points.toFixed(1)} points ± ${d.extra_ci.toFixed(1)}</small></span></div>
      </div>
      <div class="bars" role="img" aria-label="Pay lost per week">
        <span>Pay lost / week</span><span></span><span></span>
        <span class="muted">Plain covers</span><span class="track"><span class="fill" style="width:${100 * d.plain_pay_lost / maxPay}%"></span></span><span class="v num">${money(d.plain_pay_lost)}</span>
        <span class="muted">Tag Out</span><span class="track"><span class="fill hue" style="width:${100 * d.tagout_pay_lost / maxPay}%"></span></span><span class="v num">${money(d.tagout_pay_lost)}</span>
      </div>
      <p class="sim-note">Winter break (F-1 limit 40 h): ${d.winter.handed.toFixed(1)} of ${d.winter.wanted.toFixed(0)} shifts handed off a week, ${money(d.winter.kept)} kept on campus, ${d.winter.rule_breaks} rule breaks; an unchecked group chat makes about ${d.winter.unchecked_breaks.toFixed(0)} a week. <a href="https://github.com/neric-joel/tag-out/blob/main/docs/SIMULATION.md">Method and assumptions</a>.</p>`;
  }

  // ---------- judge view ----------
  async function renderJudge() {
    let d;
    try { d = await get("/admin/judge"); } catch (_) { return; }
    const rows = Object.values(d).map((s) => {
      const bind = s.rooms.reduce((a, b) => ((b.unit === "$" ? b.room / 16 : b.room) < (a.unit === "$" ? a.room / 16 : a.room) ? b : a));
      const rule = { f1_weekly_20: "F-1 20 h a week, all jobs", f1_break_40: "F-1 40 h (break)", aca_25_avg: "25 h average", weekly_40: "40 h a week", fws_award: "Work-Study award" }[bind.rule_id] || bind.rule_id;
      const room = bind.unit === "$" ? money(bind.room) : `${bind.room.toFixed(1)} h`;
      const cover = bind.unit === "$" ? bind.room - 64 : bind.room - 4;
      const other = Object.entries(s.other_employers).map(([k, v]) => `${v} h ${k}`).join(", ");
      return `<tr><td>${s.name}<span class="sub">${s.f1 ? "F-1" : "domestic"}${s.fws ? ", Work-Study" : ""}</span></td>
        <td class="num">${s.week_hours.toFixed(0)} h<span class="sub">${other ? "incl. " + other : "Library only"}</span></td>
        <td>${rule}</td><td class="num">${room}</td>
        <td class="${cover < 0 ? "over" : ""}">${cover < 0 ? "would break it" : "fits"}</td></tr>`;
    }).join("");
    $("#limits").innerHTML = `<thead><tr><th>Student</th><th class="num">This week</th><th>Limit that binds first</th><th class="num">Room left</th><th>One more 4 h shift</th></tr></thead><tbody>${rows}</tbody>`;
    try {
      const f = await get("/forecast");
      $("#forecast").innerHTML = `<h3>Crunch forecast for the manager</h3>
        <p class="muted small" style="margin-bottom:8px">Counts only, shown when ${f.k} or more of ${f.staff} staff are busy. No names, no reasons.</p>
        <ul>${f.alerts.length ? f.alerts.map((a) => `<li><span>${a.slot}</span><span class="num">${a.busy} of ${a.staff} busy</span></li>`).join("") : "<li><span>No crunch next week.</span><span></span></li>"}</ul>`;
    } catch (_) { /* steward down */ }
  }

  // ---------- controls ----------
  function wire() {
    $("#btnSunday").addEventListener("click", () => post("/demo/sunday").catch(() => {}));
    $("#btnRun").addEventListener("click", () => post("/demo/run").catch(() => {}));
    $("#btnReset").addEventListener("click", () => post("/admin/reset").catch(() => {}));
    $("#btnBreak").addEventListener("click", () => post("/demo/break").catch(() => {}));
    window.addEventListener("resize", () => { resize(); });
  }

  function connect() {
    const live = $("#live"), text = $("#liveText");
    const es = new EventSource("/events");
    es.onopen = () => { live.className = "live on"; text.textContent = "Live"; };
    es.onerror = () => { live.className = "live off"; text.textContent = "Reconnecting"; };
    es.onmessage = (m) => { try { onEvent(JSON.parse(m.data), true); } catch (err) { console.error(err); } };
  }

  async function boot() {
    const [st, ag] = await Promise.all([get("/state"), get("/agents")]);
    S.debug = !!st.debug; S.names = ag.names; S.petMeta = st.pets;
    Object.values(st.agents).forEach((a) => { S.pets[a.agent_id] = a.pet_id; });
    st.roster.forEach((r) => { S.roster[r.shift_id] = r; });
    document.querySelectorAll("[data-debug]").forEach((el) => { el.hidden = !S.debug; });
    $("#tabJudge").hidden = !S.debug;
    (JUDGE ? $("#tabJudge") : $("#tabArena")).setAttribute("aria-current", "page");
    if (JUDGE && S.debug) { $("#debugBanner").hidden = false; $("#judgePanel").hidden = false; renderJudge(); setInterval(renderJudge, 4000); }
    const used = new Set(Object.values(S.pets));
    const credits = S.petMeta.filter((p) => used.has(p.id)).map((p) => `<a href="${p.page}">${escapeHtml(p.name)}</a> by ${escapeHtml(p.creator)}`);
    $("#credits").innerHTML = `Mascots from <a href="https://codex-pets.net">Codex Pets</a>: ${credits.join(", ")}. Each student picked their own.`;
    renderKpis(); renderBoard(); renderSim(); wire(); resize(); requestAnimationFrame(frame);
    if (S.debug) buildPhones();
    connect();
  }
  boot().catch((e) => { $("#roundStatus").textContent = "Can't reach the broker. Start it with: python -m scripts.run_all"; console.error(e); });
})();
