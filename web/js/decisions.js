import { PIN, approverLabel, esc, factView } from "./format.js";

function pins(ids, brokenIds) {
  return `<div class="pins">${ids
    .map((id) => {
      const f = factView(id);
      return `<span class="pill ${brokenIds.has(id) ? "broken" : ""}" title="${esc(f.why)}">${PIN}${esc(f.label)}</span>`;
    })
    .join("")}</div>`;
}

export function renderDecisions(snap, sel, onSelect) {
  const root = document.getElementById("decisions");
  const sub = document.getElementById("dec-sub");
  const list = [...snap.decisions].sort((a, b) => (b.status === "reopened") - (a.status === "reopened") || a.created_ms - b.created_ms);
  sub.textContent = list.length ? `${list.length} recorded · ${snap.reopened.length} reopened` : "";

  if (!list.length) {
    root.innerHTML = '<p class="empty">No decisions yet. Approvals appear on the timeline.</p>';
    return;
  }
  root.innerHTML = list
    .map((d) => {
      const re = snap.reopened.find((r) => r.decision === d.decision);
      const broken = new Set(re?.broken ?? []);
      const selected = d.artifact === sel.artifact && d.advisory === sel.advisory;
      return `<article class="dec ${d.status}" data-art="${esc(d.artifact)}" data-adv="${esc(d.advisory)}" tabindex="0"
          role="button" aria-label="${esc(d.artifact)}, ${esc(d.status)}" ${selected ? 'style="outline:1px solid var(--accent)"' : ""}>
        <div class="dec-top"><b>${esc(d.artifact)}</b><span class="status">${esc(d.status)}</span></div>
        <div class="dec-sub">${esc(d.advisory)} · approved by ${esc(approverLabel(d.approver))} at ${esc(d.created.slice(11, 19))} UTC</div>
        <div class="shift"><span class="mini ${d.verdict}">${d.verdict}</span>
          ${re ? `<span class="arrow">→</span><span class="mini ${re.now}">${re.now}</span><span class="muted">after ${esc(re.broken_at.slice(11, 19))} UTC</span>` : ""}</div>
        ${pins(d.assumption_ids, broken)}
      </article>`;
    })
    .join("");

  root.onclick = (e) => { const el = e.target.closest("[data-art]"); if (el) onSelect(el.dataset.adv, el.dataset.art); };
  root.onkeydown = (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const el = e.target.closest("[data-art]");
    if (el) { e.preventDefault(); onSelect(el.dataset.adv, el.dataset.art); }
  };
}
