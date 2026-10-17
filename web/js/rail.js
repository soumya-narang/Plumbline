// The timeline as a plumb line: a string hangs down the left edge of the instrument, each event is a knot on it, and a brass
// bob is the playhead. Drag the bob and it follows the pointer 1:1 (resisting at the ends); let go and it carries your
// velocity on to the knot a flick would reach, swinging a little before it hangs still.
import { clock, esc, hhmm } from "./format.js";
import { createSpring, project, rubberband, velocityTracker } from "./spring.js";

const SECS = (iso) => Date.parse(iso) / 1000;
const BOB_H = 30; // px; the bob hangs with its tip on the knot
const TOP = 20; // px of string above the first knot
const BOTTOM = 26;
const HYSTERESIS = 5; // px before a press becomes a drag, so taps on a knot still tap

const KIND = { start: "start", advisory: "release", approval: "decision", revision: "later" };
const CAPTION = { release: "Poisoned releases", decision: "Decisions", later: "Later" };

/** Short name for a knot's label: "keyv published" -> "keyv". */
const shortLabel = (s) => {
  if (s.kind === "start") return "Start";
  if (s.kind === "advisory") return s.label.replace(/ published$/, "").replace(/^@[^/]+\//, ""); // "@cacheable/net" -> "net"
  if (s.kind === "approval") return s.label.replace(/^Approved /, "").replace(/^[^/]+\//, ""); // "planted/orders-api" -> "orders-api"
  return s.label.replace(/ \(hypothetical\)/, "");
};

export function createRail({ stops, onChange }) {
  const root = document.getElementById("rail");
  const prev = document.getElementById("tl-prev");
  const next = document.getElementById("tl-next");
  const play = document.getElementById("tl-play");
  const nowLabel = document.getElementById("tl-label");
  const clockEl = document.getElementById("tl-clock");
  const hintEl = document.getElementById("rail-hint");
  const vertical = () => matchMedia("(min-width: 1180px)").matches;

  let index = 0;
  let timer = null;
  let ys = []; // y of each knot (px), desktop only
  let height = 0;
  let stringEl;
  let bobEl;
  let heatEl;

  // ---- layout ---------------------------------------------------------------------------------------------------------

  function layout() {
    const rows = [];
    let lastKind = null;
    stops.forEach((s, i) => {
      const k = KIND[s.kind];
      if (k !== lastKind && k !== "start") rows.push(`<li class="caption" aria-hidden="true">${CAPTION[k]}</li>`);
      lastKind = k;
      const text = `${clock(s.at)} UTC, ${s.label}${s.scripted ? " (hypothetical)" : ""}`;
      rows.push(`<li class="knot-row ${k}"><button type="button" class="knot" data-i="${i}" aria-label="${esc(text)}">
          <span class="when">${hhmm(s.at)}</span><i class="glyph" aria-hidden="true"></i><span class="what">${esc(shortLabel(s))}</span></button></li>`);
    });
    root.innerHTML = `<div class="string" aria-hidden="true"><span class="heat"></span></div>
      <ol class="knots">${rows.join("")}</ol>
      <div class="bob" aria-hidden="true">${bobSvg()}</div>`;
    stringEl = root.querySelector(".string");
    heatEl = root.querySelector(".heat");
    bobEl = root.querySelector(".bob");
    measure();
    paint(index, { snap: true });
  }

  /** The brass bob: a faceted cone, tip down, hung from a short eye. Drawn once, shaded with gradients. */
  function bobSvg() {
    return `<svg viewBox="0 0 24 34" width="22" height="31" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="brass" x1="0" x2="1"><stop offset="0" stop-color="#8d6a22"/><stop offset=".38" stop-color="#e6c877"/><stop offset=".62" stop-color="#c7a04a"/><stop offset="1" stop-color="#6f5118"/></linearGradient>
        <linearGradient id="brass-top" x1="0" x2="1"><stop offset="0" stop-color="#a9822f"/><stop offset=".5" stop-color="#f1dc98"/><stop offset="1" stop-color="#8a6620"/></linearGradient>
      </defs>
      <path d="M12 0v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/>
      <path d="M4 7.2 12 4.6 20 7.2 20.8 11.4 12 33 3.2 11.4Z" fill="url(#brass)"/>
      <path d="M4 7.2 12 4.6 20 7.2 12 9.6Z" fill="url(#brass-top)"/>
      <path d="M12 9.6V33" stroke="#fff" stroke-opacity=".22" stroke-width=".7"/>
    </svg>`;
  }

  /** On desktop the knots are absolutely positioned on the string; measure them so the bob can hang from each. */
  function measure() {
    if (!vertical()) { ys = []; return; }
    const base = root.getBoundingClientRect().top;
    ys = [...root.querySelectorAll(".knot")].map((b) => {
      const g = b.querySelector(".glyph").getBoundingClientRect();
      return g.top + g.height / 2 - base;
    });
    height = root.getBoundingClientRect().height;
    stringEl.style.height = `${ys.at(-1) + BOTTOM}px`;
  }

  // ---- the bob is a spring --------------------------------------------------------------------------------------------

  const place = (y) => {
    if (!bobEl) return;
    bobEl.style.transform = `translate3d(0, ${y - BOB_H}px, 0)`;
    heatEl.style.height = `${Math.max(0, y - BOB_H + 4)}px`; // the string above the bob is the part already played
  };
  const bob = createSpring(0, place, { damping: 1, response: 0.4 });
  const nearestKnot = (y) => ys.reduce((best, k, i) => (Math.abs(k - y) < Math.abs(ys[best] - y) ? i : best), 0);

  // ---- state -> pixels ------------------------------------------------------------------------------------------------

  /** Show stop i everywhere (clock, label, knot states). `move: false` previews it while the bob is being dragged. */
  function paint(i = index, { snap = false, move = true, cfg } = {}) {
    const stop = stops[i];
    root.querySelectorAll(".knot").forEach((el) => {
      const n = Number(el.dataset.i);
      el.classList.toggle("passed", n <= i);
      el.classList.toggle("current", n === i);
      el.setAttribute("aria-current", n === i ? "step" : "false");
    });
    clockEl.textContent = clock(stop.at);
    nowLabel.innerHTML = `${esc(stop.label.replace(/ \(hypothetical\)/, ""))}${stop.scripted ? ' <span class="hypo">hypothetical</span>' : ""}`;
    prev.disabled = i === 0;
    next.disabled = i === stops.length - 1;
    root.dataset.kind = KIND[stop.kind];
    if (move && ys.length) snap ? bob.set(ys[i]) : bob.to(ys[i], cfg);
    if (!vertical()) { // narrow screens: the chips scroll so the current event is always in view
      const chip = root.querySelector(".knot.current")?.parentElement;
      const list = root.querySelector(".knots");
      if (chip && list) list.scrollTo({ left: chip.offsetLeft - (list.clientWidth - chip.offsetWidth) / 2, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches || snap ? "auto" : "smooth" });
    }
    root.classList.toggle("hot", stops.slice(0, i + 1).some((s) => s.kind === "advisory")); // the string runs flag-red once poison is in
  }

  function go(i, { announce = true, cfg } = {}) {
    const to = Math.max(0, Math.min(stops.length - 1, i));
    const changed = to !== index;
    index = to;
    paint(index, { cfg });
    if (changed) { try { navigator.vibrate?.(8); } catch { /* not supported */ } } // the haptic lands with the knot, same frame
    if (announce) onChange(stops[index], index);
  }

  function stopPlaying() {
    clearInterval(timer);
    timer = null;
    play.dataset.playing = "false";
    play.setAttribute("aria-label", "Play the incident");
  }
  function startPlaying() {
    if (index === stops.length - 1) go(0);
    play.dataset.playing = "true";
    play.setAttribute("aria-label", "Pause");
    timer = setInterval(() => (index >= stops.length - 1 ? stopPlaying() : go(index + 1)), 2200);
  }

  // ---- direct manipulation --------------------------------------------------------------------------------------------

  let drag = null;
  let justDragged = false;
  const dismissHint = () => hintEl?.classList.add("gone");

  root.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || !vertical()) return;
    const top = root.getBoundingClientRect().top;
    const y = e.clientY - top;
    const grabbed = e.target.closest(".bob");
    drag = { id: e.pointerId, y0: e.clientY, top, active: false, vt: velocityTracker(), grabbed: !!grabbed, offset: grabbed ? bob.value - y : 0 };
    drag.vt.add(y);
    dismissHint();
  });

  root.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (!drag.active) {
      if (Math.abs(e.clientY - drag.y0) < HYSTERESIS) return;
      if (!drag.grabbed) { drag = null; return; } // only the bob drags; the knots are for tapping
      drag.active = true;
      root.setPointerCapture(e.pointerId);
      root.classList.add("dragging");
      stopPlaying();
    }
    const y = e.clientY - drag.top;
    drag.vt.add(y);
    const min = ys[0];
    const max = ys.at(-1);
    let at = y + drag.offset;
    if (at < min) at = min + rubberband(at - min, 220); // past an end the bob resists, then gives
    else if (at > max) at = max + rubberband(at - max, 220);
    bob.set(at);
    const k = nearestKnot(Math.max(min, Math.min(max, at)));
    paint(k, { move: false });
  });

  const release = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const d = drag;
    drag = null;
    root.classList.remove("dragging");
    if (!d.active) return;
    justDragged = true;
    setTimeout(() => (justDragged = false));
    const v = d.vt.get(); // px/s at the moment of release
    const landing = Math.max(ys[0], Math.min(ys.at(-1), bob.value + project(v, 0.99))); // where a flick would coast to; a short control wants the snappier 0.99 rate
    const to = nearestKnot(landing);
    // a flick carries momentum, so it earns the pendulum's swing; a slow placement just settles
    const flicked = Math.abs(v) > 350;
    go(to, { announce: to !== index, cfg: { velocity: v, damping: flicked ? 0.62 : 1, response: flicked ? 0.5 : 0.36 } });
  };
  root.addEventListener("pointerup", release);
  root.addEventListener("pointercancel", release);

  root.addEventListener("click", (e) => {
    if (justDragged) return;
    const el = e.target.closest("[data-i]");
    if (el) { stopPlaying(); dismissHint(); go(Number(el.dataset.i)); }
  });
  prev.addEventListener("click", () => { stopPlaying(); dismissHint(); go(index - 1); });
  next.addEventListener("click", () => { stopPlaying(); dismissHint(); go(index + 1); });
  play.addEventListener("click", () => { dismissHint(); timer ? stopPlaying() : startPlaying(); });

  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea, select, [contenteditable]") || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "ArrowDown" || e.key === "ArrowRight") { if (e.target.closest("[role=tablist]")) return; stopPlaying(); go(index + 1); }
    if (e.key === "ArrowUp" || e.key === "ArrowLeft") { if (e.target.closest("[role=tablist]")) return; stopPlaying(); go(index - 1); }
  });

  let resizeTimer;
  const relayout = () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { layout(); }, 100); };
  addEventListener("resize", relayout);
  document.fonts?.ready.then(() => { measure(); paint(index, { snap: true }); });

  layout();

  /** The page-load moment: the bob drops from the top of the string and swings onto its knot. */
  function drop(to) {
    index = Math.max(0, Math.min(stops.length - 1, to));
    if (!ys.length) { go(index); return; }
    bob.set(ys[0] - 40);
    paint(index, { move: false });
    onChange(stops[index], index);
    bob.to(ys[index], { velocity: 0, damping: 0.52, response: 0.9 });
  }

  return { go, drop, current: () => stops[index], stopPlaying, relayout: () => { measure(); paint(index, { snap: true }); } };
}
