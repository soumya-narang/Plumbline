import { esc, plural } from "./format.js";

/** One-line summary of what a tool returned, so the trace reads at a glance. */
function summarise(call) {
  const r = call.result ?? {};
  if (call.error || r.error) return `error: ${r.error ?? call.error}`;
  switch (call.name) {
    case "list_advisories": return plural(r.advisories?.length ?? 0, "advisory").replace("advisorys", "advisories");
    case "triage_advisory": return `${r.counts?.EXPOSED ?? 0} exposed, ${r.counts?.UNKNOWN ?? 0} not determined, ${r.counts?.CLEARED ?? 0} cleared`;
    case "explain_path": return `${r.verdict}${r.hops != null ? `, ${plural(r.hops, "hop")}` : ""}`;
    case "reopen_check": return `${plural(r.decisions?.length ?? 0, "decision")} with a broken assumption`;
    case "propose_decision": return `${r.verdict} → ${r.proposed_action}, nothing written`;
    case "list_decisions": return plural(r.decisions?.length ?? 0, "decision");
    default: return "ok";
  }
}

const shortArgs = (args) =>
  Object.entries(args ?? {}).filter(([k]) => k !== "at").map(([, v]) => (typeof v === "string" ? v : JSON.stringify(v))).join(", ");

function resultHtml(run) {
  const calls = run.calls.map((c) => `<div class="call"><b>${esc(c.name)}</b>(${esc(shortArgs(c.args))}) → ${esc(summarise(c))}${c.ms != null ? ` <span class="ms">${c.ms} ms</span>` : ""}</div>`).join("");
  const who = run.backend === "llm"
    ? `Written by ${esc(run.model)}, which also chose the tools.`
    : "Written by the built-in planner. No model was involved.";
  return `<div class="trace" aria-label="Tool calls made over MCP">${calls}</div>
    <p class="answer">${esc(run.answer)}</p>
    <span class="answer-by">${who} Verdicts in the drawing come from the tool results, not from this sentence.</span>`;
}

export function createAgent({ suggestions, live, getStop, ask }) {
  const root = document.getElementById("agent");
  document.getElementById("agent-sub").textContent = live ? "tools over MCP" : "recorded answers";

  root.innerHTML = `<div class="desk-body">
    <div class="desk-left">
      <ul class="suggest">${suggestions.map((q, i) => `<li><button type="button" data-q="${i}">${esc(q)}</button></li>`).join("")}</ul>
      <form class="ask" id="ask-form">
        <input id="ask-input" maxlength="300" aria-label="Question for the agent" autocomplete="off"
          placeholder="${live ? "Ask about the fleet" : "Free text runs in the live deployment"}" ${live ? "" : "disabled"}>
        <button class="btn" ${live ? "" : "disabled"}>Ask</button>
      </form>
    </div>
    <div class="desk-right" id="agent-out" aria-live="polite"><p class="thinking">Choose a question. The agent works out which tools to call and shows each call here.</p></div>
  </div>`;
  const out = root.querySelector("#agent-out");
  const input = root.querySelector("#ask-input");

  async function run(question) {
    out.innerHTML = '<p class="thinking">Choosing tools over MCP…</p>';
    try {
      out.innerHTML = resultHtml(await ask(question, getStop()));
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
}
