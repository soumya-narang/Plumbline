import { api } from "./api.js";
import { createGraphView } from "./graphview.js";
import { esc } from "./format.js";

let view = null;
let token = 0;
const cache = new Map();

async function graphFor(artifact) {
  if (!cache.has(artifact)) cache.set(artifact, await api.getGraph(artifact));
  return cache.get(artifact);
}

/** The Graph tab: the whole dependency tree of the selected artifact, with the poisoned path lit. */
export async function renderGraphTab(snap, sel) {
  const body = document.getElementById("graph-body");
  const adv = snap.advisories.find((a) => a.id === sel.advisory);
  const row = adv?.rows.find((r) => r.artifact === sel.artifact);
  if (!row) {
    view?.destroy();
    view = null;
    body.innerHTML = '<p class="empty">Choose an artifact to see its dependency graph.</p>';
    return;
  }
  const mine = ++token;
  view?.destroy();
  view = null;
  body.innerHTML = `<div class="g-head"><h3>${esc(row.artifact)}</h3><p class="muted" id="g-meta">Loading the graph…</p></div>
    <div class="gv-host"><canvas aria-label="Dependency graph of ${esc(row.artifact)}"></canvas></div>
    <p class="hint" id="g-hint"></p>`;
  let data;
  try {
    data = await graphFor(row.artifact);
  } catch {
    if (mine !== token) return;
    body.innerHTML = `<div class="g-head"><h3>${esc(row.artifact)}</h3></div>
      <p class="empty" style="padding:8px 0">${row.verdict === "UNKNOWN" ? "There is no dependency graph to draw: this artifact has no lockfile this build can read, which is why its verdict is not determined." : "No dependency graph is available for this artifact."}</p>`;
    return;
  }
  if (mine !== token) return;
  body.querySelector("#g-meta").textContent = `${data.nodes.length.toLocaleString()} packages, ${data.edges.length.toLocaleString()} dependency edges`;
  body.querySelector("#g-hint").textContent = row.verdict === "EXPOSED"
    ? "The poisoned path is lit. Hover any package to trace what it requires and what requires it."
    : "Hover any package to trace what it requires and what requires it. Nothing here reaches an affected version.";
  view = createGraphView(body.querySelector("canvas"), { interactive: true, labels: true });
  view.setData(data);
  if (row.verdict === "EXPOSED" && row.path_keys) view.setPath(row.path_keys);
}
