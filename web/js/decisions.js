import { VERDICT_WORD, approverLabel, attachClouds, clock, esc, factView, mark } from "./format.js";

export function renderDecisions(snap, sel, onSelect, revFor) {
  const root = document.getElementById("decisions");
  const sub = document.getElementById("dec-sub");
  const list = [...snap.decisions].sort((a, b) => (b.status === "reopened") - (a.status === "reopened") || a.created_ms - b.created_ms);
  sub.textContent = list.length ? `${list.length} recorded · ${snap.reopened.length} revised` : "";

  if (!list.length) {
    root.innerHTML = '<p class="empty" style="padding:24px 14px">No decisions recorded yet. Approvals appear on the timeline as open circles.</p>';
    return;
  }

  root.innerHTML = `<ol class="reglist">${list.map((d) => {
    const re = snap.reopened.find((r) => r.decision === d.decision);
    const selected = d.artifact === sel.artifact && d.advisory === sel.advisory;
    const broken = re ? factView(re.broken[0]).label : "";
    return `<li class="regitem ${d.status}" data-art="${esc(d.artifact)}" data-adv="${esc(d.advisory)}" tabindex="0" role="button"
        aria-selected="${selected}" aria-label="${esc(d.artifact)}, ${esc(d.status)}" ${re ? "data-cloud" : ""}>
      <span class="who">${esc(d.artifact)}</span>
      <span class="by">${esc(d.advisory)} · approved by ${esc(approverLabel(d.approver))} at ${esc(clock(d.created))}</span>
      <span class="shift">${mark(d.verdict)} ${esc(VERDICT_WORD[d.verdict])}
        ${re ? `<span class="arrow">→</span>${mark(re.now)} <span class="to">${esc(VERDICT_WORD[re.now])}</span>` : ""}</span>
      ${re ? `<span class="why">Assumption broken at ${esc(clock(re.broken_at))}: ${esc(broken)}.</span><span class="delta"><i></i>${esc(revFor(re.broken_at))}</span>` : ""}
    </li>`;
  }).join("")}</ol>
  <p class="reg-key">A revision cloud marks a decision that was reopened because one of its assumptions stopped being true.</p>`;

  attachClouds(root);
  const pick = (el) => { if (el?.dataset.art) onSelect(el.dataset.adv, el.dataset.art); };
  root.onclick = (e) => pick(e.target.closest("[data-art]"));
  root.onkeydown = (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const el = e.target.closest("[data-art]");
    if (el) { e.preventDefault(); pick(el); }
  };
}
