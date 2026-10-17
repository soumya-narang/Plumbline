// The graph tab's map: the selected service's whole dependency graph, depth running downward like a plumb line, with the
// poisoned path pinned to the centre line and lit.
import { api } from "./api.js";
import { createGraphView } from "./graphview.js";
import { esc } from "./format.js";

const EMPTY = { nodes: [], edges: [] };

export function createMap() {
  const host = document.getElementById("map");
  const canvas = host.querySelector("canvas");
  const caption = document.getElementById("map-caption");
  const veil = document.getElementById("map-veil");
  const cache = new Map();
  let shown = ""; // artifact currently on the canvas
  let sig = ""; // artifact + path: what is lit
  let token = 0;

  const view = createGraphView(canvas, { interactive: true, labels: true, anchor: () => 0.5, padTop: 64 });

  async function graphFor(artifact) {
    if (!cache.has(artifact)) cache.set(artifact, await api.getGraph(artifact));
    return cache.get(artifact);
  }

  function say(html, { hatch = false } = {}) {
    veil.hidden = !hatch;
    if (hatch) veil.innerHTML = html;
  }

  /** Called on every render; only does work when the artifact or the lit path actually changed. */
  async function show(snap, sel) {
    const adv = snap.advisories.find((a) => a.id === sel.advisory);
    const row = adv?.rows.find((r) => r.artifact === sel.artifact);
    if (!row) {
      shown = sig = "";
      view.setData(EMPTY);
      say("");
      caption.innerHTML = '<span>Choose a service to see everything it depends on.</span>';
      return;
    }
    const keys = row.verdict === "EXPOSED" && row.path_keys ? row.path_keys : [];
    const next = `${row.artifact}|${keys.join(">")}`;
    if (next === sig) return;
    const mine = ++token;
    let data;
    try {
      data = await graphFor(row.artifact);
    } catch {
      if (mine !== token) return;
      shown = ""; sig = next;
      view.setData(EMPTY);
      caption.innerHTML = `<b>${esc(row.artifact)}</b><span>Nothing to draw</span>`;
      say(row.verdict === "UNKNOWN"
        ? `<strong>Not surveyed.</strong> ${esc(row.artifact)} has no lockfile this build can read, so there is no graph to trace and no answer to give.`
        : `<strong>No graph.</strong> A dependency graph isn't available for ${esc(row.artifact)}.`, { hatch: true });
      return;
    }
    if (mine !== token) return;
    say("");
    if (shown !== row.artifact) { view.setData(data); shown = row.artifact; }
    view.setPath(keys, { animate: true });
    sig = next;
    caption.innerHTML = `<b>${esc(row.artifact)}</b><span>${data.nodes.length.toLocaleString()} packages, ${data.edges.length.toLocaleString()} dependencies</span>` +
      `<span class="tip">${keys.length ? "Hover a package to trace what it requires and what requires it." : "Hover a package to trace it. Nothing here reaches an affected version."}</span>`;
  }

  // the headline wraps differently once the web font arrives, which moves where the graph may begin
  document.fonts?.ready.then(() => view.resize());
  // the graph view already re-lays itself out when the map resizes; recolour when the theme flips
  const redraw = () => view.resize();
  addEventListener("themechange", redraw);

  /** How many packages a service's graph holds; 0 when it has none to draw. Used to pick the richest map to open on. */
  async function size(artifact) {
    try { return (await graphFor(artifact)).nodes.length; } catch { return 0; }
  }

  return { show, redraw, size };
}
