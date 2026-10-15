// A dependency graph drawn in layers, depth running downward like a plumb line.
// Used twice: as the hero's backdrop and as the survey's Graph tab (where it is interactive).
//
// data = { nodes: [[key, name, version, depth, direct], ...], edges: [[source, target], ...] }

const PAD_X = 28;
const PAD_TOP = 64;
const PAD_BOTTOM = 40;

/** Parents of every node, and children, as index lists. */
function adjacency(data) {
  const n = data.nodes.length;
  const parents = Array.from({ length: n }, () => []);
  const children = Array.from({ length: n }, () => []);
  for (const [s, t] of data.edges) {
    children[s].push(t);
    parents[t].push(s);
  }
  return { parents, children };
}

/** Order each layer by the average position of its neighbours, a few sweeps, to keep edges from tangling. */
function orderLayers(layers, adj, pos) {
  const maxD = layers.length - 1;
  const frac = (i) => pos[i];
  const reposition = (d) => layers[d].forEach((idx, k) => { pos[idx] = (k + 0.5) / layers[d].length; });
  for (let d = 1; d <= maxD; d++) reposition(d);
  for (let sweep = 0; sweep < 4; sweep++) {
    for (let d = 2; d <= maxD; d++) {
      const key = (i) => { const p = adj.parents[i].filter((q) => pos[q] != null); return p.length ? p.reduce((a, q) => a + frac(q), 0) / p.length : frac(i); };
      layers[d].sort((a, b) => key(a) - key(b));
      reposition(d);
    }
    for (let d = maxD - 1; d >= 1; d--) {
      const key = (i) => { const c = adj.children[i]; return c.length ? c.reduce((a, q) => a + frac(q), 0) / c.length : frac(i); };
      layers[d].sort((a, b) => key(a) - key(b));
      reposition(d);
    }
  }
}

/** Keys of the chain from a direct dependency down to one node, following parents one layer at a time. */
export function pathTo(data, target) {
  const adj = adjacency(data);
  const keys = [];
  let cur = target;
  while (cur != null) {
    keys.push(data.nodes[cur][0]);
    const depth = data.nodes[cur][3];
    if (depth <= 1) break;
    cur = adj.parents[cur].find((p) => data.nodes[p][3] === depth - 1);
  }
  return keys.reverse();
}

export function findNode(data, name, version) {
  return data.nodes.findIndex((n) => n[1] === name && n[2] === version);
}

