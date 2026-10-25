/* Codex Pets sprite sheets: 8 columns, cells 192x208. Row: [frames, fps].
   Source of the layout: codex-pet-share src/playground/core/config.ts (MIT). */
(function () {
  const CELL_W = 192, CELL_H = 208;
  const ROWS = {
    idle: [0, 6, 6], "running-right": [1, 8, 12], "running-left": [2, 8, 12], waving: [3, 4, 5],
    jumping: [4, 5, 14], failed: [5, 8, 6], waiting: [6, 6, 4], running: [7, 6, 12], review: [8, 6, 6],
  };
  // public face -> sprite row. One mapping for every student.
  const FACE = {
    idle: "idle", thinking: "review", shrug: "waiting", covering: "jumping", relieved: "waving",
    walking: "running-right", failed: "failed",
  };
  const cache = new Map();
  const BADGE_SCALE = 0.25;

  function load(petId) {
    if (cache.has(petId)) return cache.get(petId);
    const img = new Image();
    const entry = { img, ok: false, failed: false };
    img.onload = () => {
      // badges are small: draw from a quarter-size copy so many sheets don't thrash the image cache
      const c = document.createElement("canvas");
      c.width = Math.round(img.naturalWidth * BADGE_SCALE); c.height = Math.round(img.naturalHeight * BADGE_SCALE);
      const g = c.getContext("2d"); g.imageSmoothingQuality = "high"; g.drawImage(img, 0, 0, c.width, c.height);
      entry.src = c; entry.ok = true;
    };
    img.onerror = () => { entry.failed = true; };
    img.src = window.TAGOUT_PET_URL ? window.TAGOUT_PET_URL(petId) : `/web/pets/${petId}/spritesheet.webp`;
    cache.set(petId, entry);
    return entry;
  }

  /** Draw one frame. Returns false when the sheet isn't loaded (caller draws a fallback). */
  function draw(ctx, petId, face, t, x, y, w, h, flip) {
    const e = load(petId);
    if (!e.ok) return false;
    const [row, frames, fps] = ROWS[FACE[face] || face] || ROWS.idle;
    const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    const col = reduce ? 0 : Math.floor((t / 1000) * fps) % frames;
    ctx.save();
    if (flip) { ctx.translate(x + w, y); ctx.scale(-1, 1); x = 0; y = 0; }
    const k = e.src ? BADGE_SCALE : 1;
    ctx.drawImage(e.src || e.img, col * CELL_W * k, row * CELL_H * k, CELL_W * k, CELL_H * k, x, y, w, h);
    ctx.restore();
    return true;
  }

  /** A small canvas that keeps one pet animated in a state (for the roster and the phones). */
  function badge(canvas, petId, face) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 32, h = canvas.clientHeight || 35;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    canvas.dataset.pet = petId; canvas.dataset.face = face || "idle";
    const tick = (t) => {
      if (!canvas.isConnected) return;
      ctx.clearRect(0, 0, w, h);
      if (!draw(ctx, canvas.dataset.pet, canvas.dataset.face, t, 0, 0, w, h)) {
        ctx.fillStyle = "#cfccc6"; ctx.beginPath(); ctx.arc(w / 2, h / 2, Math.min(w, h) / 3, 0, 7); ctx.fill();
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  window.Sprites = { load, draw, badge, CELL_W, CELL_H };
})();
