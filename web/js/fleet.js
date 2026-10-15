import { VERDICT_RANK, esc, plural, purlLabel } from "./format.js";

const GROUPS = [
  ["EXPOSED", "Exposed"],
  ["UNKNOWN", "Unknown · refusing to guess"],
  ["CLEARED", "Cleared · relative to stated assumptions"],
];

export const rowKey = (advisory, artifact) => `${advisory}|${artifact}`;

function advisoryChip(adv, selected) {
  const first = purlLabel(adv.affected_purls[0] ?? adv.package);
  const more = adv.affected_purls.length > 1 ? ` +${adv.affected_purls.length - 1}` : "";
  return `<button type="button" role="tab" class="chip ${adv.counts.EXPOSED ? "hot" : ""}" aria-selected="${selected}"
      data-adv="${esc(adv.id)}" title="${esc(adv.id)}">${esc(first)}${more}</button>`;
}

function rowHtml(adv, row, selected, flash) {
  const decided = row.decision ? `<span class="tag ${row.decision.status === "reopened" ? "net" : ""}">${esc(row.decision.status)}</span>` : "";
  return `<button type="button" class="row ${row.verdict} ${flash ? "flash" : ""}" aria-pressed="${selected}"
      data-art="${esc(row.artifact)}">
      <span class="bar"></span>
      <span><span class="name">${esc(row.artifact)}</span>
        <span class="meta">
          <span>${esc(row.service ?? "")}</span>
          ${row.exposure === "internet" ? '<span class="tag net">internet</span>' : '<span class="tag">internal</span>'}
          ${row.synthetic ? '<span class="tag planted">planted</span>' : ""}${decided}
        </span></span>
      <span class="mini ${row.verdict}">${row.verdict}</span>
    </button>`;
}

export function renderFleet(snap, sel, changed, { onAdvisory, onArtifact }) {
  const tabs = document.getElementById("adv-tabs");
  const counts = document.getElementById("counts");
  const list = document.getElementById("fleet-list");
  const sub = document.getElementById("fleet-sub");

  if (!snap.advisories.length) {
    tabs.innerHTML = "";
    counts.innerHTML = "";
    list.innerHTML = '<p class="empty">No advisory has been published yet.<br>Step forward to the first malicious release.</p>';
    return;
  }

  sub.textContent = `${snap.advisories[0].rows.length} artifacts · declared deployment`;
  tabs.innerHTML = snap.advisories.map((a) => advisoryChip(a, a.id === sel.advisory)).join("");
  const adv = snap.advisories.find((a) => a.id === sel.advisory) ?? snap.advisories[0];
  const c = adv.counts;
  const total = c.EXPOSED + c.UNKNOWN + c.CLEARED || 1;
  counts.innerHTML = `
    <div class="counts" role="img" aria-label="${plural(c.EXPOSED, "exposed artifact")}, ${c.UNKNOWN} unknown, ${c.CLEARED} cleared">
      <i class="e" style="flex-grow:${c.EXPOSED / total}"></i><i class="u" style="flex-grow:${c.UNKNOWN / total}"></i><i class="c" style="flex-grow:${c.CLEARED / total}"></i>
    </div>
    <div class="count-legend"><span><b>${c.EXPOSED}</b> exposed</span><span><b>${c.UNKNOWN}</b> unknown</span><span><b>${c.CLEARED}</b> cleared</span></div>`;

  const rows = [...adv.rows].sort((a, b) => VERDICT_RANK[a.verdict] - VERDICT_RANK[b.verdict]);
  list.innerHTML = GROUPS.map(([verdict, title]) => {
    const group = rows.filter((r) => r.verdict === verdict);
    if (!group.length) return "";
    return `<div class="group-title">${title} (${group.length})</div>` +
      group.map((r) => rowHtml(adv, r, r.artifact === sel.artifact, changed.has(rowKey(adv.id, r.artifact)))).join("");
  }).join("");

  tabs.onclick = (e) => { const b = e.target.closest("[data-adv]"); if (b) onAdvisory(b.dataset.adv); };
  list.onclick = (e) => { const b = e.target.closest("[data-art]"); if (b) onArtifact(b.dataset.art); };
}
