import { esc, plural } from "./format.js";

/** One-line summary of what a tool returned, so the trace reads at a glance. */
function summarise(call) {
  const r = call.result ?? {};
  if (call.error || r.error) return `error: ${r.error ?? call.error}`;
  switch (call.name) {
    case "list_advisories": return plural(r.advisories?.length ?? 0, "advisory").replace("advisorys", "advisories");
    case "triage_advisory": return `${r.counts?.EXPOSED ?? 0} exposed · ${r.counts?.UNKNOWN ?? 0} unknown · ${r.counts?.CLEARED ?? 0} cleared`;
    case "explain_path": return `${r.verdict}${r.hops != null ? ` · ${plural(r.hops, "hop")}` : ""}`;
    case "reopen_check": return `${plural(r.decisions?.length ?? 0, "decision")} with a broken assumption`;
    case "propose_decision": return `${r.verdict} → ${r.proposed_action} · nothing written`;
    case "list_decisions": return plural(r.decisions?.length ?? 0, "decision");
    default: return "ok";
  }
}

const shortArgs = (args) =>
  Object.entries(args ?? {}).filter(([k]) => k !== "at").map(([, v]) => (typeof v === "string" ? v : JSON.stringify(v))).join(", ");

function traceHtml(run) {
  const calls = run.calls.map((c) => `<div class="call"><b>${esc(c.name)}</b>(${esc(shortArgs(c.args))}) → ${esc(summarise(c))} ${c.ms != null ? `<span class="ms">${c.ms} ms</span>` : ""}</div>`).join("");
  const who = run.backend === "llm" ? `Model: ${esc(run.model)} · chose the tools and wrote the sentence` : "Built-in planner · no model · deterministic";
  return `<div class="trace" aria-label="Tool calls over MCP">${calls}</div>
    <div class="answer">${esc(run.answer)}<span class="by">${who}. Verdicts above are drawn from tool results, not from this text.</span></div>`;
}

export function createAgent({ suggestions, live, getStop, ask }) {
  const root = document.getElementById("agent");
  const sub = document.getElementById("agent-sub");
  sub.textContent = live ? "tools over MCP" : "recorded answers";

  root.innerHTML = `<div class="suggest">${suggestions.map((q, i) => `<button type="button" data-q="${i}">${esc(q)}</button>`).join("")}</div>
    <form class="ask" id="ask-form"><input id="ask-input" maxlength="300" placeholder="${live ? "Ask about the fleet…" : "Free text runs in the live deployment"}"
      aria-label="Question for the agent" ${live ? "" : "disabled"}><button class="btn primary" ${live ? "" : "disabled"}>Ask</button></form>
    <div id="agent-out" aria-live="polite"></div>`;
  const out = root.querySelector("#agent-out");
  const input = root.querySelector("#ask-input");

  async function run(question) {
    out.innerHTML = '<p class="thinking">Choosing tools over MCP…</p>';
    try {
      out.innerHTML = traceHtml(await ask(question, getStop()));
    } catch (err) {
      out.innerHTML = `<p class="thinking">${esc(err.message)}</p>`;
    }
  }

  root.querySelector(".suggest").addEventListener("click", (e) => {
    const b = e.target.closest("[data-q]");
    if (!b) return;
    input.value = suggestions[Number(b.dataset.q)];
    run(input.value);
  });
  root.querySelector("#ask-form").addEventListener("submit", (e) => {
    e.preventDefault();
    if (input.value.trim()) run(input.value.trim());
  });
  return { clear: () => (out.innerHTML = "") };
}
