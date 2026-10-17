import { esc } from "./format.js";

const COLUMNS = [["graph", "Graph (FalkorDB)"], ["sql", "SQL, tuned"], ["retrieval", "Text retrieval"]];
const ROWS = [
  ["locks", "Does A lock P@V?", "single hop"],
  ["pulled_by", "Which direct dependencies pull P@V in?", "multi hop"],
  ["fleet", "Which artifacts lock P@V?", "fleet wide"],
];

/** The ablation, graded against npm's own resolver. Shown with its caveats, because they are part of the result. */
export async function initBench() {
  let r;
  try {
    const res = await fetch("data/benchmark.json");
    if (!res.ok) return;
    r = await res.json();
  } catch {
    return;
  }
  const root = document.getElementById("bench");
  const total = Object.values(r.questions).reduce((a, b) => a + b, 0);
  document.getElementById("bench-lede").textContent =
    `${total} questions about ${r.artifacts_graded.length} real and planted lockfiles, answered three ways and graded against npm ls, npm's own resolver, which does not use this project's parser or graph.`;
  const head = `<thead><tr><th>Question</th>${COLUMNS.map(([, label]) => `<th>${esc(label)}</th>`).join("")}</tr></thead>`;
  const body = ROWS.map(([key, label, kind]) => {
    const cells = COLUMNS.map(([sys]) => {
      const x = r.results[sys][key];
      return `<td class="${x.accuracy === 1 ? "ok" : "miss"}"><b>${Math.round(x.accuracy * 100)}%</b><span>${x.correct}/${x.questions} correct · median ${x.p50_ms} ms</span></td>`;
    }).join("");
    return `<tr><th scope="row">${esc(label)}<span>${esc(kind)} · ${r.questions[key]} questions</span></th>${cells}</tr>`;
  }).join("");
  document.getElementById("bench-table").innerHTML = `${head}<tbody>${body}</tbody>`;
  // The same numbers as bars: one scale (0 to 100% correct) for every row, direct labels, bars anchored to the baseline.
  document.getElementById("bench-chart").innerHTML = ROWS.map(([key, label, kind]) => `
    <figure class="bar-group">
      <figcaption>${esc(label)}<span>${esc(kind)} · ${r.questions[key]} questions</span></figcaption>
      ${COLUMNS.map(([sys, name]) => {
        const x = r.results[sys][key];
        const pct = Math.round(x.accuracy * 100);
        return `<div class="bar-row ${sys}" title="${esc(name)}: ${x.correct} of ${x.questions} correct, median ${x.p50_ms} ms">
          <span class="bar-name">${esc(name)}</span>
          <span class="bar-track"><i class="bar-fill" style="width:${pct}%"></i></span>
          <span class="bar-val"><b>${pct}%</b><span>${x.correct}/${x.questions}, ${x.p50_ms} ms</span></span></div>`;
      }).join("")}
    </figure>`).join("");
  document.getElementById("bench-note").textContent =
    "A tuned SQL query gets the same answers and is faster on lookups at this size, because SQLite runs inside the process. " +
    "Retrieval alone cannot follow a dependency chain. So the graph's case here is not speed: it is evidence that carries its path, " +
    "memory that knows what it assumed, algorithms such as PageRank, and one store that several agents can share. " +
    `Median of ${r.repeats_per_question} runs on one machine. ${Object.keys(r.artifacts_skipped).length} artifacts the oracle cannot read were left out of grading.`;
  root.hidden = false;
}
