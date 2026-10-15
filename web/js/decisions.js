import { VERDICT_WORD, approverLabel, clock, esc, factView, mark } from "./format.js";

export function renderDecisions(snap, sel, onSelect) {
  const root = document.getElementById("decisions");
  const count = document.getElementById("dec-count");
  const list = [...snap.decisions].sort((a, b) => (b.status === "reopened") - (a.status === "reopened") || a.created_ms - b.created_ms);

  count.textContent = list.length ? String(list.length) : "";
  count.classList.toggle("change", snap.reopened.length > 0);
  count.hidden = list.length === 0;

  if (!list.length) {
    root.innerHTML = '<p class="empty" style="padding:8px 0">No decisions recorded yet. Approvals appear on the timeline as open circles.</p>';
    return;
  }

  root.innerHTML = `<ul class="dlist">${list.map((d) => {
    const re = snap.reopened.find((r) => r.decision === d.decision);
    const selected = d.artifact === sel.artifact && d.advisory === sel.advisory;
    return `<li class="ditem ${d.status}" data-art="${esc(d.artifact)}" data-adv="${esc(d.advisory)}" tabindex="0" role="button"
        aria-current="${selected}" aria-label="${esc(d.artifact)}, ${esc(d.status)}">
      ${re ? '<span class="badge">Reopened</span>' : ""}
      <span class="who">${esc(d.artifact)}</span>
      <span class="by">${esc(d.advisory)} · approved by ${esc(approverLabel(d.approver))} at ${esc(clock(d.created))} UTC</span>
      <span class="shift">${mark(d.verdict)} ${esc(VERDICT_WORD[d.verdict])}${re ? ` <span class="muted">→</span> ${mark(re.now)} <span class="to">${esc(VERDICT_WORD[re.now])}</span>` : ""}</span>
      ${re ? `<span class="why">${esc(factView(re.broken[0]).label)}. No longer true since ${esc(clock(re.broken_at))} UTC.</span>` : ""}
    </li>`;
  }).join("")}</ul>
  <p class="dnote">A decision reopens only when a fact it assumed stops being true.</p>`;

  const pick = (el) => { if (el?.dataset.art) onSelect(el.dataset.adv, el.dataset.art); };
  root.onclick = (e) => pick(e.target.closest("[data-art]"));
  root.onkeydown = (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const el = e.target.closest("[data-art]");
    if (el) { e.preventDefault(); pick(el); }
  };
}
