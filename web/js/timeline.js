import { clock, esc } from "./format.js";

const GAP = 20 * 60; // seconds; a longer silence is broken out of the axis, as a drawing breaks a long dimension
const BREAK = 6; // percent of the axis given to a break
const MIN_DOMAIN = 14; // percent; a short stretch still gets room to read

const secs = (iso) => Date.parse(iso) / 1000;
const minutesBetween = (a, b) => Math.round((b - a) / 60);

/** Piecewise time scale: each burst of activity is linear in time, long gaps collapse to a break. */
function buildScale(stops) {
  const t = stops.map((s) => secs(s.at));
  const groups = [[t[0]]];
  for (let i = 1; i < t.length; i++) {
    if (t[i] - t[i - 1] > GAP) groups.push([]);
    groups.at(-1).push(t[i]);
  }
  const domains = groups.map((g) => ({
    start: Math.floor((Math.min(...g) - 45) / 60) * 60,
    end: Math.ceil((Math.max(...g) + 45) / 60) * 60,
  }));
  const usable = 100 - BREAK * (domains.length - 1);
  const total = domains.reduce((a, d) => a + (d.end - d.start), 0);
  let widths = domains.map((d) => Math.max(MIN_DOMAIN, (usable * (d.end - d.start)) / total));
  const sum = widths.reduce((a, b) => a + b, 0);
  widths = widths.map((w) => (w * usable) / sum);
  let x = 0;
  domains.forEach((d, i) => {
    d.x0 = x;
    d.w = widths[i];
    x += widths[i] + BREAK;
  });
  const pct = (time) => {
    const d = domains.find((q) => time >= q.start && time <= q.end);
    return d.x0 + ((time - d.start) / (d.end - d.start)) * d.w;
  };
  return { domains, pct };
}

export function createTimeline({ stops, onChange }) {
  const ruler = document.getElementById("ruler");
  const prev = document.getElementById("tl-prev");
  const next = document.getElementById("tl-next");
  const play = document.getElementById("tl-play");
  const nowLabel = document.getElementById("tl-label");
  const clockEl = document.getElementById("tl-clock");
  const scale = buildScale(stops);
  let index = 0;
  let timer = null;

  function layout() {
    const parts = ['<div class="axis"></div>'];
    scale.domains.forEach((d, di) => {
      for (let s = d.start; s <= d.end; s += 60) {
        const major = (s / 60) % 5 === 0;
        const x = d.x0 + ((s - d.start) / (d.end - d.start)) * d.w;
        parts.push(`<i class="tick ${major ? "major" : ""}" style="left:${x}%"></i>`);
        if (major) parts.push(`<span class="tick-label" style="left:${x}%">${new Date(s * 1000).toISOString().slice(11, 16)}</span>`);
      }
      const nxt = scale.domains[di + 1];
      if (nxt) {
        const x = d.x0 + d.w + BREAK / 2;
        parts.push(`<i class="brk" style="left:${x}%"></i><span class="brk-label" style="left:${x}%">${minutesBetween(d.end, nxt.start)} min later</span>`);
      }
    });
    stops.forEach((s) => {
      const kind = s.kind === "revision" ? "hypo" : s.kind;
      const text = `${clock(s.at)} UTC · ${s.label}${s.scripted ? " (hypothetical)" : ""}`;
      parts.push(`<button type="button" class="mk ${kind}" data-i="${s.index}" style="left:${scale.pct(secs(s.at))}%" title="${esc(text)}" aria-label="${esc(text)}"><i></i></button>`);
    });
    parts.push('<div class="playhead" id="playhead"><span id="ph-tag"></span></div>');
    ruler.innerHTML = parts.join("");
    paint();
  }

  function paint() {
    const stop = stops[index];
    ruler.querySelectorAll("[data-i]").forEach((el) => {
      const i = Number(el.dataset.i);
      el.classList.toggle("passed", i <= index);
      el.classList.toggle("current", i === index);
      el.setAttribute("aria-current", i === index ? "step" : "false");
    });
    const head = ruler.querySelector("#playhead");
    const pct = scale.pct(secs(stop.at));
    head.style.left = `${pct}%`;
    head.classList.toggle("edge-r", pct > 92); // keep the time tag inside the card
    head.querySelector("#ph-tag").textContent = clock(stop.at);
    clockEl.textContent = clock(stop.at);
    nowLabel.innerHTML = `${esc(stop.label)}${stop.scripted ? ' <span class="hypo">· hypothetical</span>' : ""}`;
    prev.disabled = index === 0;
    next.disabled = index === stops.length - 1;
  }

  function go(i, { announce = true } = {}) {
    index = Math.max(0, Math.min(stops.length - 1, i));
    paint();
    if (announce) onChange(stops[index], index);
  }

  function stopPlaying() {
    clearInterval(timer);
    timer = null;
    play.textContent = "Play";
    play.setAttribute("aria-label", "Play the incident");
  }

  function startPlaying() {
    if (index === stops.length - 1) go(0);
    play.textContent = "Pause";
    play.setAttribute("aria-label", "Pause");
    timer = setInterval(() => {
      if (index >= stops.length - 1) return stopPlaying();
      go(index + 1);
    }, 2200);
  }

  ruler.addEventListener("click", (e) => {
    const el = e.target.closest("[data-i]");
    if (el) {
      stopPlaying();
      go(Number(el.dataset.i));
    }
  });
  prev.addEventListener("click", () => { stopPlaying(); go(index - 1); });
  next.addEventListener("click", () => { stopPlaying(); go(index + 1); });
  play.addEventListener("click", () => (timer ? stopPlaying() : startPlaying()));
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "ArrowRight") { stopPlaying(); go(index + 1); }
    if (e.key === "ArrowLeft") { stopPlaying(); go(index - 1); }
  });
  let resizeTimer;
  window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(layout, 120); });

  layout();
  return { go, current: () => stops[index], stopPlaying };
}
