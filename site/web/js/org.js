/* Tag Out org chart: the campus hierarchy (seeds/org.py) as a tree of pets. Each escalation moves a case up one
   rung; the rung holding it shows a countdown, and silence moves it up again. Nodes can be dragged. */
(function () {
  "use strict";
  const W = 1200, H = 720;
  const TIERS = { top: 22, backup: 128, manager: 236, lead: 344, students: 462 };
  const RULE = { no_cover_2h: "2 h without a cover", no_answer_30m: "no answer in 30 min (silence counts as no)",
    safety_first: "a safety report goes to Environmental Health and Safety at once" };
  const SUB = { dining_gm: "Aramark, both dining halls", rec_ad: "Sun Devil Fitness", ehs: "ASU EHS · safety reports",
    se: "weekly count of ASU cases", issc: "F-1 questions only" };
  const OUTCOME = { covered: "Covered", acknowledged: "Acknowledged", answered: "Answered", closed: "Closed", excused: "Excused" };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const clockText = (d) => `${d.getHours() % 12 || 12}:${String(d.getMinutes()).padStart(2, "0")} ${d.getHours() >= 12 ? "PM" : "AM"}`;
  const dayText = (d) => ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getDay()];
  const store = { get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (_) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* private mode */ } } };

  function create(root, opts) {
    const judge = !!opts.judge;
    root.innerHTML = `
      <div class="org-head">
        <div class="org-clock"><span class="muted small">Story time</span><b id="orgClock">Sat 6:30 AM</b><span class="muted small" id="orgPace"></span></div>
        <div class="org-tools"><button class="btn small-btn" type="button" data-act="reset-layout">Reset layout</button></div>
      </div>
      <div class="org-body">
        <div class="org-viewport"><div class="org-stage" role="group" aria-label="Org chart: students, shift leads, managers, backup managers, Environmental Health and Safety, Student Employment and ISSC">
          <svg class="org-wires" viewBox="0 0 ${W} ${H}" aria-hidden="true"></svg></div></div>
        <aside class="org-side">
          <section class="org-cases" aria-live="polite"><h3>Cases</h3><div id="orgCases"><p class="muted small">No cases yet. Play the morning to watch one climb.</p></div></section>
          <section class="org-inbox"><h3 id="orgInboxTitle">Inbox</h3><p class="muted small" id="orgInboxSub">Click anyone on the chart to read what landed on their phone.</p><div class="thread tg-thread" id="orgInbox"></div></section>
        </aside>
      </div>`;
    const viewport = root.querySelector(".org-viewport"), stage = root.querySelector(".org-stage"), wires = root.querySelector(".org-wires");
    const nodes = new Map(), edges = [], cases = new Map();
    let last = null; // {sim: Date, at: ms, minute}
    let selected = null, phoneOf = opts.phoneOf || (() => []);
    const saved = store.get("tagout.org.layout", {});

    function node(id, kind, title, sub, pet, x, y) {
      const el = document.createElement("article");
      el.className = `org-node org-${kind}`; el.tabIndex = 0; el.dataset.id = id;
      el.setAttribute("aria-label", `${title}, ${sub}`);
      el.innerHTML = `<canvas class="org-pet" width="40" height="43" aria-hidden="true"></canvas><div class="org-text"><b>${esc(title)}</b><span class="org-sub">${esc(sub)}</span><span class="org-status"></span></div><span class="org-timer" hidden></span>`;
      stage.appendChild(el);
      const pos = saved[id] || { x, y };
      const n = { id, el, kind, x: pos.x, y: pos.y, home: { x, y }, w: kind === "student" ? 118 : 196, h: kind === "student" ? 54 : 62, pet, face: "idle" };
      place(n);
      if (window.Sprites) Sprites.badge(el.querySelector("canvas"), pet || "debug-duck-v2", "idle");
      el.addEventListener("click", () => { if (!n.dragged) inbox(id); });
      el.addEventListener("keydown", (e) => {
        const step = e.shiftKey ? 64 : 16, d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
        if (d) { e.preventDefault(); n.x = Math.max(0, Math.min(W - n.w, n.x + d[0])); n.y = Math.max(0, Math.min(H - n.h, n.y + d[1])); place(n); route(); keep(); }
        if (e.key === "Enter") inbox(id);
      });
      drag(n);
      nodes.set(id, n);
      return n;
    }
    function place(n) { Object.assign(n.el.style, { left: n.x + "px", top: n.y + "px", width: n.w + "px", height: n.h + "px" }); }
    function keep() { const out = {}; nodes.forEach((n) => { if (n.x !== n.home.x || n.y !== n.home.y) out[n.id] = { x: n.x, y: n.y }; }); store.set("tagout.org.layout", out); }
    function drag(n) {
      let start = null;
      n.el.addEventListener("pointerdown", (e) => { if (e.button) return; start = { px: e.clientX, py: e.clientY, x: n.x, y: n.y, scale: scale() }; n.dragged = false; n.el.setPointerCapture(e.pointerId); });
      n.el.addEventListener("pointermove", (e) => {
        if (!start) return;
        const dx = (e.clientX - start.px) / start.scale, dy = (e.clientY - start.py) / start.scale;
        if (!n.dragged && Math.hypot(dx, dy) < 4) return;
        n.dragged = true; n.el.classList.add("dragging");
        n.x = Math.max(0, Math.min(W - n.w, start.x + dx)); n.y = Math.max(0, Math.min(H - n.h, start.y + dy)); place(n); route();
      });
      const end = () => { if (start && n.dragged) keep(); start = null; n.el.classList.remove("dragging"); setTimeout(() => { n.dragged = false; }, 0); };
      n.el.addEventListener("pointerup", end); n.el.addEventListener("pointercancel", end);
    }
    // fit the column's width, and the window's height under the panel's own header, so the whole chart is on
    // screen at once (the window's height is in the page's own pixels: the demo video zooms the page)
    function scale() {
      const z = parseFloat(getComputedStyle(document.documentElement).zoom) || 1, panel = viewport.closest(".panel") || viewport;
      const head = (viewport.getBoundingClientRect().top - panel.getBoundingClientRect().top) / z;
      return Math.min(1, viewport.clientWidth / W, Math.max(0.5, (innerHeight / z - 32 - head - 24) / H)) || 1;
    }
    function fit() { const s = scale(); stage.style.transform = `scale(${s})`; viewport.style.height = H * s + "px"; }
    addEventListener("resize", fit);
    new ResizeObserver(fit).observe(viewport);

    function edge(a, b, dashed) {
      const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("class", "org-edge" + (dashed ? " also" : ""));
      wires.appendChild(p);
      edges.push({ a, b, p });
    }
    function anchor(n, side) { return side === "top" ? [n.x + n.w / 2, n.y] : [n.x + n.w / 2, n.y + n.h]; }
    function curve(a, b) {
      const [x1, y1] = anchor(a, "top"), [x2, y2] = anchor(b, "bottom");
      const m = (y1 + y2) / 2;
      return `M${x1},${y1} C${x1},${m} ${x2},${m} ${x2},${y2}`;
    }
    function route() { edges.forEach((e) => { const a = nodes.get(e.a), b = nodes.get(e.b); if (a && b) e.p.setAttribute("d", curve(a, b)); }); }

    // ---- build the tree from /org ----
    function build(data) {
      const roles = data.roles, depts = ["library", "dining", "rec"];
      const span = W / 3;
      // the offices above every department; each employer's own chain sits under them
      ["issc", "se", "ehs"].forEach((r, k) => node(r, r, roles[r].name, SUB[r], roles[r].pet_id, [60, W / 2 - 98, W - 256][k], TIERS.top));
      depts.forEach((d, i) => {
        const dep = data.departments[d], lead = dep.lead, mgr = dep.manager, x0 = i * span;
        node(mgr, "manager", roles[mgr].name, dep.name, roles[mgr].pet_id, x0 + span / 2 - 98, TIERS.manager);
        node(lead, "lead", roles[lead].name, d === "dining" ? "Aramark shift lead" : "shift lead", roles[lead].pet_id, x0 + span / 2 - 98, TIERS.lead);
        if (dep.backup) { node(dep.backup, "backup", roles[dep.backup].name, SUB[dep.backup], roles[dep.backup].pet_id, x0 + span / 2 - 98, TIERS.backup); edge(mgr, dep.backup); }
        edge(lead, mgr);
        if (dep.asu) { edge(mgr, "ehs", true); edge(mgr, "se", true); }
        const mine = data.students.filter((s) => s.dept === d);
        mine.forEach((s, k) => {
          const col = k % 3, row = Math.floor(k / 3);
          node(s.id, "student", s.name, s.also && s.also.length ? `also ${s.also.map((a) => ({ dining: "Dining", rec: "Rec" }[a] || a)).join(", ")}` : s.elsewhere ? "also Aramark, Barrett" : "student worker",
            s.pet_id, x0 + 14 + col * (span - 28) / 3, TIERS.students + row * 92);
          edge(s.id, lead);
        });
      });
      data.students.forEach((s) => (s.also || []).forEach((d) => edge(s.id, data.departments[d].lead, true)));
      route(); fit();
      root.querySelector('[data-act="reset-layout"]').addEventListener("click", () => { nodes.forEach((n) => { n.x = n.home.x; n.y = n.home.y; place(n); }); route(); store.set("tagout.org.layout", {}); });
      renderCases();
    }

    // ---- live: events, packets, timers ----
    function status(id, text, tone) { const n = nodes.get(id); if (!n) return; const s = n.el.querySelector(".org-status"); s.textContent = text || ""; s.dataset.tone = tone || ""; }
    function face(id, f) { const n = nodes.get(id); if (!n) return; const c = n.el.querySelector("canvas"); if (c) c.dataset.face = f; }
    function holder(id, on) { const n = nodes.get(id); if (n) n.el.classList.toggle("holding", !!on); }
    function packet(from, to, kind) {
      const a = nodes.get(from), b = nodes.get(to);
      if (!a || !b || matchMedia("(prefers-reduced-motion: reduce)").matches) { if (b) { b.el.classList.add("ping"); setTimeout(() => b.el.classList.remove("ping"), 500); } return; }
      const up = b.y < a.y, [x1, y1] = up ? anchor(a, "top") : anchor(a, "bottom"), [x2, y2] = up ? anchor(b, "bottom") : anchor(b, "top");
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("r", kind === "up" ? 7 : 5); dot.setAttribute("class", "org-packet " + (kind || ""));
      wires.appendChild(dot);
      const t0 = performance.now(), dur = kind === "up" ? 900 : 600;
      (function step(t) {
        const k = Math.min(1, (t - t0) / dur), e = k * k * (3 - 2 * k);
        dot.setAttribute("cx", x1 + (x2 - x1) * e); dot.setAttribute("cy", y1 + (y2 - y1) * e);
        if (k < 1) requestAnimationFrame(step); else { dot.remove(); b.el.classList.add("ping"); setTimeout(() => b.el.classList.remove("ping"), 500); }
      })(t0);
    }
    function simNow() {
      if (!last) return null;
      // the story clock only runs while some case is waiting on someone
      if (![...cases.values()].some((c) => c.status === "open")) return last.sim;
      return new Date(last.sim.getTime() + (performance.now() - last.at) / last.minute / 1000 * 60000);
    }
    function tick() {
      const now = simNow();
      if (!now) return;
      root.querySelector("#orgClock").textContent = `${dayText(now)} ${clockText(now)}`;
      const shown = new Set();
      cases.forEach((c) => {
        const n = nodes.get(c.holder); if (!n || c.status !== "open" || !c.deadline) return;
        const t = n.el.querySelector(".org-timer");
        shown.add(c.holder);
        const left = Math.round((c.deadline - now) / 60000);
        t.hidden = false; t.textContent = c.acting ? "waiting for both to confirm" : left > 0 ? `moves up in ${left >= 60 ? Math.floor(left / 60) + " h " + (left % 60) + " min" : left + " min"}` : "deadline passed";
        t.classList.toggle("late", left <= 10);
      });
      nodes.forEach((n, id) => { if (!shown.has(id)) n.el.querySelector(".org-timer").hidden = true; });
    }
    setInterval(tick, 200);

    function caseFor(id) { if (!cases.has(id)) cases.set(id, { id, steps: [], status: "open" }); return cases.get(id); }
    const name = (id) => opts.name(id);
    function step(c, ev, text) { c.steps.push({ t: new Date(ev.sim), text }); }

    function event(ev, animate) {
      if (ev.sim) last = { sim: new Date(ev.sim), at: performance.now(), minute: ev.minute || 0.05 };
      if (ev.minute) root.querySelector("#orgPace").textContent = `1 story minute = ${ev.minute} s here`;
      if (ev.type === "org_reset") { reset(); return; }
      if (ev.type === "org_pending") {
        const p = caseFor(ev.case_id);
        Object.assign(p, { status: "pending" });
        step(p, ev, `${name(ev.by)} sent the cited rule and flagged it for an advisor (DSO), who replies by ${clockText(new Date(ev.deadline))}. The case stays open until then.`);
        holder(ev.by, false); status(ev.by, "advisor pending", "wait");
        renderCases(); return;
      }
      const c = ev.case_id ? caseFor(ev.case_id) : null;
      switch (ev.type) {
        case "org_case":
          Object.assign(c, { kind: ev.kind, holder: ev.holder, status: "open", deadline: new Date(ev.deadline), owner: ev.owner || c.owner, shift_id: ev.shift_id || c.shift_id, dept: ev.dept || c.dept, label: ev.shift_label || c.label });
          if (ev.level === 1 && ev.kind === "uncovered_callout") {
            step(c, ev, `${name(ev.owner)} called out of ${c.label || ev.shift_id}. No reason given, and none travels.`);
            status(ev.owner, "called out", "bad"); face(ev.owner, "failed");
          }
          if (ev.kind === "f1_question") step(c, ev, `A question reached ISSC from a student who chose to send it. Only their words came.`);
          if (ev.kind === "safety") step(c, ev, ev.holder === "ehs" ? `Environmental Health and Safety opened its own case. Acknowledge by ${clockText(new Date(ev.deadline))}.`
            : `The ${name(ev.holder).toLowerCase()} on duty has the report. Acknowledge by ${clockText(new Date(ev.deadline))}.`);
          nodes.forEach((n) => holder(n.id, false)); holder(ev.holder, true);
          status(ev.holder, "holding a case", "wait"); face(ev.holder, "review");
          break;
        case "org_ask":
          step(c, ev, ev.iteration === 3 ? `${name(ev.by)} offered it to people who already work for the same employer elsewhere: ${ev.asked.map(name).join(", ")}.`
            : `${name(ev.by)} asked ${ev.asked.length} coworkers who work there${ev.iteration === 2 ? " again, halfway to the deadline" : ""}.`);
          if (animate) ev.asked.forEach((a, i) => setTimeout(() => packet(ev.by, a, "ask"), i * 60));
          ev.asked.forEach((a) => { status(a, "asked", "wait"); face(a, "review"); });
          break;
        case "org_picks": {
          const picked = Object.entries(ev.picks).filter(([, s]) => s).map(([a]) => a);
          const passed = Object.keys(ev.picks).filter((a) => !ev.picks[a]);
          step(c, ev, picked.length ? `${picked.map(name).join(", ")} picked it${passed.length ? `; ${passed.length} passed` : ""}.`
            : `Nobody could take it: ${passed.length} passes. A pass looks the same whatever the reason${judge ? ` (${passed.map(name).join(", ")})` : ""}.`);
          passed.forEach((a) => { status(a, judge ? "passed" : "answered"); face(a, "waiting"); });
          if (!picked.length && ev.picks.raj === null && opts.privateNote && !c.noted) {
            c.noted = true;
            opts.privateNote("raj").then((t) => { if (t) { step(c, ev, t); renderCases(); } });
          }
          picked.forEach((a) => { status(a, "picked it", "ok"); face(a, "jumping"); if (animate) packet(a, ev.by, "ask"); });
          break;
        }
        case "org_escalate":
          c.acting = false;
          step(c, ev, `${RULE[ev.rule] || ev.rule}: up to ${name(ev.to)}. They have until ${clockText(new Date(ev.deadline))}.`);
          if (animate) packet(ev.frm, ev.to, "up");
          status(ev.frm, ev.rule === "no_answer_30m" ? "didn't answer" : ev.rule === "safety_first" ? "sent it up" : "moved it up", ev.rule === "no_answer_30m" ? "bad" : "");
          face(ev.frm, ev.rule === "no_answer_30m" ? "failed" : "waving");
          holder(ev.frm, false);
          Object.assign(c, { holder: ev.to, deadline: new Date(ev.deadline), status: "open" });
          break;
        case "org_hold":
          c.acting = true;
          step(c, ev, `Asking ${ev.members.map(name).join(" and ")} to confirm on their phones. Nothing moves without both.`);
          ev.members.forEach((a) => status(a, "asked to confirm", "wait"));
          break;
        case "org_vote":
          if (ev.vote === "yes") { status(ev.agent, "confirmed", "ok"); face(ev.agent, "jumping"); }
          step(c || [...cases.values()].pop(), ev, `${name(ev.agent)} ${ev.vote === "yes" ? "confirmed" : "said no"}.`);
          break;
        case "org_done":
          Object.assign(c, { status: ev.outcome });
          step(c, ev, ev.outcome === "covered" ? `Covered: ${name(ev.taker)} takes it. Every rung below is told, so their timers stop.`
            : ev.outcome === "excused" ? `Excused by ${name(ev.by)}: staff covers it, and the student doesn't have to find anyone.`
            : `${OUTCOME[ev.outcome] || ev.outcome} by ${name(ev.by)}.`);
          holder(ev.by, false); status(ev.by, OUTCOME[ev.outcome] ? OUTCOME[ev.outcome].toLowerCase() : ev.outcome, "ok"); face(ev.by, "waving");
          if (ev.taker) { status(ev.taker, "covering it", "ok"); face(ev.taker, "waving"); }
          if (c.owner) { status(c.owner, "covered", "ok"); face(c.owner, "idle"); }
          break;
        case "org_overdue":
          Object.assign(c, { status: "overdue" });
          step(c, ev, `Past every deadline with nobody above ${name(ev.by)}. It stays open; nothing was approved by the silence.`);
          break;
        default: return;
      }
      renderCases();
      if (selected) inbox(selected, true);
    }
    // a wire event between two org agents: just the packet (the case list already tells the story)
    function wire(ev, animate) { if (animate && nodes.has(ev.from) && nodes.has(ev.to) && /Escalation|IssueReport|Question|Answer|IssueAck|CaseUpdate/.test(ev.schema)) packet(ev.from, ev.to, /Escalation|IssueReport/.test(ev.schema) ? "up" : "ask"); }

    function renderCases() {
      const el = root.querySelector("#orgCases");
      if (!cases.size) { el.innerHTML = '<p class="muted small">No cases yet. Play the morning to watch one climb.</p>'; return; }
      const title = (c) => c.kind === "uncovered_callout" ? `${name(c.owner)}'s ${c.label || c.shift_id}: same-day call-out`
        : c.kind === "safety" ? (c.id.endsWith("-ehs") ? "Safety report, Environmental Health and Safety" : "Safety report, the manager on duty")
        : c.kind === "f1_question" ? "F-1 question for ISSC" : "Report";
      el.innerHTML = [...cases.values()].reverse().map((c) => `<article class="org-case ${c.status}">
        <header><b>${esc(title(c))}</b><span class="pill ${c.status === "open" || c.status === "pending" ? "wait" : c.status === "overdue" ? "bad" : "ok"}">${esc(c.status === "open" ? "with " + name(c.holder) : c.status === "pending" ? "advisor pending" : OUTCOME[c.status] || c.status)}</span></header>
        <ol>${c.steps.map((s) => `<li><time>${clockText(s.t)}</time><span>${esc(s.text)}</span></li>`).join("")}</ol></article>`).join("");
    }
    async function inbox(id, quiet) {
      selected = id;
      nodes.forEach((n) => n.el.classList.toggle("selected", n.id === id));
      let msgs = [];
      try { msgs = (await phoneOf(id)) || []; } catch (_) { /* not in this recording */ }
      if (selected !== id) return;
      root.querySelector("#orgInboxTitle").textContent = `${name(id)}'s phone`;
      root.querySelector("#orgInboxSub").textContent = nodes.get(id) && nodes.get(id).kind === "student"
        ? "Their private chat with their own mascot (synthetic demo). Nobody else in the chart sees it."
        : "What landed on this person's phone. Reasons never arrive here; shift ids and rule names do.";
      const t = root.querySelector("#orgInbox");
      t.innerHTML = msgs.length ? msgs.map((m) => `<div class="msg${m.kind === "student" ? " me" : m.kind === "reply" ? " reply" : ""}">${esc(m.text)}${(m.buttons || []).length ? `<div class="btns">${m.buttons.map((b) => `<button type="button" disabled>${esc(b.label)}</button>`).join("")}</div>` : ""}</div>`).join("")
        : '<p class="empty">Nothing on this phone yet.</p>';
      if (!quiet) t.scrollTop = t.scrollHeight;
    }
    function reset() {
      cases.clear(); last = null; renderCases();
      nodes.forEach((n) => { status(n.id, ""); face(n.id, "idle"); holder(n.id, false); n.el.querySelector(".org-timer").hidden = true; });
      root.querySelector("#orgClock").textContent = "Sat 6:30 AM";
    }
    build(opts.data);
    return { event, wire, reset, inbox, has: (id) => nodes.has(id), setPhones(fn) { phoneOf = fn; } };
  }
  window.TagOutOrg = { create };
})();
