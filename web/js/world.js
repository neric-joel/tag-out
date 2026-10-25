/* Tag Out pet world. Codex Pets sprite layout (192 x 208 cells, eight columns) follows the MIT-licensed
   codex-pet-share code; the pet art itself has no reuse licence and is downloaded at setup, not shipped. */
(function () {
  "use strict";
  const STATES = {
    idle: [0, 6, 6, true], "running-right": [1, 8, 12, true],
    "running-left": [2, 8, 12, true], waving: [3, 4, 5, false],
    jumping: [4, 5, 14, false], failed: [5, 8, 6, false],
    waiting: [6, 6, 4, true], running: [7, 6, 12, true], review: [8, 6, 6, true]
  };
  const STYLES = {
    pick: ["#8c8a86", 1.5, []], ring: ["#1d5fbf", 3, []],
    chain: ["#1d5fbf", 2, [7, 5]], abort: ["#c4242a", 2, [7, 5]]
  };
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const random = (a, b) => a + Math.random() * (b - a);
  const running = state => state.indexOf("running") === 0;
  const font = (px, weight = 400) => `${weight} ${px}px "IBM Plex Sans", sans-serif`;

  function create(canvas, opts = {}) {
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("PetWorld needs a 2D canvas.");
    const parent = canvas.parentElement || canvas;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const saved = {};
    ["width", "height", "display", "touchAction", "cursor"].forEach(k => { saved[k] = canvas.style[k]; });
    Object.assign(canvas.style, { width: "100%", height: "100%", display: "block", touchAction: "none" });
    let pets = new Map(), links = new Map(), images = new Map(), serial = 0;
    let width = 1, height = 1, dpr = 1, top = 100, band = 300;
    let desiredHeight = clamp(Number(opts.petHeight) || 96, 48, 220), size = desiredHeight;
    let clock = 0, last = null, raf = 0, dead = false, reduced = media.matches;
    let hover = null, pointer = null;

    function geometry() {
      const effective = Math.min(size, width * 0.34, height * 0.48);
      top = Math.min(height * 0.48, Math.max(100, effective * 1.08 + 30));
      band = Math.max(1, height - top - 58);
    }
    function resize() {
      if (dead) return;
      const rect = parent.getBoundingClientRect();
      width = Math.max(1, rect.width); height = Math.max(1, rect.height);
      dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      geometry();
    }
    const observer = new ResizeObserver(resize);
    observer.observe(parent);
    resize();

    function load(p, petId) {
      p.petId = String(petId);
      if (!images.has(p.petId)) {
        const entry = { img: new Image(), ready: false, v2: false };
        images.set(p.petId, entry);
        entry.img.onload = () => {
          if (dead) return;
          entry.ready = entry.img.naturalWidth >= 1536 && entry.img.naturalHeight >= 1872;
          entry.v2 = entry.img.naturalHeight === 2288;
        };
        entry.img.onerror = () => { entry.ready = false; };
        entry.img.src = `/web/pets/${encodeURIComponent(p.petId)}/spritesheet.webp`;
      }
    }
    function dimensions(p) {
      // Keep the world usable on narrow embeds; perspective is tied to ground depth.
      const h = Math.min(size, width * 0.34, height * 0.48) * (0.88 + p.y * 0.18);
      return { h, w: h * 192 / 208 };
    }
    function point(p) { return { x: p.x * width, y: top + p.y * band }; }
    function bounds(p) {
      const { w } = dimensions(p);
      return { x: Math.min(0.45, (w / 2 + 16) / width), y: Math.min(0.22, 12 / band) };
    }
    function confine(p) {
      const b = bounds(p);
      p.x = clamp(p.x, b.x, 1 - b.x); p.y = clamp(p.y, b.y, 1 - b.y);
    }
    function target(p) {
      // Best of five random spots: the one farthest from every other pet (and their targets), so the commons
      // stays spread out instead of everyone piling into one corner.
      const b = bounds(p);
      let best = null, bestScore = -1;
      for (let k = 0; k < 5; k++) {
        const c = { x: random(b.x, 1 - b.x), y: random(b.y, 1 - b.y) };
        let score = 1e9;
        pets.forEach(q => {
          if (q === p) return;
          [q, q.target].forEach(o => { if (o) score = Math.min(score, Math.hypot((c.x - o.x) * width, (c.y - o.y) * band)); });
        });
        if (score > bestScore) { best = c; bestScore = score; }
      }
      p.target = best;
    }
    function rest(p) {
      p.target = null; p.mood = random(1.5, 5);
      p.rest = Math.random() < 0.22 ? "waiting" : "idle";
      p.look = Math.random() < 0.38 ? { d: Math.floor(random(0, 16)), time: 0 } : null;
    }
    function state(p, value) {
      if (p.state !== value) { p.state = value; p.frameTime = 0; }
    }
    function play(p, value, options = {}) {
      if (!STATES[value]) return;
      if (value === "waving") p.waved = clock;
      if (STATES[value][3]) {
        p.action = null; p.manual = value; state(p, value);
      } else {
        // Interruptions preserve the underlying behaviour, including an earlier play().
        p.action = { state: value, time: 0, prior: p.action ? p.action.prior : p.manual, then: options.then };
        p.vx = p.vy = 0; state(p, value); p.frameTime = 0;
      }
    }
    function seat(p) {
      const b = bounds(p), angle = -Math.PI / 2 + p.seat * Math.PI * 2 / p.seats;
      return { x: clamp(0.5 + Math.cos(angle) * 0.32, b.x, 1 - b.x),
        y: clamp(0.52 + Math.sin(angle) * 0.38, b.y, 1 - b.y) };
    }
    function facing(p) {
      const other = pets.get((p.action && p.action.meet) || p.faceId);
      const a = point(p);
      if (other) { const b = point(other); return { x: b.x - a.x, y: b.y - a.y }; }
      if (p.mode === "seated") return { x: width * 0.5 - a.x, y: top + band * 0.52 - a.y };
      return null;
    }
    function update(p, dt) {
      p.frameTime += dt;
      if (p.bubble && clock >= p.bubble.until) p.bubble = null;
      p.lift += ((hover === p.id ? 5 : 0) - p.lift) * Math.min(1, dt * 14);
      if (p.action) {
        p.action.time += dt;
        const a = p.action, spec = STATES[a.state];
        if (a.time < spec[1] / spec[2]) return;
        p.action = null; p.manual = a.prior;
        if (STATES[a.then]) { play(p, a.then); return; }
      }
      if (pointer && pointer.id === p.id && pointer.dragged) return;
      if (reduced) { p.vx = p.vy = 0; state(p, p.manual || p.rest); return; }
      if (p.manual && !running(p.manual)) { state(p, p.manual); return; }
      if (p.look) { p.look.time += dt; if (p.look.time > 1.75) p.look = null; }
      if (p.mode === "gather") p.target = seat(p);
      let dx = 0, dy = 0, distance = 0;
      const a = point(p), { w, h } = dimensions(p), speed = h * 0.92;
      if (p.target) {
        dx = p.target.x * width - a.x; dy = top + p.target.y * band - a.y;
        distance = Math.hypot(dx, dy);
        if (distance < 3) {
          p.vx = p.vy = 0;
          if (p.mode === "gather") {
            p.x = p.target.x; p.y = p.target.y; p.mode = "seated"; p.target = null;
          }
          else { rest(p); if (Math.random() < 1 / 40) play(p, "jumping"); }
          dx = dy = 0;
        } else {
          const pace = Math.min(speed, distance * 3.4);
          dx = dx / distance * pace; dy = dy / distance * pace;
        }
      } else if (p.mode === "wander") {
        p.mood -= dt;
        if (p.mood <= 0) target(p);
      }
      if (p.action) return;
      // An elliptical personal space protects both bodies and the labels at their feet.
      if (p.mode !== "seated") pets.forEach(q => {
        if (q === p) return;
        const b = point(q), qw = dimensions(q).w;
        let sx = a.x - b.x, sy = a.y - b.y;
        const rx = (w + qw) * 0.52 + 12, ry = Math.max(48, (h + dimensions(q).h) * 0.32);
        let gap = Math.hypot(sx / rx, sy / ry);
        if (gap < 1) {
          if (gap < 0.001) { sx = p.order < q.order ? -1 : 1; sy = 0.25; gap = 0.01; }
          // Assigned seats must win over separation as pets finish approaching them.
          const arrival = p.mode === "gather" ? Math.min(1, distance / (h * 0.8)) : 1;
          const len = Math.hypot(sx, sy), push = speed * (1 - gap) * 1.5 * arrival;
          dx += sx / len * push; dy += sy / len * push;
        }
      });
      const blend = 1 - Math.exp(-dt * 9);
      p.vx += (dx - p.vx) * blend; p.vy += (dy - p.vy) * blend;
      const oldX = p.x, oldY = p.y;
      p.x += p.vx * dt / width; p.y += p.vy * dt / band; confine(p);
      const moved = Math.hypot((p.x - oldX) * width, (p.y - oldY) * band) / Math.max(dt, 0.001);
      if (Math.abs(p.vx) > 5) p.left = p.vx < 0;
      if (moved > 5) state(p, p.manual && running(p.manual) ? p.manual : p.left ? "running-left" : "running-right");
      else state(p, p.rest);
      // Re-route a blocked wanderer instead of letting it run against a neighbour.
      p.blocked = p.target && moved < 6 && distance > 10 ? p.blocked + dt : 0;
      if (p.blocked > 1.4 && p.mode === "wander") { rest(p); p.blocked = 0; }
    }
    // Pets standing still in a looping or one-shot animation skip update()'s steering, so a gentle positional
    // nudge keeps them from stacking on top of each other (seated and dragged pets stay put).
    function separate(p, dt) {
      if (reduced || p.mode === "seated" || p.mode === "gather" || (pointer && pointer.id === p.id && pointer.dragged)) return;
      if (!(p.manual || p.action)) return; // moving pets already separate inside update()
      const a = point(p), { w, h } = dimensions(p);
      let dx = 0, dy = 0;
      pets.forEach(q => {
        if (q === p) return;
        const b = point(q), qd = dimensions(q);
        let sx = a.x - b.x, sy = a.y - b.y;
        const rx = (w + qd.w) * 0.42 + 10, ry = Math.max(40, (h + qd.h) * 0.26);
        const gap = Math.hypot(sx / rx, sy / ry);
        if (gap >= 1) return;
        if (gap < 0.001) { sx = p.order < q.order ? -1 : 1; sy = 0.2; }
        const len = Math.hypot(sx, sy) || 1, push = h * 0.9 * (1 - gap);
        dx += sx / len * push; dy += sy / len * push;
      });
      if (!dx && !dy) return;
      p.x += dx * dt / width; p.y += dy * dt / band; confine(p);
    }
    function greet() {
      if (reduced) return;
      const list = Array.from(pets.values());
      for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
        const p = list[i], q = list[j];
        if ([p, q].some(v => v.mode !== "wander" || v.manual || v.action || clock - v.waved < 12 || (pointer && pointer.id === v.id))) continue;
        const a = point(p), b = point(q), reach = (dimensions(p).w + dimensions(q).w) * 0.6;
        if (Math.hypot(a.x - b.x, a.y - b.y) < reach) {
          [p, q].forEach((v, index) => {
            v.waved = clock; play(v, "waving"); v.action.meet = index ? p.id : q.id;
          });
        }
      }
    }

    function roundRect(x, y, w, h, r, fill, stroke) {
      r = Math.min(r, w / 2, h / 2);
      ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r);
      ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r);
      ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
      ctx.fillStyle = fill; ctx.fill();
      if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke(); }
    }
    function ellipse(x, y, rx, ry, fill) {
      ctx.beginPath(); ctx.ellipse(x, y, Math.max(0.1, rx), Math.max(0.1, ry), 0, 0, Math.PI * 2);
      ctx.fillStyle = fill; ctx.fill();
    }
    function fit(text, max) {
      if (ctx.measureText(text).width <= max) return text;
      while (text.length && ctx.measureText(text + "…").width > max) text = text.slice(0, -1);
      return text + "…";
    }
    function overlaps(a, b) { return a.x < b.x + b.w + 4 && a.x + a.w + 4 > b.x && a.y < b.y + b.h + 4 && a.y + a.h + 4 > b.y; }
    function drawLinks() {
      const pills = [];
      links.forEach(link => {
        const p = pets.get(link.from), q = pets.get(link.to);
        if (!p || !q || p === q) return;
        const a = point(p), b = point(q), pd = dimensions(p), qd = dimensions(q);
        a.y -= pd.h * 0.4; b.y -= qd.h * 0.4;
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        let ix = width * 0.5 - mx, iy = top + band * 0.52 - my;
        if (Math.hypot(ix, iy) < 5) { ix = -(b.y - a.y); iy = b.x - a.x; }
        const bend = Math.min(110, Math.hypot(b.x - a.x, b.y - a.y) * 0.35), len = Math.hypot(ix, iy) || 1;
        const control = { x: mx + ix / len * bend, y: my + iy / len * bend };
        function at(t) {
          const s = 1 - t;
          return { x: s * s * a.x + 2 * s * t * control.x + t * t * b.x,
            y: s * s * a.y + 2 * s * t * control.y + t * t * b.y };
        }
        // Clip the actual curve against each body, then preserve its exact subcurve.
        function exit(v, dim, reverse) {
          const inside = t => {
            const u = at(reverse ? 1 - t : t);
            return Math.hypot((u.x - v.x) / (dim.w * 0.47 + 5), (u.y - v.y) / (dim.h * 0.4 + 5)) < 1;
          };
          let lo = 0, hi = 1 / 32;
          while (hi < 1 && inside(hi)) { lo = hi; hi += 1 / 32; }
          if (inside(hi)) return reverse ? 0 : 1;
          for (let n = 0; n < 12; n++) {
            const mid = (lo + hi) / 2;
            if (inside(mid)) lo = mid; else hi = mid;
          }
          return reverse ? 1 - hi : hi;
        }
        const t0 = exit(a, pd, false), t1 = exit(b, qd, true);
        if (t1 <= t0) return;
        const start = at(t0), end = at(t1), c = {
          x: start.x + (t1 - t0) * ((1 - t0) * (control.x - a.x) + t0 * (b.x - control.x)),
          y: start.y + (t1 - t0) * ((1 - t0) * (control.y - a.y) + t0 * (b.y - control.y))
        }, style = STYLES[link.style];
        ctx.strokeStyle = style[0]; ctx.lineWidth = style[1]; ctx.setLineDash(style[2]);
        ctx.beginPath(); ctx.moveTo(start.x, start.y); ctx.quadraticCurveTo(c.x, c.y, end.x, end.y); ctx.stroke();
        ctx.setLineDash([]);
        const angle = Math.atan2(end.y - c.y, end.x - c.x);
        ctx.beginPath(); ctx.moveTo(end.x, end.y);
        ctx.lineTo(end.x - 9 * Math.cos(angle - 0.45), end.y - 9 * Math.sin(angle - 0.45));
        ctx.moveTo(end.x, end.y); ctx.lineTo(end.x - 9 * Math.cos(angle + 0.45), end.y - 9 * Math.sin(angle + 0.45)); ctx.stroke();
        if (!link.label) return;
        ctx.font = font(12, 500);
        const label = fit(link.label, Math.min(200, width - 40)), w = ctx.measureText(label).width + 20;
        const box = { x: clamp((start.x + 2 * c.x + end.x) / 4 - w / 2, 4, Math.max(4, width - w - 4)),
          y: (start.y + 2 * c.y + end.y) / 4 - 12, w, h: 25 };
        for (let n = 0; n < 12 && pills.some(v => overlaps(v, box)); n++) box.y += 28;
        pills.push({ ...box, label, color: style[0] });
      });
      pills.forEach(p => {
        roundRect(p.x, p.y, p.w, p.h, 9, "#fff");
        ctx.font = font(12, 500); ctx.fillStyle = p.color; ctx.textAlign = "center";
        ctx.fillText(p.label, p.x + p.w / 2, p.y + 17);
      });
    }
    function drawPet(p) {
      const a = point(p), { w, h } = dimensions(p), entry = images.get(p.petId);
      const lift = reduced ? 0 : p.lift + (pointer && pointer.dragged && pointer.id === p.id ? 8 : 0);
      ellipse(a.x, a.y - 2, w * 0.32, Math.max(3, h * 0.065), "rgba(0,0,0,0.10)");
      const spec = STATES[p.state], frame = Math.floor(p.frameTime * spec[2]);
      let row = spec[0], col = reduced ? 0 : spec[3] ? frame % spec[1] : Math.min(frame, spec[1] - 1);
      const face = facing(p);
      if (face && Math.abs(face.x) > 1) p.left = face.x < 0;
      if (entry && entry.v2 && !p.action && p.state === "idle" && (face || p.look)) {
        const d = face ? (Math.round(Math.atan2(face.x, -face.y) * 8 / Math.PI) + 16) % 16
          : (p.look.d + [0, 1, 2, 1, 0][Math.min(4, Math.floor(p.look.time / 0.35))]) % 16;
        row = 9 + Math.floor(d / 8); col = d % 8;
        if (reduced) col = 0;
      }
      if (entry && entry.ready) {
        ctx.save(); ctx.translate(a.x, a.y - lift);
        if (p.left && row !== 1 && row !== 2 && row < 9) ctx.scale(-1, 1);
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(entry.img, col * 192, row * 208, 192, 208, -w / 2, -h, w, h);
        ctx.restore();
      } else ellipse(a.x, a.y - h * 0.4 - lift, w * 0.34, h * 0.36, "#d9d6d0");
      if (p.badge) {
        const x = a.x + w * 0.35, y = a.y - h * 0.82 - lift;
        ellipse(x, y, 9, 9, p.badge === "yes" ? "#24753a" : "#c4242a");
        ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.lineCap = "round"; ctx.beginPath();
        if (p.badge === "yes") { ctx.moveTo(x - 4, y); ctx.lineTo(x - 1, y + 3); ctx.lineTo(x + 4, y - 3); }
        else { ctx.moveTo(x - 3, y - 3); ctx.lineTo(x + 3, y + 3); ctx.moveTo(x + 3, y - 3); ctx.lineTo(x - 3, y + 3); }
        ctx.stroke(); ctx.lineCap = "butt";
      }
    }
    function drawLabels(list) {
      const used = [];
      list.forEach(p => {
        const a = point(p), max = Math.min(220, width - 20);
        ctx.font = font(13, 600); const name = fit(p.name, max), nw = ctx.measureText(name).width;
        ctx.font = font(12); const status = fit(p.status, max), sw = status ? ctx.measureText(status).width : 0;
        const w = Math.max(nw, sw) + 8, h = status ? 35 : 18;
        const box = { x: clamp(a.x - w / 2, 2, Math.max(2, width - w - 2)), y: a.y + 3, w, h };
        for (let n = 0; n < 8 && used.some(b => overlaps(b, box)); n++) box.y += 18;
        box.y = Math.min(box.y, height - h - 2); used.push(box);
        ctx.textAlign = "center"; ctx.lineWidth = 4; ctx.strokeStyle = "#faf9f7"; ctx.lineJoin = "round";
        ctx.font = font(13, 600); ctx.fillStyle = "#121212";
        ctx.strokeText(name, box.x + w / 2, box.y + 13); ctx.fillText(name, box.x + w / 2, box.y + 13);
        if (status) {
          ctx.font = font(12); ctx.fillStyle = "#5d5b57";
          ctx.strokeText(status, box.x + w / 2, box.y + 30); ctx.fillText(status, box.x + w / 2, box.y + 30);
        }
      });
    }
    function drawBubbles(list) {
      const used = [];
      list.forEach(p => {
        if (!p.bubble) return;
        ctx.font = font(13);
        const max = Math.max(1, Math.min(196, width - 44)), lines = [];
        let line = "";
        // Split oversized words too, so unbroken app strings cannot escape the bubble.
        p.bubble.text.split(/\s+/).forEach(word => {
          if (line && ctx.measureText(line + " " + word).width > max) { lines.push(line); line = ""; }
          for (const char of (line ? " " : "") + word) {
            if (line && ctx.measureText(line + char).width > max) { lines.push(line); line = ""; }
            line += char;
          }
        });
        if (line) lines.push(line);
        const a = point(p), w = Math.min(220, Math.max(40, ...lines.map(t => ctx.measureText(t).width + 24)));
        const h = lines.length * 18 + 20, box = { x: clamp(a.x - w / 2, 6, Math.max(6, width - w - 6)),
          y: Math.max(6, a.y - dimensions(p).h - h - 16 - p.lift), w, h };
        for (let n = 0; n < 8 && used.some(b => overlaps(b, box)); n++) box.y = Math.max(6, box.y - h - 6);
        used.push(box); roundRect(box.x, box.y, w, h, 12, "#fff", "#e4e2dd");
        const tail = clamp(a.x, box.x + 14, box.x + w - 14);
        ctx.beginPath(); ctx.moveTo(tail - 6, box.y + h - 0.5); ctx.lineTo(tail, box.y + h + 7);
        ctx.lineTo(tail + 6, box.y + h - 0.5); ctx.fillStyle = "#fff"; ctx.fill(); ctx.strokeStyle = "#e4e2dd"; ctx.stroke();
        ctx.textAlign = "left"; ctx.fillStyle = "#121212";
        lines.forEach((text, i) => ctx.fillText(text, box.x + 12, box.y + 24 + i * 18));
      });
    }
    function draw() {
      ctx.clearRect(0, 0, width, height); ctx.fillStyle = "#f6f4f0"; ctx.fillRect(0, 0, width, height);
      ellipse(width * 0.5, top + band * 0.52, Math.min(width * 0.21, 205), Math.min(48, band * 0.21), "#efece6");
      drawLinks();
      const list = Array.from(pets.values()).sort((a, b) => a.y - b.y || a.order - b.order);
      list.forEach(drawPet); drawLabels(list); drawBubbles(list);
    }
    function tick(time) {
      raf = 0;
      if (dead || document.hidden) return;
      const dt = last === null ? 0 : clamp((time - last) / 1000, 0, 0.2);
      last = time; clock += dt;
      if (dpr !== (window.devicePixelRatio || 1)) resize();
      size += (desiredHeight - size) * (1 - Math.exp(-dt * 8)); geometry();
      pets.forEach(p => { confine(p); update(p, dt); separate(p, dt); }); greet(); draw();
      raf = requestAnimationFrame(tick);
    }
    function visibility() {
      if (raf) cancelAnimationFrame(raf);
      raf = 0; last = null;
      if (!document.hidden && !dead) raf = requestAnimationFrame(tick);
    }
    function motion() {
      reduced = media.matches;
      pets.forEach(p => { p.vx = p.vy = 0; p.look = null; });
    }
    function eventPoint(e) {
      const r = canvas.getBoundingClientRect();
      return { x: (e.clientX - r.left) * width / (r.width || 1), y: (e.clientY - r.top) * height / (r.height || 1) };
    }
    function hit(a) {
      return Array.from(pets.values()).sort((p, q) => q.y - p.y).find(p => {
        const b = point(p), d = dimensions(p);
        return Math.abs(a.x - b.x) <= d.w * 0.46 && a.y >= b.y - d.h && a.y <= b.y + 8;
      });
    }
    function cursor() { canvas.style.cursor = pointer && pointer.dragged ? "grabbing" : hover ? "pointer" : "default"; }
    function down(e) {
      if (pointer || e.button !== 0) return;
      const a = eventPoint(e), p = hit(a);
      if (!p) return;
      const b = point(p);
      pointer = { id: p.id, pointerId: e.pointerId, start: a, ox: b.x - a.x, oy: b.y - a.y, dragged: false };
      canvas.setPointerCapture(e.pointerId); hover = p.id; cursor();
    }
    function move(e) {
      const a = eventPoint(e);
      if (pointer && pointer.pointerId === e.pointerId) {
        const p = pets.get(pointer.id);
        if (!p) return;
        if (!pointer.dragged && Math.hypot(a.x - pointer.start.x, a.y - pointer.start.y) > 5) {
          pointer.dragged = true;
          if (p.action) p.manual = p.action.prior;
          p.action = null;
        }
        if (pointer.dragged) {
          p.x = (a.x + pointer.ox) / width; p.y = (a.y + pointer.oy - top) / band; confine(p);
          p.vx = p.vy = 0; state(p, "idle");
        }
      } else hover = (hit(a) || {}).id || null;
      cursor();
    }
    function up(e) {
      if (!pointer || pointer.pointerId !== e.pointerId) return;
      const drag = pointer, p = pets.get(drag.id); pointer = null;
      if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
      hover = (hit(eventPoint(e)) || {}).id || null; cursor();
      if (!p) return;
      if (drag.dragged) { if (p.mode === "wander") rest(p); play(p, "jumping"); }
      else if (e.type === "pointerup" && typeof opts.onSelect === "function") opts.onSelect(p.id);
    }
    function leave() { if (!pointer) { hover = null; cursor(); } }
    const events = { pointerdown: down, pointermove: move, pointerup: up, pointercancel: up, pointerleave: leave };
    Object.keys(events).forEach(k => canvas.addEventListener(k, events[k]));
    document.addEventListener("visibilitychange", visibility); media.addEventListener("change", motion);
    visibility();
    const withPet = (id, fn) => { if (!dead && pets.has(id)) fn(pets.get(id)); };
    const selected = ids => (ids === undefined ? Array.from(pets.keys()) : Array.from(new Set(ids))).filter(id => pets.has(id));
    const api = {
      setPets(items) {
        if (dead) return;
        const next = new Map();
        items.forEach((item, i) => {
          let p = pets.get(item.id);
          if (!p) {
            p = { id: item.id, order: serial++, x: (i + 0.5) / Math.max(1, items.length), y: 0.35 + (i % 2) * 0.4,
              vx: 0, vy: 0, state: "idle", frameTime: 0, mode: "wander", rest: "idle", mood: random(1.5, 5),
              manual: null, action: null, target: null, waved: -12, left: false, look: null, lift: 0, blocked: 0,
              faceId: null, status: "", badge: null, bubble: null };
          }
          p.name = String(item.name == null ? item.id : item.name);
          load(p, item.petId); confine(p); next.set(item.id, p);
        });
        pets = next;
        links.forEach((v, k) => { if (!pets.has(v.from) || !pets.has(v.to)) links.delete(k); });
        if (pointer && !pets.has(pointer.id)) {
          if (canvas.hasPointerCapture(pointer.pointerId)) canvas.releasePointerCapture(pointer.pointerId);
          pointer = null;
        }
        if (!pets.has(hover)) hover = null; cursor();
      },
      setPet(id, petId) { withPet(id, p => load(p, petId)); },
      setPetHeight(px) { if (!dead && Number.isFinite(Number(px))) desiredHeight = clamp(Number(px), 48, 220); },
      say(id, text, ms = 3500) { withPet(id, p => { p.bubble = text ? { text: String(text), until: clock + Math.max(0, Number(ms) || 0) / 1000 } : null; }); },
      status(id, text) { withPet(id, p => { p.status = String(text || ""); }); },
      play(id, value, options) { withPet(id, p => play(p, value, options)); },
      face(id, other) { withPet(id, p => { p.faceId = other == null ? null : other; }); },
      gather(ids) {
        if (dead) return;
        const list = selected(ids);
        list.forEach((id, i) => withPet(id, p => {
          p.mode = "gather"; p.seat = i; p.seats = list.length; p.manual = null; p.action = null;
          p.faceId = null; p.look = null; p.rest = "idle"; p.target = seat(p);
          if (reduced) { p.x = p.target.x; p.y = p.target.y; p.mode = "seated"; p.target = null; state(p, "idle"); }
        }));
      },
      release(ids) {
        if (dead) return;
        selected(ids).forEach(id => withPet(id, p => {
          p.mode = "wander"; p.manual = null; p.action = null; p.faceId = null; rest(p); state(p, "idle");
        }));
      },
      link(from, to, options = {}) {
        if (dead || !pets.has(from) || !pets.has(to) || from === to) return null;
        const key = options.key == null ? `pet-link-${++serial}` : options.key;
        links.set(key, { from, to, style: STYLES[options.style] ? options.style : "pick", label: String(options.label || "") });
        return key;
      },
      unlink(key) { if (!dead) links.delete(key); },
      clearLinks(style) { if (!dead) links.forEach((v, k) => { if (style === undefined || v.style === style) links.delete(k); }); },
      badge(id, value) { withPet(id, p => { p.badge = value === "yes" || value === "no" ? value : null; }); },
      pets() { return Array.from(pets.values(), p => ({ id: p.id, x: p.x, y: p.y, state: p.state })); },
      destroy() {
        if (dead) return;
        dead = true; if (raf) cancelAnimationFrame(raf); observer.disconnect();
        document.removeEventListener("visibilitychange", visibility); media.removeEventListener("change", motion);
        Object.keys(events).forEach(k => canvas.removeEventListener(k, events[k]));
        if (pointer && canvas.hasPointerCapture(pointer.pointerId)) canvas.releasePointerCapture(pointer.pointerId);
        images.forEach(v => { v.img.onload = v.img.onerror = null; });
        pets.clear(); links.clear(); images.clear(); pointer = null;
        Object.assign(canvas.style, saved); ctx.clearRect(0, 0, width, height);
      }
    };
    return api;
  }
  window.PetWorld = { create };
})();
