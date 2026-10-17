import { esc, highlightCypher } from "./format.js";

const SNIPPETS = [
  ["q2", "Evidence path", "Q2 finds the shortest chain from a service's direct dependency to the poisoned version. This engine only allows shortestPath in WITH or RETURN."],
  ["q5", "Reopen", "Q5 is the whole truth-maintenance step: which accepted decisions rest on a fact that has since been superseded."],
  ["q6", "Fix first", "Q6 runs across the entire fleet and ranks the direct dependencies to upgrade by how many artifacts they expose."],
  ["q7", "PageRank", "Q7 ranks one artifact's packages by PageRank over the REQUIRES graph, using FalkorDB's built-in algorithm."],
];

export function initHood(meta) {
  const tabs = document.getElementById("code-tabs");
  const view = document.getElementById("code-view");
  const hint = document.getElementById("code-hint");
  const facts = document.getElementById("facts");
  const available = SNIPPETS.filter(([k]) => meta.queries?.[k]);

  function show(i) {
    const [key, , note] = available[i];
    view.innerHTML = highlightCypher(meta.queries[key]);
    hint.textContent = note;
    tabs.querySelectorAll("button").forEach((b, j) => b.setAttribute("aria-selected", String(j === i)));
  }
  tabs.innerHTML = available.map(([, label], i) => `<button type="button" role="tab" data-i="${i}" aria-selected="false">${esc(label)}</button>`).join("");
  tabs.onclick = (e) => { const b = e.target.closest("[data-i]"); if (b) show(Number(b.dataset.i)); };
  if (available.length) show(0);

  const s = meta.stats;
  if (s) {
    const n = (v) => `<b>${Number(v).toLocaleString()}</b>`;
    facts.innerHTML = `The demo graph holds ${n(s.dependencies)} packages and ${n(s.edges)} dependency edges across ${n(s.artifacts)} repositories. Four of them are planted and labelled as such.`;
  }
}
