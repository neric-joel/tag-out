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
  // Column widths for the general layout, before it stretches to the viewport.
  const WIDTHS = { Phones: 140, Mascots: 170, Broker: 180, Steward: 160, Manager: 150 };
  const GAP = 56; // wide enough for a "private" label between neighbours
  const clampZoom = value => Math.min(3, Math.max(.1, value));
  let instances = 0;
  function create(container, opts = {}) {
    if (!container || container.nodeType !== 1) throw new TypeError('A container element is required.');
    const students = (opts.students || []).map(s => ({ id: String(s.id), name: String(s.name), pet: s.pet ? String(s.pet) : '' }));
    const showPhones = opts.phones !== false;
    const ids = new Set(['broker', 'steward', 'phone:manager']);
    students.forEach(s => {
      if (!s.id || s.id.startsWith('phone:') || ids.has(s.id) || ids.has('phone:' + s.id)) {
        throw new Error('Student ids must be unique and cannot use reserved agent ids.');
      }
      ids.add(s.id);
      ids.add('phone:' + s.id);
    });
    const order = new Map(students.map((s, i) => [s.id, i]));
    const layoutKey = String(opts.layoutKey || 'tagout.flow.layout');
    // Saved positions: node id -> [x as a fraction of the stage width, y in px].
    const saved = new Map();
    try {
      const raw = JSON.parse(localStorage.getItem(layoutKey));
      if (raw && typeof raw === 'object') Object.entries(raw).forEach(([id, p]) => {
        if (Array.isArray(p) && p.length === 2 && p.every(Number.isFinite)) saved.set(id, p);
      });
    } catch (_) { /* storage blocked or unreadable: use the automatic layout */ }
    const root = html('section', 'tof', undefined, container);
    root.setAttribute('aria-label', 'Agent message flow');
    const graphHead = html('div', 'tof-graph-head', undefined, root);
    html('h2', '', 'Agent flow', graphHead);
    const headSide = html('div', 'tof-head-side', undefined, graphHead);
    const legend = html('div', 'tof-legend', undefined, headSide);
    [['req', 'Request'], ['resp', 'Response'], ['private', 'Private owner channel']].forEach(([kind, label]) => {
      const item = html('span', '', undefined, legend);
      html('i', 'tof-key tof-' + kind, undefined, item);
      item.appendChild(document.createTextNode(label));
    });
    const tools = html('div', 'tof-tools', undefined, headSide);
    tools.setAttribute('role', 'group');
    tools.setAttribute('aria-label', 'Graph view');
    [['−', 'Zoom out', () => zoomBy(1 / 1.25)], ['+', 'Zoom in', () => zoomBy(1.25)],
      ['Fit', 'Fit the whole graph in view', () => fit()],
      ['Reset layout', 'Put every block back in its automatic place', () => resetLayout()]].forEach(([text, tip, action]) => {
      const button = html('button', 'tof-tool', text, tools);
      button.type = 'button';
      button.title = tip;
      if (text.length === 1) button.setAttribute('aria-label', tip);
      button.addEventListener('click', () => { if (!dead) action(); });
    });
    const viewport = html('div', 'tof-viewport', undefined, root);
    const stage = html('div', 'tof-stage', undefined, viewport);
    stage.setAttribute('role', 'group');
    stage.setAttribute('aria-label', (showPhones ? 'Phones connect privately to mascots. ' : '') + 'Mascots connect to the broker, then the steward and manager.');
    const hint = html('p', 'tof-sr', 'Drag to move this block, or use the arrow keys. Hold Shift to move it further.', root);
    hint.id = 'tof-hint-' + (++instances);
    const wires = svg('svg', { class: 'tof-wires', 'aria-hidden': 'true' }, stage);
    const packetLayer = svg('svg', { class: 'tof-packets', 'aria-label': 'Messages in flight' }, stage);
    const nodes = new Map(), edges = [], packets = [], effects = new Map(), columns = new Map();
    function column(title) {
      if (!columns.has(title)) {
        const el = html('div', 'tof-column', title, stage);
        el.title = title;
        columns.set(title, { title, el, nodes: [], x: 0, w: 0 });
      }
      return columns.get(title);
    }
    ['Phones', 'Mascots', 'Broker', 'Steward', 'Manager'].forEach(column);
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
    // stage size, viewport height, row pitch, and the pan/zoom transform
    let extras = 0, stageW = 0, stageH = 0, viewH = 0, lastWidth = 0, rowH = 76;
    let zoom = 1, panX = 0, panY = 0, fitted = true;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');

    function addNode(id, title, subtitle, kind, heading, pet, hidden) {
      const el = html('article', 'tof-node tof-node-' + kind, undefined, stage);
      el.dataset.nodeId = id;
      el.tabIndex = 0;
      el.setAttribute('aria-label', subtitle ? title + ', ' + subtitle : title);
      el.setAttribute('aria-describedby', hint.id);
      el.hidden = !!hidden;
      html('span', 'tof-port tof-port-in', undefined, el).setAttribute('aria-hidden', 'true');
      html('span', 'tof-port tof-port-out', undefined, el).setAttribute('aria-hidden', 'true');
      if (pet && window.Sprites) {
        el.classList.add('tof-has-pet');
        const canvas = html('canvas', 'tof-pet', undefined, el);
        canvas.setAttribute('aria-hidden', 'true');
        window.Sprites.badge(canvas, pet, 'idle');
      }
      const name = html('h3', 'tof-node-title', title, el);
      name.title = title;
      const sub = html('p', 'tof-node-sub', subtitle, el);
      sub.title = subtitle;
      const footer = html('div', 'tof-node-footer', undefined, el);
      const status = html('span', 'tof-node-status', 'Ready', footer);
      const badge = kind === 'mascot' ? html('span', 'tof-rule', 'Rulebook', footer) : null;
      const n = { id, el, title, status, badge, kind, hidden: !!hidden, x: 0, y: 0, w: 0, h: 64 };
      column(heading).nodes.push(n);
      nodes.set(id, n);
      return n;
    }
    students.forEach(s => {
      addNode('phone:' + s.id, s.name + "'s phone", 'Telegram / Cubbie', 'phone', 'Phones', '', !showPhones);
      addNode(s.id, s.name + "'s mascot", 'own process + database', 'mascot', 'Mascots', s.pet);
    });
    const broker = addNode('broker', 'Broker', 'sees shift ids, picks, yes/no', 'broker', 'Broker');
    broker.el.querySelector('.tof-port-in').hidden = students.length > 0;
    const brokerInputs = students.map(() => html('span', 'tof-port tof-port-in', undefined, broker.el));
    brokerInputs.forEach(port => port.setAttribute('aria-hidden', 'true'));
    addNode('steward', 'Library Steward', 'roster + manager approval', 'steward', 'Steward');
    addNode('phone:manager', "Manager's phone", opts.manager || 'Library manager', 'phone', 'Manager');
    function addSpec(spec) {
      const id = spec && spec.id != null ? String(spec.id) : '';
      if (!id || nodes.has(id)) throw new Error('Node ids must be unique and non-empty.');
      extras++;
      return addNode(id, String(spec.title || id), spec.subtitle ? String(spec.subtitle) : '',
        String(spec.kind || 'role').replace(/[^\w-]/g, '-'), String(spec.column || 'Other'), spec.pet ? String(spec.pet) : '');
    }

    function connect(a, b, privateEdge, side) {
      const known = edges.find(e => (e.a === a && e.b === b) || (e.a === b && e.b === a));
      if (known) return known;
      const path = svg('path', { class: 'tof-edge' + (privateEdge ? ' tof-edge-private' : '') + (side ? ' tof-edge-side' : '') }, wires);
      let label;
      if (privateEdge) {
        label = svg('g', { class: 'tof-edge-label' }, wires);
        svg('rect', { x: -26, y: -9, width: 53, height: 18, rx: 6 }, label);
        svg('path', { d: 'M-21 -1 v-3 a3 3 0 0 1 6 0 v3 M-22 -1 h8 v7 h-8 Z', class: 'tof-lock' }, label);
        svg('text', { x: -10, y: 4 }, label).textContent = 'private';
      }
      const edge = { a, b, path, label, curve: null, privateEdge, hidden: nodes.get(a).hidden || nodes.get(b).hidden };
      if (edge.hidden) [path, label].forEach(el => el && el.setAttribute('display', 'none'));
      edges.push(edge);
      return edge;
    }
    function connectSpec(a, b, o) {
      a = String(a); b = String(b);
      if (!nodes.has(a) || !nodes.has(b) || a === b) throw new Error('Edges must join two different known node ids.');
      return connect(a, b, !!(o && o.private), !!(o && o.side));
    }
    students.forEach(s => { connect('phone:' + s.id, s.id, true); connect(s.id, 'broker', false); });
    connect('broker', 'steward', false);
    // the Steward also asks mascots directly: busy bits for meetings, meeting invites, issue replies
    students.forEach(s => connect(s.id, 'steward', false, true));
    connect('steward', 'phone:manager', true);
    (opts.nodes || []).forEach(addSpec);
    (opts.edges || []).forEach(e => connectSpec(e.a, e.b, e));
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
    function route(e) {
      const a = nodes.get(e.a), b = nodes.get(e.b);
      // Leave from the sides that face each other, so a block dragged past its neighbour still wires cleanly.
      const forward = b.x + b.w / 2 >= a.x + a.w / 2;
      const x1 = forward ? a.x + a.w : a.x, x2 = forward ? b.x : b.x + b.w;
      const y1 = a.y + a.h / 2;
      const index = forward && e.b === 'broker' && order.has(e.a) ? order.get(e.a) : -1;
      const y2 = index >= 0 ? b.y + 30 + (index + .5) * (b.h - 60) / students.length : b.y + b.h / 2;
      const bend = Math.max(20, Math.abs(x2 - x1) * .5) * (forward ? 1 : -1);
      e.curve = [x1, y1, x1 + bend, y1, x2 - bend, y2, x2, y2];
      e.path.setAttribute('d', 'M' + x1 + ',' + y1 + ' C' + (x1+bend) + ',' + y1 + ' ' + (x2-bend) + ',' + y2 + ' ' + x2 + ',' + y2);
      if (e.label) {
        const p = point(e.curve, .5);
        const offset = e.a === 'phone:' + e.b && order.has(e.b) ? rowH / 2 + 5 : 13;
        e.label.setAttribute('transform', 'translate(' + p.x + ' ' + (p.y - offset) + ')');
      }
    }
    function place(n, x, y, width, height) {
      const s = saved.get(n.id);
      if (s) { x = s[0] * stageW; y = s[1]; }
      Object.assign(n, { x, y, w: width, h: height });
      Object.assign(n.el.style, { left: x + 'px', top: y + 'px', width: width + 'px', height: height + 'px' });
    }
    function layout() {
      if (dead) return;
      const available = viewport.clientWidth;
      if (!available) return;
      // The original five-column layout, kept exactly while nothing was added to it.
      const legacy = showPhones && !extras;
      const compact = students.length > 8;
      rowH = compact ? 60 : 76;
      const rowNode = compact ? 52 : 64;
      stage.classList.toggle('tof-compact', compact);
      const all = [...columns.values()];
      const shown = legacy ? all : all.filter(c => c.nodes.some(n => !n.hidden));
      all.forEach(c => { c.el.hidden = !shown.includes(c); });
      let base, w, h;
      if (legacy) {
        base = 720;
        w = Math.max(base, available);
        h = Math.max(70 + students.length * 76, 360);  // as tall as its rows need, so it fits on one screen
        const xs = [12, w * .214, w * .452, w * .715, w - Math.max(124, w * .15) - 12];
        const ws = [w * .15, w * .19, w * .237, w * .212, Math.max(124, w * .15)];
        shown.forEach((c, i) => { c.x = xs[i]; c.w = ws[i]; });
      } else {
        const design = shown.map(c => WIDTHS[c.title] || 150);
        base = 24 + design.reduce((sum, v) => sum + v, 0) + GAP * (shown.length - 1);
        w = Math.max(base, available);
        const stretch = w / base;
        let x = 12;
        shown.forEach((c, i) => { c.x = x * stretch; c.w = design[i] * stretch; x += design[i] + GAP; });
        h = Math.max(w * 7 / 16, 360, ...shown.map(c => {
          const visible = c.nodes.filter(n => !n.hidden).length;
          return c.title === 'Phones' || c.title === 'Mascots' ? 70 + visible * rowH : 84 + visible * 80;
        }));
      }
      const fitScale = Math.min(1, available / base);
      stageW = w; stageH = h; viewH = h * fitScale;
      // no taller than the window has room for under the page's header, so the whole graph is on one screen
      const z = parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
      let top = 0;
      for (let el = viewport; el; el = el.offsetParent) top += el.offsetTop;
      const room = innerHeight / z - top - 24;
      if (room > 260) viewH = Math.min(viewH, room);
      stage.style.width = w + 'px'; stage.style.height = h + 'px';
      viewport.style.height = viewH + 'px';
      [wires, packetLayer].forEach(el => { el.setAttribute('width', w); el.setAttribute('height', h); });
      shown.forEach(c => { c.el.style.left = c.x + 'px'; c.el.style.width = c.w + 'px'; });
      if (legacy) {
        const [phones, mascots, , steward, manager] = shown;
        students.forEach((s, i) => {
          place(nodes.get('phone:' + s.id), phones.x, 52 + i * 76, phones.w, 64);
          place(nodes.get(s.id), mascots.x, 52 + i * 76, mascots.w, 64);
        });
        place(broker, shown[2].x, 52, shown[2].w, h - 84);
        place(nodes.get('steward'), steward.x, 100, steward.w, 64);
        place(nodes.get('phone:manager'), manager.x, h - 96, manager.w, 64);
      } else {
        shown.forEach(c => {
          const visible = c.nodes.filter(n => !n.hidden);
          if (c.title === 'Phones' || c.title === 'Mascots') {
            visible.forEach((n, i) => place(n, c.x, 52 + i * rowH, c.w, rowNode));
          } else if (c.title === 'Broker') {
            // the broker spans the column; anything else added here stacks below it
            const tall = h - 84 - (visible.length - 1) * 80;
            visible.forEach((n, i) => place(n, c.x, i ? 52 + tall + 16 + (i - 1) * 80 : 52, c.w, i ? 64 : tall));
          } else if (visible.length === 1 && (c.title === 'Steward' || c.title === 'Manager')) {
            // alone in their columns, the steward sits high and the manager low, as in the original layout
            place(visible[0], c.x, c.title === 'Steward' ? 100 : h - 96, c.w, 64);
          } else {
            const slot = (h - 84) / visible.length;
            visible.forEach((n, i) => place(n, c.x, 52 + (i + .5) * slot - 32, c.w, 64));
          }
        });
      }
      brokerInputs.forEach((port, i) => {
        port.style.top = (30 + (i + .5) * (broker.h - 60) / students.length) + 'px';
      });
      edges.forEach(e => { if (!e.hidden) route(e); });
      packets.forEach(position);
      if (fitted || available !== lastWidth) fit(); else apply();
      lastWidth = available;
    }
    function apply() {
      stage.style.transform = 'translate(' + panX + 'px, ' + panY + 'px) scale(' + zoom + ')';
    }
    function fit() {
      fitted = true;
      const vw = viewport.clientWidth;
      if (!vw || !stageW) return;
      let x0 = 0, y0 = 0, x1 = stageW, y1 = stageH;
      nodes.forEach(n => {
        if (n.hidden) return;
        x0 = Math.min(x0, n.x - 12); y0 = Math.min(y0, n.y - 12);
        x1 = Math.max(x1, n.x + n.w + 12); y1 = Math.max(y1, n.y + n.h + 12);
      });
      zoom = Math.min(1, vw / (x1 - x0), viewH / (y1 - y0));
      panX = (vw - (x1 - x0) * zoom) / 2 - x0 * zoom;
      panY = (viewH - (y1 - y0) * zoom) / 2 - y0 * zoom;
      apply();
    }
    function zoomAt(next, x, y) {
      next = clampZoom(next);
      panX = x - (x - panX) * next / zoom;
      panY = y - (y - panY) * next / zoom;
      zoom = next; fitted = false;
      apply();
    }
    function zoomBy(factor) { zoomAt(zoom * factor, viewport.clientWidth / 2, viewH / 2); }
    function save() {
      try { localStorage.setItem(layoutKey, JSON.stringify(Object.fromEntries(saved))); } catch (_) { /* storage unavailable: positions last for this page only */ }
    }
    function resetLayout() {
      saved.clear();
      try { localStorage.removeItem(layoutKey); } catch (_) { /* storage unavailable */ }
      fitted = true;
      layout();
    }
    function moveNode(n, x, y) {
      saved.set(n.id, [x / stageW, y]);
      Object.assign(n, { x, y });
      n.el.style.left = x + 'px'; n.el.style.top = y + 'px';
      edges.forEach(e => { if (!e.hidden && (e.a === n.id || e.b === n.id)) route(e); });
      packets.forEach(position);
    }

    // Pointer input: drag a block, drag empty canvas to pan, two fingers to pinch.
    const pointers = new Map();
    let drag = null, pinch = null, swallow = false;
    function swallowClick() { swallow = true; setTimeout(() => { swallow = false; }); }
    function pointerDown(e) {
      if (dead || (e.pointerType === 'mouse' && e.button !== 0) || e.target.closest('.tof-packet')) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) startPinch();
      if (pointers.size > 1) return;
      const el = e.target.closest('.tof-node');
      const n = el ? nodes.get(el.dataset.nodeId) : null;
      drag = { id: e.pointerId, node: n, x: e.clientX, y: e.clientY, ox: n ? n.x : panX, oy: n ? n.y : panY, moved: false };
    }
    function pointerMove(e) {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pinch) return pinchMove();
      if (!drag || drag.id !== e.pointerId) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved) {
        if (Math.hypot(dx, dy) < 4) return; // a plain click, not a drag
        drag.moved = true;
        // Capture only once moving, so a click on a block still lands on the block.
        try { viewport.setPointerCapture(e.pointerId); } catch (_) { /* pointer already released */ }
        if (drag.node) drag.node.el.classList.add('tof-dragging'); else viewport.classList.add('tof-panning');
      }
      if (drag.node) moveNode(drag.node, drag.ox + dx / zoom, drag.oy + dy / zoom);
      else { panX = drag.ox + dx; panY = drag.oy + dy; fitted = false; apply(); }
    }
    function pointerUp(e) {
      if (!pointers.delete(e.pointerId)) return;
      if (pinch) {
        if (pointers.size < 2) { pinch = null; swallowClick(); }
      } else if (drag && drag.id === e.pointerId) endDrag();
    }
    function endDrag() {
      if (drag.moved) {
        swallowClick();
        if (drag.node) { drag.node.el.classList.remove('tof-dragging'); save(); } else viewport.classList.remove('tof-panning');
      }
      drag = null;
    }
    function startPinch() {
      if (drag) endDrag();
      const [p, q] = [...pointers.values()];
      const box = viewport.getBoundingClientRect();
      pinch = { left: box.left + viewport.clientLeft, top: box.top + viewport.clientTop,
        distance: Math.hypot(p.x - q.x, p.y - q.y) || 1, x: (p.x + q.x) / 2, y: (p.y + q.y) / 2, zoom, panX, panY };
    }
    function pinchMove() {
      const [p, q] = [...pointers.values()];
      // keep the stage point that started under the fingers under them
      const sx = (pinch.x - pinch.left - pinch.panX) / pinch.zoom, sy = (pinch.y - pinch.top - pinch.panY) / pinch.zoom;
      zoom = clampZoom(pinch.zoom * Math.hypot(p.x - q.x, p.y - q.y) / pinch.distance);
      panX = (p.x + q.x) / 2 - pinch.left - sx * zoom;
      panY = (p.y + q.y) / 2 - pinch.top - sy * zoom;
      fitted = false;
      apply();
    }
    viewport.addEventListener('pointerdown', pointerDown);
    window.addEventListener('pointermove', pointerMove);
    window.addEventListener('pointerup', pointerUp);
    window.addEventListener('pointercancel', pointerUp);
    root.addEventListener('click', e => {
      if (swallow && viewport.contains(e.target)) { e.preventDefault(); e.stopPropagation(); }
    }, true);
    viewport.addEventListener('wheel', e => {
      if (dead || (!e.ctrlKey && !e.metaKey)) return; // a plain wheel scrolls the page
      e.preventDefault();
      const box = viewport.getBoundingClientRect();
      zoomAt(zoom * Math.exp(-e.deltaY * (e.deltaMode ? 16 : 1) * .002),
        e.clientX - box.left - viewport.clientLeft, e.clientY - box.top - viewport.clientTop);
    }, { passive: false });
    // The viewport clips but can still be scrolled (focus, find in page); turn any scroll into a pan.
    viewport.addEventListener('scroll', () => {
      if (!viewport.scrollLeft && !viewport.scrollTop) return;
      panX -= viewport.scrollLeft; panY -= viewport.scrollTop;
      viewport.scrollLeft = viewport.scrollTop = 0;
      fitted = false;
      apply();
    });
    // Keyboard focus on a block or packet outside the view pans it into the middle.
    stage.addEventListener('focusin', e => {
      if (!e.target.matches(':focus-visible')) return;
      const box = e.target.getBoundingClientRect(), view = viewport.getBoundingClientRect();
      const left = view.left + viewport.clientLeft, top = view.top + viewport.clientTop;
      if (box.left >= left && box.top >= top && box.right <= left + viewport.clientWidth && box.bottom <= top + viewH) return;
      panX += left + viewport.clientWidth / 2 - (box.left + box.right) / 2;
      panY += top + viewH / 2 - (box.top + box.bottom) / 2;
      fitted = false;
      apply();
    });
    stage.addEventListener('keydown', e => {
      const n = e.target.classList.contains('tof-node') ? nodes.get(e.target.dataset.nodeId) : null;
      const step = e.shiftKey ? 64 : 16;
      const d = n && !e.altKey && !e.ctrlKey && !e.metaKey && { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
      if (!d || dead) return;
      e.preventDefault();
      moveNode(n, n.x + d[0], n.y + d[1]);
      save();
    });

    function name(id) { return nodes.get(id)?.title || String(id); }
    function select(record) {
      selected?.row.setAttribute('aria-pressed', 'false');
      selected = record;
      record.row.setAttribute('aria-pressed', 'true');
      const m = record.message;
      detailHead.textContent = m.schema + ' · ' + name(m.from) + ' → ' + name(m.to);
      meaning.textContent = explain(m.schema);
      meta.textContent = [m.id != null ? 'ID: ' + m.id : '', m.path ? 'Path: ' + m.path : '', record.time].filter(Boolean).join(' · ');
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
    function message(input, quiet) {
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
      if (quiet || edge.hidden) return; // history, or a hidden phone: listed for inspection, not animated
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
      addNode(spec) { if (dead) return; addSpec(spec); layout(); },
      connect(a, b, o) {
        if (dead) return;
        const edge = connectSpec(a, b, o);
        if (stageW && !edge.hidden) route(edge);
      },
      resetLayout() { if (!dead) resetLayout(); },
      fit() { if (!dead) fit(); },
      explain,
      destroy() {
        if (dead) return;
        clear(); dead = true; observer.disconnect();
        window.removeEventListener('pointermove', pointerMove);
        window.removeEventListener('pointerup', pointerUp);
        window.removeEventListener('pointercancel', pointerUp);
        motion.removeEventListener('change', motionChanged); root.remove();
      }
    };
  }
  window.TagOutFlow = { create, explain };
}());
