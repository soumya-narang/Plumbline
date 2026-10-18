// The memory graph: decisions on the left, the facts they assumed on the right, one ASSUMES edge for each.
// A fact that stopped being true turns red, and so does every decision hanging from it. That is the whole "reopen" query, drawn.
import { VERDICT_WORD, clock, esc, factView } from "./format.js";

const ROW = 40;
const PAD = 22;
const LEFT = 16;
const RIGHT_X = 0.44; // fraction of the width where the fact column starts

const short = (artifact) => artifact.replace(/^planted\//, "");
const factKind = (id) => (id.startsWith("lock_snapshot") ? "lock" : "advisory");
const factText = (id) => {
  const f = factView(id);
  return id.startsWith("lock_snapshot") ? "lockfile unchanged" : f.label.replace(" is not named by ", " not named by ");
};
const clip = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/**
 * decisions: snapshot decisions; brokenAt: Map(factId -> iso time); focus: optional decision id to draw alone.
 * Returns an SVG string. Nodes carry data-art/data-adv so a click can select the service.
 */
export function memorySvg(decisions, brokenAt, { focus = null, selected = null, width = 520 } = {}) {
  const ds = focus ? decisions.filter((d) => d.decision === focus) : decisions;
  if (!ds.length) return "";
  const facts = [];
  for (const d of ds) for (const id of d.assumption_ids) if (!facts.includes(id)) facts.push(id);
  // lockfile facts sit with their own decision; advisory facts are shared and go below, so shared edges stay readable
  facts.sort((a, b) => (factKind(a) === factKind(b) ? 0 : factKind(a) === "lock" ? -1 : 1));
  const rows = Math.max(ds.length, facts.length);
  const H = PAD * 2 + rows * ROW;
  const dy = (i, n) => PAD + (H - PAD * 2) * ((i + 0.5) / n);
  const fx = Math.round(width * RIGHT_X);
  const dx = LEFT;
  const nodeW = Math.round(width * 0.32);
  const factW = width - fx - LEFT;

  const brokenSet = new Set(brokenAt.keys());
  const dpos = new Map(ds.map((d, i) => [d.decision, dy(i, ds.length)]));
  const fpos = new Map(facts.map((id, i) => [id, dy(i, facts.length)]));
  const reopened = (d) => d.assumption_ids.some((id) => brokenSet.has(id));

  const edges = ds.flatMap((d) => d.assumption_ids.map((id) => {
    const y1 = dpos.get(d.decision);
    const y2 = fpos.get(id);
    const x1 = dx + nodeW;
    const bad = brokenSet.has(id);
    const mid = (x1 + fx) / 2;
    return `<path class="m-edge${bad ? " bad" : ""}" d="M${x1} ${y1} C${mid} ${y1} ${mid} ${y2} ${fx} ${y2}"/>`;
  }));

  const dnodes = ds.map((d) => {
    const y = dpos.get(d.decision);
    const re = reopened(d);
    const sel = selected && d.artifact === selected;
    return `<g class="m-node m-dec${re ? " bad" : ""}${sel ? " sel" : ""}" data-art="${esc(d.artifact)}" data-adv="${esc(d.advisory)}" tabindex="0" role="button"
        aria-label="Decision on ${esc(d.artifact)}, ${esc(VERDICT_WORD[d.verdict])}${re ? ", reopened" : ""}">
      <rect x="${dx}" y="${y - 15}" width="${nodeW}" height="30" rx="10"/>
      <text x="${dx + 12}" y="${y + 4}">${esc(clip(short(d.artifact), 24))}</text>
      ${re ? `<circle class="m-pulse" cx="${dx + nodeW - 12}" cy="${y}" r="4"/>` : ""}
    </g>`;
  });

  const fnodes = facts.map((id) => {
    const y = fpos.get(id);
    const bad = brokenSet.has(id);
    const share = ds.filter((d) => d.assumption_ids.includes(id)).length;
    return `<g class="m-node m-fact ${factKind(id)}${bad ? " bad" : ""}" role="img" aria-label="Fact: ${esc(factView(id).label)}${bad ? ", no longer true" : ""}">
      <title>${esc(factView(id).label)}${bad ? ` (no longer true since ${esc(clock(brokenAt.get(id)))} UTC)` : ""}</title>
      <rect x="${fx}" y="${y - 15}" width="${factW}" height="30" rx="15"/>
      <text x="${fx + 14}" y="${y + 4}">${esc(clip(factText(id), Math.floor(factW / 6.4)))}</text>
      ${share > 1 ? `<text class="m-share" x="${fx + factW - 12}" y="${y + 4}" text-anchor="end">×${share}</text>` : ""}
    </g>`;
  });

  return `<svg class="memory-svg" viewBox="0 0 ${width} ${H}" role="group" aria-label="Memory graph: ${ds.length} decision${ds.length === 1 ? "" : "s"} and the ${facts.length} fact${facts.length === 1 ? "" : "s"} they assumed">
    <g class="m-edges">${edges.join("")}</g>${dnodes.join("")}${fnodes.join("")}</svg>`;
}

/** Facts that stopped being true in this snapshot, as Map(factId -> iso time). */
export function brokenFacts(snap) {
  const out = new Map();
  for (const r of snap.reopened) for (const id of r.broken) out.set(id, r.broken_at);
  return out;
}

const legend = (broke) => `<p class="m-legend"><code>(Decision)-[:ASSUMES]-&gt;(Fact)</code>
  <span><i class="k dec"></i>decision</span><span><i class="k fact"></i>fact it assumed</span>${broke ? '<span><i class="k bad"></i>no longer true</span>' : ""}</p>`;

export function renderMemory(snap, sel, onSelect) {
  const root = document.getElementById("memory");
  if (!root) return;
  if (!snap.decisions.length) { root.innerHTML = ""; return; }
  const broken = brokenFacts(snap);
  const n = snap.reopened.length;
  root.innerHTML = `<div class="memory ${n ? "has-bad" : ""}">
    <h4 class="wq-head">What the agent remembers</h4>
    <p class="m-sentence" aria-live="polite">${n
      ? `A fact stopped being true. <b>${n} decision${n === 1 ? "" : "s"} reopened</b>; the other ${snap.decisions.length - n} stayed decided.`
      : `Each decision is stored with the facts it assumed. If one stops being true, only the decisions hanging from it reopen.`}</p>
    ${memorySvg(snap.decisions, broken, { selected: sel.artifact })}${legend(n > 0)}</div>`;
  const pick = (el) => { if (el?.dataset.art) onSelect(el.dataset.adv, el.dataset.art); };
  root.onclick = (e) => pick(e.target.closest("[data-art]"));
  root.onkeydown = (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const el = e.target.closest("[data-art]");
    if (el) { e.preventDefault(); pick(el); }
  };
}
