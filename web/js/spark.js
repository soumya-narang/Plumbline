// A small step line: how many distinct services are exposed at each moment of the incident, with the current moment marked.
// One series, so no legend box: the caption names it. The line is a step because exposure changes at events, not between them.
import { getSnapshot } from "./api.js";
import { clock } from "./format.js";

const W = 222;
const H = 46;
const PAD = { l: 2, r: 8, t: 8, b: 6 };

export function createSpark(root, stops) {
  let counts = null;
  let at = 0;

  const exposed = (snap) => new Set(snap.advisories.flatMap((a) => a.rows.filter((r) => r.verdict === "EXPOSED").map((r) => r.artifact))).size;

  async function load() {
    try {
      counts = await Promise.all(stops.map(async (s) => exposed(await getSnapshot(s))));
      draw();
    } catch { root.hidden = true; }
  }

  function draw() {
    if (!counts) return;
    const max = Math.max(1, ...counts);
    const x = (i) => PAD.l + (i / (stops.length - 1)) * (W - PAD.l - PAD.r);
    const y = (v) => PAD.t + (1 - v / max) * (H - PAD.t - PAD.b);
    const step = counts.map((v, i) => `${i ? "H" : "M"}${x(i).toFixed(1)}${i ? "" : ` ${y(v).toFixed(1)}`}${i ? ` V${y(v).toFixed(1)}` : ""}`).join(" ");
    const area = `${step} V${H - PAD.b} H${x(0).toFixed(1)} Z`;
    const hits = stops.map((s, i) => `<rect x="${(x(i) - W / stops.length / 2).toFixed(1)}" y="0" width="${(W / stops.length).toFixed(1)}" height="${H}" fill="transparent"><title>${clock(s.at)} UTC: ${counts[i]} exposed</title></rect>`).join("");
    root.innerHTML = `<div class="spark-head"><span>Exposed, all advisories</span><b id="spark-now">${counts[at]}</b></div>
      <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Exposed services over the incident, from ${counts[0]} to ${counts.at(-1)}, peaking at ${max}">
        <line class="base" x1="${PAD.l}" x2="${W - PAD.r}" y1="${H - PAD.b}" y2="${H - PAD.b}"/>
        <path class="area" d="${area}"/><path class="line" d="${step}"/>
        <line class="now" id="spark-line" y1="${PAD.t - 2}" y2="${H - PAD.b}"/><circle class="dot" id="spark-dot" r="4"/>${hits}
      </svg>`;
    move();
  }

  function move() {
    if (!counts) return;
    const max = Math.max(1, ...counts);
    const cx = PAD.l + (at / (stops.length - 1)) * (W - PAD.l - PAD.r);
    const cy = PAD.t + (1 - counts[at] / max) * (H - PAD.t - PAD.b);
    const line = root.querySelector("#spark-line");
    const dot = root.querySelector("#spark-dot");
    line?.setAttribute("x1", cx); line?.setAttribute("x2", cx);
    dot?.setAttribute("cx", cx); dot?.setAttribute("cy", cy);
    const n = root.querySelector("#spark-now");
    if (n) n.textContent = counts[at];
  }

  load();
  return { update(i) { at = i; move(); } };
}
