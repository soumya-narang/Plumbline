// The work queue under the Decisions tab: fixes one agent has handed to another. Live deployment only, because the
// queue is written by agents through the graph and the recorded site has no graph to read it from.
import { esc } from "./format.js";
import { isLive } from "./api.js";

const root = document.getElementById("work-queue");

const WORD = { open: "waiting", claimed: "in progress", done: "done" };

function row(t) {
  const who = t.status === "open" ? `handed over by ${esc(t.created_by)}`
    : t.status === "claimed" ? `${esc(t.claimed_by)} is working on it`
      : `${esc(t.claimed_by)}: ${esc(t.resolution ?? "")}`;
  return `<li class="witem ${t.status}"><span class="wtag">${WORD[t.status]}</span>
    <span class="who">${esc(t.artifact)}</span>
    <span class="by">Bump ${esc(t.fix)} · ${who}</span></li>`;
}

export async function refreshWork() {
  if (!root || !isLive()) return;
  try {
    const res = await fetch("api/tasks");
    if (!res.ok) return;
    const { tasks } = await res.json();
    root.innerHTML = tasks.length
      ? `<h4 class="wq-head">Work queue</h4>
         <p class="dnote">Fixes the triage agent has handed to remediation agents.</p>
         <ul class="wlist">${tasks.map(row).join("")}</ul>`
      : `<h4 class="wq-head">Work queue</h4><p class="dnote">Empty. Ask the agent to "hand off the fixes for keyv" and the exposed services appear here as tasks.</p>`;
  } catch { /* the queue is a nicety; the rest of the page does not depend on it */ }
}

addEventListener("agent-answered", refreshWork);