export function createGraphView(canvas, { interactive = false, labels = true, loop = false, inset = () => 0, anchor = () => 0.5, padTop = PAD_TOP } = {}) {
  const ctx = canvas.getContext("2d");
  const host = canvas.parentElement;
  let data = null;
  let adj = null;
  let xs = [];
  let ys = [];
  let pathIdx = [];
  let hover = -1;
  let related = null;
  let progress = 1; // 0..1 along the path; the bob rides it
  let raf = 0;
  let timer = 0;
  let W = 0;
  let H = 0;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const tip = interactive ? Object.assign(document.createElement("div"), { className: "gv-tip", hidden: true }) : null;
  if (tip) host.appendChild(tip);

  const css = (name, fallback) => getComputedStyle(canvas).getPropertyValue(name).trim() || fallback;

  function layout() {
    if (!data) return;
    adj = adjacency(data);
    const maxD = Math.max(1, ...data.nodes.map((n) => n[3] ?? 0));
    const layers = Array.from({ length: maxD + 1 }, () => []);
    data.nodes.forEach((n, i) => { if (n[3] != null && n[3] >= 1) layers[n[3]].push(i); });
    layers.forEach((l) => l.sort((a, b) => (data.nodes[a][0] < data.nodes[b][0] ? -1 : 1)));
    const pos = new Array(data.nodes.length).fill(null);
    orderLayers(layers, adj, pos);
    xs = new Array(data.nodes.length).fill(-1);
    ys = new Array(data.nodes.length).fill(-1);
    const span = Math.max(1, maxD - 1);
    const left = inset() * W + PAD_X; // lets the hero keep its headline clear of the graph
    const right = W - PAD_X;
    const onPath = new Set(pathIdx);
    // The poisoned path is pinned to one vertical line, the plumb line; every other node hangs around it.
    const plumbX = left + anchor() * (right - left);
    layers.forEach((l, d) => {
      if (d < 1) return;
      const at = l.findIndex((idx) => onPath.has(idx));
      if (at >= 0) { const [p] = l.splice(at, 1); l.splice(Math.floor(l.length / 2), 0, p); }
      const y = padTop + ((d - 1) / span) * (H - padTop - PAD_BOTTOM);
      const kp = l.findIndex((idx) => onPath.has(idx));
      l.forEach((idx, k) => {
        ys[idx] = y;
        if (kp < 0) xs[idx] = left + ((k + 0.5) / l.length) * (right - left);
        else if (k === kp) xs[idx] = plumbX;
        else if (k < kp) xs[idx] = left + ((k + 0.5) / kp) * (plumbX - 14 - left);
        else xs[idx] = plumbX + 14 + ((k - kp - 0.5) / (l.length - kp - 1)) * (right - plumbX - 14);
      });
    });
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const r = host.getBoundingClientRect();
    W = Math.max(200, Math.round(r.width));
    H = Math.max(160, Math.round(r.height));
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = `${W}px`;
    canvas.style.height = `${H}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    layout();
    draw();
  }

  function pathPoints() { return pathIdx.map((i) => [xs[i], ys[i]]); }

  /** Point at fraction p along the polyline of the path (including the hanging bar above the first node). */
  function along(p) {
    const pts = pathPoints();
    if (!pts.length) return null;
    const full = [[pts[0][0], padTop - 30], ...pts];
    const lens = full.slice(1).map((q, i) => Math.hypot(q[0] - full[i][0], q[1] - full[i][1]));
    const total = lens.reduce((a, b) => a + b, 0) || 1;
    let want = p * total;
    for (let i = 0; i < lens.length; i++) {
      if (want <= lens[i] || i === lens.length - 1) {
        const f = Math.min(1, want / (lens[i] || 1));
        return { x: full[i][0] + (full[i + 1][0] - full[i][0]) * f, y: full[i][1] + (full[i + 1][1] - full[i][1]) * f, upto: i + 1 };
      }
      want -= lens[i];
    }
    return null;
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    if (!data || !adj) return;
    const cEdge = css("--g-edge", "rgba(120,180,190,.16)");
    const cNode = css("--g-node", "#62d3c7");
    const cRel = css("--g-related", "#d9eef0");
    const cPath = css("--g-path", "#ff6b3d");
    const cLabel = css("--g-label", "#e8f3f4");
    const dim = related != null;

    ctx.lineWidth = 0.7;
    for (const [s, t] of data.edges) {
      if (xs[s] < 0 || xs[t] < 0 || ys[s] === ys[t]) continue; // same-layer edges would stack into one bright line
      const hot = dim && related.has(s) && related.has(t);
      ctx.strokeStyle = hot ? cRel : cEdge;
      ctx.globalAlpha = dim ? (hot ? 0.9 : 0.25) : 1;
      ctx.beginPath();
      ctx.moveTo(xs[s], ys[s]);
      ctx.lineTo(xs[t], ys[t]);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    data.nodes.forEach((n, i) => {
      if (xs[i] < 0) return;
      const deg = adj.parents[i].length + adj.children[i].length;
      const r = Math.min(3.6, 1.5 + Math.sqrt(deg) * 0.32);
      const on = !dim || related.has(i);
      ctx.globalAlpha = on ? 1 : 0.3;
      ctx.fillStyle = dim && related.has(i) ? cRel : cNode;
      ctx.beginPath();
      ctx.arc(xs[i], ys[i], r, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;

    if (pathIdx.length) drawPath(cPath, cLabel);
    if (hover >= 0) {
      ctx.strokeStyle = cRel;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(xs[hover], ys[hover], 6, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  function drawPath(cPath, cLabel) {
    const pts = pathPoints();
    const full = [[pts[0][0], padTop - 30], ...pts];
    const head = along(progress);
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = cPath;
    ctx.shadowColor = cPath;
    ctx.shadowBlur = 14;
    ctx.lineWidth = 2.6;
    ctx.beginPath();
    ctx.moveTo(full[0][0], full[0][1]);
    for (let i = 1; i < head.upto; i++) ctx.lineTo(full[i][0], full[i][1]);
    ctx.lineTo(head.x, head.y);
    ctx.stroke();
    ctx.shadowBlur = 0;
    // the bar the line hangs from
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(full[0][0] - 11, full[0][1]);
    ctx.lineTo(full[0][0] + 11, full[0][1]);
    ctx.stroke();
    // joints already passed
    pts.forEach(([x, y], i) => {
      if (i + 1 >= head.upto && progress < 1) return;
      const last = i === pts.length - 1;
      if (last) return;
      ctx.fillStyle = cLabel;
      ctx.beginPath();
      ctx.arc(x, y, 3.6, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = cPath;
      ctx.lineWidth = 1.6;
      ctx.stroke();
    });
    // the bob
    ctx.fillStyle = cPath;
    ctx.shadowColor = cPath;
    ctx.shadowBlur = 18;
    ctx.beginPath();
    ctx.arc(head.x, head.y, progress >= 1 ? 8 : 6.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    if (labels) {
      ctx.font = '500 13px "IBM Plex Mono", ui-monospace, monospace';
      ctx.textBaseline = "middle";
      pathIdx.forEach((idx, i) => {
        if (progress < 1 && i + 1 > head.upto - 0.5) return;
        const n = data.nodes[idx];
        const text = `${n[1]}@${n[2]}`;
        const x = xs[idx];
        const right = x < W - 200;
        ctx.textAlign = right ? "left" : "right";
        ctx.lineJoin = "round";
        ctx.lineWidth = 5;
        ctx.strokeStyle = css("--g-halo", "#061620");
        ctx.strokeText(text, x + (right ? 16 : -16), ys[idx]);
        ctx.fillStyle = i === pathIdx.length - 1 ? cPath : cLabel;
        ctx.fillText(text, x + (right ? 16 : -16), ys[idx]);
      });
    }
  }

  function setData(next) {
    data = next;
    hover = -1;
    related = null;
    pathIdx = [];
    resize();
  }

  function setPath(keys, { animate = true } = {}) {
    cancelAnimationFrame(raf);
    clearTimeout(timer);
    const index = new Map(data.nodes.map((n, i) => [n[0], i]));
    pathIdx = (keys ?? []).map((k) => index.get(k)).filter((i) => i != null);
    progress = pathIdx.length && animate && !reduced ? 0 : 1;
    layout();
    draw();
    if (pathIdx.length && progress < 1) run(1700);
  }

  function run(duration) {
    const start = performance.now();
    const ease = (t) => 1 - Math.pow(1 - t, 3);
    const step = (now) => {
      progress = ease(Math.min(1, (now - start) / duration));
      draw();
      if (progress < 1) raf = requestAnimationFrame(step);
      else if (loop && !reduced) timer = setTimeout(() => { progress = 0; run(duration); }, 3200);
    };
    raf = requestAnimationFrame(step);
  }

  function nearest(mx, my) {
    let best = -1;
    let bestD = 12 * 12;
    for (let i = 0; i < xs.length; i++) {
      if (xs[i] < 0) continue;
      const d = (xs[i] - mx) ** 2 + (ys[i] - my) ** 2;
      if (d < bestD) { bestD = d; best = i; }
    }
    return best;
  }

  function relatedTo(i) {
    const seen = new Set([i]);
    for (const dir of [adj.parents, adj.children]) {
      const stack = [i];
      while (stack.length) for (const nx of dir[stack.pop()]) if (!seen.has(nx)) { seen.add(nx); stack.push(nx); }
    }
    return seen;
  }

  if (interactive) {
    canvas.addEventListener("pointermove", (e) => {
      const r = canvas.getBoundingClientRect();
      const i = nearest(e.clientX - r.left, e.clientY - r.top);
      if (i === hover) return;
      hover = i;
      related = i >= 0 ? relatedTo(i) : null;
      if (i >= 0) {
        const n = data.nodes[i];
        tip.textContent = `${n[1]}@${n[2]}${n[4] ? " · direct dependency" : ` · depth ${n[3]}`} · ${adj.parents[i].length} required by, ${adj.children[i].length} requires`;
        tip.style.left = `${Math.min(xs[i] + 12, W - 250)}px`;
        tip.style.top = `${Math.max(ys[i] - 30, 4)}px`;
        tip.hidden = false;
      } else tip.hidden = true;
      draw();
    });
    canvas.addEventListener("pointerleave", () => { hover = -1; related = null; tip.hidden = true; draw(); });
  }

  const ro = new ResizeObserver(() => { if (host.clientWidth > 0) resize(); });
  ro.observe(host);

  return {
    setData, setPath, resize,
    replay: () => { if (pathIdx.length && !reduced) { cancelAnimationFrame(raf); clearTimeout(timer); progress = 0; run(1700); } },
    destroy: () => { ro.disconnect(); cancelAnimationFrame(raf); clearTimeout(timer); tip?.remove(); },
  };
}
