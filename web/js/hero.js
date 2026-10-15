import { api } from "./api.js";
import { createGraphView, findNode, pathTo } from "./graphview.js";

/** The hero's backdrop: the storefront's real dependency tree with the poisoned path lit and a bob dropping along it. */
export async function initHero() {
  const canvas = document.getElementById("hero-graph");
  const view = createGraphView(canvas, { interactive: false, labels: true, loop: true, inset: () => (window.innerWidth > 1000 ? 0.34 : 0), anchor: () => 0.58, padTop: 132 });
  try {
    const data = await api.getGraph("planted/storefront");
    view.setData(data);
    const bad = findNode(data, "keyv", "6.0.0");
    if (bad >= 0) view.setPath(pathTo(data, bad));
  } catch {
    /* the hero still reads without its backdrop */
  }
  return view;
}
