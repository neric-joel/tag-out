/* Tag Out flow viewer. Original code; free to use, modify, and share. */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const explanations = {
    PickRequest: "The broker offers the round's open shifts. The mascot answers with one shift id or a pass.",
    Pick: 'One shift id, or null for a pass. A pass looks the same whatever the reason.',
    RingCheck: 'The broker asks: is this exact ring OK for your student? The mascot checks its private rules.',
    Eligibility: 'One yes/no bit. No reason, no hours.',
    Prepare: 'Two-phase commit, phase 1: hold the trade and ask your student to confirm.',
    Vote: 'yes, no, stale (the week changed) or timeout.',
    Decision: 'Phase 2: commit or abort, the same for everyone.',
    TradeRequest: 'A mascot asks to trade a shift. Only the shift id leaves it.',
    SundayCheck: "Check next week against your student's calendar. The reply is empty on purpose.",
    OpenShift: 'No safe trade: the manager sees the shift as open, with no reason.',
    CallOut: 'A same-day call-out: the manager hears at once, with no reason.',
    ShiftRef: 'Roster facts the employer already shares.',
    NoTrade: "Tells the owner's mascot that no trade worked.",
    OwnerNotice: 'Your mascot explains a schedule conflict in your private owner channel.',
    ConfirmTrade: 'Your mascot asks you to confirm the proposed trade privately.',
    OwnerReply: 'Your answer returns to your own mascot in the private owner channel.',
    ManagerApproval: 'The steward asks the manager to approve the proposed roster changes.'
  };
  function explain(schema) {
    return explanations[schema] || 'A message exchanged between these two participants. Inspect its contents below.';
  }
  function html(tag, cls, text, parent) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    if (parent) parent.appendChild(el);
    return el;
  }
  function svg(tag, attrs, parent) {
    const el = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([key, value]) => el.setAttribute(key, value));
    if (parent) parent.appendChild(el);
    return el;
  }
  function create(container, opts = {}) {
    if (!container || container.nodeType !== 1) throw new TypeError('A container element is required.');
    const students = (opts.students || []).map(s => ({ id: String(s.id), name: String(s.name) }));
    const ids = new Set(['broker', 'steward', 'phone:manager']);
    students.forEach(s => {
      if (!s.id || s.id.startsWith('phone:') || ids.has(s.id) || ids.has('phone:' + s.id)) {
        throw new Error('Student ids must be unique and cannot use reserved agent ids.');
      }
      ids.add(s.id);
      ids.add('phone:' + s.id);
    });
    const root = html('section', 'tof', undefined, container);
    root.setAttribute('aria-label', 'Agent message flow');
    const graphHead = html('div', 'tof-graph-head', undefined, root);
    html('h2', '', 'Agent flow', graphHead);
    const legend = html('div', 'tof-legend', undefined, graphHead);
    [['req', 'Request'], ['resp', 'Response'], ['private', 'Private owner channel']].forEach(([kind, label]) => {
      const item = html('span', '', undefined, legend);
      html('i', 'tof-key tof-' + kind, undefined, item);
      item.appendChild(document.createTextNode(label));
    });
    const viewport = html('div', 'tof-viewport', undefined, root);
    const stage = html('div', 'tof-stage', undefined, viewport);
    stage.setAttribute('role', 'group');
    stage.setAttribute('aria-label', 'Phones connect privately to mascots. Mascots connect to the broker, then the steward and manager.');
    const wires = svg('svg', { class: 'tof-wires', 'aria-hidden': 'true' }, stage);
    const packetLayer = svg('svg', { class: 'tof-packets', 'aria-label': 'Messages in flight' }, stage);
    const nodes = new Map(), edges = [], packets = [], effects = new Map();
    const headings = ['Phones', 'Mascots', 'Broker', 'Steward', 'Manager'].map(t => html('div', 'tof-column', t, stage));
    const lower = html('div', 'tof-inspector', undefined, root);
    const log = html('section', 'tof-log', undefined, lower);
    const logHead = html('div', 'tof-pane-head', undefined, log);
    html('h3', '', 'Messages', logHead);
    const count = html('span', 'tof-count', '0 retained', logHead);
    const list = html('div', 'tof-list', undefined, log);
    list.setAttribute('role', 'group');
    list.setAttribute('aria-label', 'Message history, newest first');
    const empty = html('p', 'tof-empty', 'Messages will appear here. Select one to inspect what crossed.', list);
    const details = html('section', 'tof-details', undefined, lower);
    details.setAttribute('aria-label', 'Selected message');
    const detailHead = html('h3', '', 'Inspect a message', details);
    const meaning = html('p', 'tof-meaning', 'Select a packet or a message below the graph.', details);
    const meta = html('p', 'tof-meta', '', details);
    const ownerNote = html('p', 'tof-owner-note', 'Owner channel: only this student sees it.', details);
    ownerNote.hidden = true;
    const content = html('pre', 'tof-json', '', details);
    content.tabIndex = 0;
    content.setAttribute('aria-label', 'Message payload');
    const ownerText = html('p', 'tof-owner-text', '', details);
    ownerText.hidden = true;
    let records = [], selected = null, speed = 1, paused = false, dead = false, frame = 0, previous = 0;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');

    function addNode(id, title, subtitle, kind) {
      const el = html('article', 'tof-node tof-node-' + kind, undefined, stage);
      el.dataset.nodeId = id;
      html('span', 'tof-port tof-port-in', undefined, el).setAttribute('aria-hidden', 'true');
      html('span', 'tof-port tof-port-out', undefined, el).setAttribute('aria-hidden', 'true');
      const name = html('h3', 'tof-node-title', title, el);
      name.title = title;
      const sub = html('p', 'tof-node-sub', subtitle, el);
      sub.title = subtitle;
      const footer = html('div', 'tof-node-footer', undefined, el);
      const status = html('span', 'tof-node-status', 'Ready', footer);
      const badge = kind === 'mascot' ? html('span', 'tof-rule', 'Rulebook', footer) : null;
      nodes.set(id, { el, title, status, badge, kind, x: 0, y: 0, w: 0, h: 64 });
    }
    students.forEach(s => {
      addNode('phone:' + s.id, s.name + "'s phone", 'Telegram / Cubbie', 'phone');
      addNode(s.id, s.name + "'s mascot", 'own process + database', 'mascot');
    });
    addNode('broker', 'Broker', 'sees shift ids, picks, yes/no', 'broker');
    nodes.get('broker').el.querySelector('.tof-port-in').hidden = students.length > 0;
    const brokerInputs = students.map(() => html('span', 'tof-port tof-port-in', undefined, nodes.get('broker').el));
    brokerInputs.forEach(port => port.setAttribute('aria-hidden', 'true'));
    addNode('steward', 'Library Steward', 'roster + manager approval', 'steward');
    addNode('phone:manager', "Manager's phone", opts.manager || 'Library manager', 'phone');

    function connect(a, b, privateEdge) {
      const path = svg('path', { class: 'tof-edge' + (privateEdge ? ' tof-edge-private' : '') }, wires);
      let label;
      if (privateEdge) {
        label = svg('g', { class: 'tof-edge-label' }, wires);
        svg('rect', { x: -26, y: -9, width: 53, height: 18, rx: 6 }, label);
        svg('path', { d: 'M-21 -1 v-3 a3 3 0 0 1 6 0 v3 M-22 -1 h8 v7 h-8 Z', class: 'tof-lock' }, label);
        svg('text', { x: -10, y: 4 }, label).textContent = 'private';
      }
      edges.push({ a, b, path, label, curve: null, privateEdge });
    }
    students.forEach(s => { connect('phone:' + s.id, s.id, true); connect(s.id, 'broker', false); });
    connect('broker', 'steward', false);
    connect('steward', 'phone:manager', true);
    function point(c, t) {
      const u = 1 - t;
      return { x: u*u*u*c[0] + 3*u*u*t*c[2] + 3*u*t*t*c[4] + t*t*t*c[6],
        y: u*u*u*c[1] + 3*u*u*t*c[3] + 3*u*t*t*c[5] + t*t*t*c[7] };
    }
    function position(packet) {
      const t = packet.progress, eased = t*t*(3 - 2*t);
      const p = point(packet.edge.curve, packet.reverse ? 1 - eased : eased);
      packet.el.setAttribute('transform', 'translate(' + p.x + ' ' + p.y + ')');
    }
    function layout() {
      if (dead) return;
      const available = viewport.clientWidth;
      if (!available) return;
      const w = Math.max(720, available), h = Math.max(w * 7 / 16, 70 + students.length * 76, 360);
      const scale = Math.min(1, available / 720);
      stage.style.width = w + 'px'; stage.style.height = h + 'px';
      stage.style.transform = 'scale(' + scale + ')';
      viewport.style.height = h * scale + 'px';
      [wires, packetLayer].forEach(el => { el.setAttribute('width', w); el.setAttribute('height', h); });
      const xs = [12, w * .214, w * .452, w * .715, w - Math.max(124, w * .15) - 12];
      headings.forEach((el, i) => { el.style.left = xs[i] + 'px'; });
      function place(id, x, y, width, height = 64) {
        const n = nodes.get(id);
        Object.assign(n, { x, y, w: width, h: height });
        Object.assign(n.el.style, { left: x + 'px', top: y + 'px', width: width + 'px', height: height + 'px' });
      }
      students.forEach((s, i) => {
        place('phone:' + s.id, xs[0], 52 + i * 76, w * .15);
        place(s.id, xs[1], 52 + i * 76, w * .19);
      });
      place('broker', xs[2], 52, w * .237, h - 84);
      brokerInputs.forEach((port, i) => {
        port.style.top = (30 + (i + .5) * (nodes.get('broker').h - 60) / students.length) + 'px';
      });
      place('steward', xs[3], 100, w * .212);
      place('phone:manager', xs[4], h - 96, Math.max(124, w * .15));
      edges.forEach(e => {
        const a = nodes.get(e.a), b = nodes.get(e.b);
        const x1 = a.x + a.w, x2 = b.x;
        const y1 = a.y + a.h / 2;
        const index = students.findIndex(s => s.id === e.a);
        const y2 = e.b === 'broker' ? b.y + 30 + (index + .5) * (b.h - 60) / Math.max(1, students.length) : b.y + b.h / 2;
        const bend = Math.max(20, Math.abs(x2 - x1) * .5);
        e.curve = [x1, y1, x1 + bend, y1, x2 - bend, y2, x2, y2];
        e.path.setAttribute('d', 'M' + x1 + ',' + y1 + ' C' + (x1+bend) + ',' + y1 + ' ' + (x2-bend) + ',' + y2 + ' ' + x2 + ',' + y2);
        if (e.label) {
          const p = point(e.curve, .5);
          const offset = e.a.startsWith('phone:') ? 43 : 13;
          e.label.setAttribute('transform', 'translate(' + p.x + ' ' + (p.y - offset) + ')');
        }
      });
      packets.forEach(position);
    }
    function name(id) { return nodes.get(id)?.title || String(id); }
    function select(record) {
      selected?.row.setAttribute('aria-pressed', 'false');
      selected = record;
      record.row.setAttribute('aria-pressed', 'true');
      const m = record.message;
      detailHead.textContent = m.schema + ' · ' + name(m.from) + ' → ' + name(m.to);
      meaning.textContent = explain(m.schema);
      meta.textContent = 'ID: ' + m.id + (m.path ? ' · Path: ' + m.path : '') + ' · ' + record.time;
      ownerNote.hidden = ownerText.hidden = !m.private;
      content.hidden = !!m.private;
      content.textContent = m.private ? '' : JSON.stringify(m.payload, null, 2);
      ownerText.textContent = m.private ? (m.text || 'No owner-channel text supplied.') : '';
      if (typeof opts.onSelect === 'function') opts.onSelect(m);
    }
    function summary(m) {
      if (m.private) return m.text || 'Private owner message';
      const p = m.payload;
      if (!p || typeof p !== 'object') return JSON.stringify(p) ?? 'No payload';
      const key = ['shift_id', 'ok', 'vote', 'outcome', 'items', 'moves', 'round_id', 'txn_id', 'ring_id'].find(k => k in p);
      if (!key) return JSON.stringify(p);
      return key + ': ' + (Array.isArray(p[key]) ? p[key].length + ' ' + key : JSON.stringify(p[key]));
    }
    function schedule() {
      if (!dead && !paused && !frame && (packets.length || effects.size)) frame = requestAnimationFrame(tick);
    }
    function flash(el, cls, duration, color) {
      if (color) el.style.setProperty('--tof-signal', color);
      el.classList.add(cls);
      effects.set(el, { cls, remaining: duration });
      schedule();
    }
    function tick(now) {
      frame = 0;
      const delta = previous ? Math.max(0, now - previous) * speed : 0;
      previous = now;
      effects.forEach((effect, el) => {
        effect.remaining -= delta;
        if (effect.remaining <= 0) { el.classList.remove(effect.cls); effects.delete(el); }
      });
      const acceleration = Math.max(1, packets.length / 24);
      for (let i = packets.length - 1; i >= 0; i--) {
        const p = packets[i];
        p.progress = Math.min(1, p.progress + delta * acceleration / 700);
        position(p);
        if (p.progress === 1) {
          p.el.remove(); packets.splice(i, 1);
          flash(nodes.get(p.to).el, 'tof-receiving', 420, p.color);
        }
      }
      if (packets.length || effects.size) schedule(); else previous = 0;
    }
    function message(input) {
      if (dead) return;
      if (!input || !nodes.has(input.from) || !nodes.has(input.to)) throw new Error('Message endpoints must be known node ids.');
      const edge = edges.find(e => (e.a === input.from && e.b === input.to) || (e.b === input.from && e.a === input.to));
      if (!edge) throw new Error('No direct channel connects ' + input.from + ' and ' + input.to + '.');
      // Snapshot wire contents so callers cannot change an already-inspected message.
      const m = JSON.parse(JSON.stringify(input));
      if (m.payload === undefined) m.payload = null;
      const date = m.ts === undefined ? new Date() : new Date(m.ts);
      const time = Number.isNaN(date.getTime()) ? String(m.ts) : date.toLocaleTimeString([], { hour12: false });
      const row = html('button', 'tof-row', undefined);
      row.type = 'button'; row.setAttribute('aria-pressed', 'false');
      row.dataset.direction = m.private ? 'private' : m.dir;
      html('time', 'tof-time', time, row);
      html('span', 'tof-route', name(m.from) + ' → ' + name(m.to), row);
      html('span', 'tof-schema', m.schema, row);
      html('span', 'tof-summary', summary(m), row);
      const record = { message: m, row, time };
      row.addEventListener('click', () => select(record));
      empty.hidden = true;
      list.prepend(row); records.unshift(record);
      if (records.length > 400) records.pop().row.remove();
      count.textContent = records.length + ' retained';
      const color = m.private ? 'var(--positive)' : m.dir === 'resp' ? 'var(--muted)' : 'var(--hue)';
      if (motion.matches) {
        flash(edge.path, 'tof-edge-flash', 500, color);
        flash(nodes.get(m.to).el, 'tof-receiving', 420, color);
      } else {
        const group = svg('g', { class: 'tof-packet', role: 'button', tabindex: 0, 'aria-label': m.schema + ': ' + name(m.from) + ' to ' + name(m.to) }, packetLayer);
        group.style.setProperty('--tof-signal', color);
        svg('rect', { x: -5, y: -4, width: 10, height: 8, rx: 4 }, group);
        // Keep the schema beside its packet and legible as it crosses a wire.
        svg('text', { x: 9, y: 4 }, group).textContent = m.schema;
        group.addEventListener('click', () => select(record));
        group.addEventListener('keydown', e => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(record); }
        });
        const p = { el: group, edge, reverse: edge.a !== m.from, progress: 0, to: m.to, color };
        packets.push(p);
        if (edge.curve) position(p);
        schedule();
      }
    }
    function clear() {
      cancelAnimationFrame(frame); frame = 0; previous = 0;
      packets.splice(0).forEach(p => p.el.remove());
      effects.forEach((e, el) => el.classList.remove(e.cls)); effects.clear();
      records.forEach(r => r.row.remove()); records = []; selected = null;
      empty.hidden = false; count.textContent = '0 retained';
      detailHead.textContent = 'Inspect a message';
      meaning.textContent = 'Select a packet or a message below the graph.';
      meta.textContent = content.textContent = ownerText.textContent = '';
      ownerNote.hidden = ownerText.hidden = true; content.hidden = false;
      nodes.forEach(n => { n.status.textContent = 'Ready'; n.status.title = ''; n.status.dataset.tone = ''; });
    }
    function motionChanged() {
      if (!motion.matches) return;
      packets.splice(0).forEach(p => {
        p.el.remove(); flash(p.edge.path, 'tof-edge-flash', 500, p.color);
        flash(nodes.get(p.to).el, 'tof-receiving', 420, p.color);
      });
    }
    motion.addEventListener('change', motionChanged);
    const observer = new ResizeObserver(layout);
    observer.observe(viewport);
    layout();
    return {
      message,
      state(id, text, tone = '') {
        if (dead) return;
        const n = nodes.get(id);
        if (!n) return;
        n.status.textContent = text; n.status.title = text;
        n.status.dataset.tone = ['ok', 'bad', 'wait'].includes(tone) ? tone : '';
      },
      rule(id) { const badge = nodes.get(id)?.badge; if (!dead && badge) flash(badge, 'tof-rule-check', 650); },
      clear() { if (!dead) clear(); },
      pause(value) {
        if (dead) return;
        paused = !!value;
        cancelAnimationFrame(frame); frame = 0; previous = 0; schedule();
      },
      setSpeed(value) {
        if (!Number.isFinite(value) || value <= 0) throw new RangeError('Speed must be a positive finite number.');
        speed = value;
      },
      explain,
      destroy() {
        if (dead) return;
        clear(); dead = true; observer.disconnect();
        motion.removeEventListener('change', motionChanged); root.remove();
      }
    };
  }
  window.TagOutFlow = { create, explain };
}());
