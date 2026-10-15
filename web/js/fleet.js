import { VERDICT_RANK, esc, mark, purlLabel } from "./format.js";

export const rowKey = (advisory, artifact) => `${advisory}|${artifact}`;

const GROUPS = [
  ["EXPOSED", "Exposed"],
  ["UNKNOWN", "Not determined"],
  ["CLEARED", "Cleared"],
];

let showCleared = false;

function advisoryLabel(adv) {
  const first = purlLabel(adv.affected_purls[0] ?? adv.package).replace(/^@[^/]+\//, "");
  return first + (adv.affected_purls.length > 1 ? ` +${adv.affected_purls.length - 1}` : "");
}

function rowHtml(row, selected, flash) {
  const tags = (row.synthetic ? '<span class="tag">planted</span>' : "") +
    (row.decision?.status === "reopened" ? '<span class="tag change">reopened</span>' : "");
  return `<li><button type="button" class="row ${flash ? "flash" : ""}" data-art="${esc(row.artifact)}" aria-current="${selected}">
    ${mark(row.verdict)}
    <span><span class="name">${esc(row.artifact)}</span>
      <span class="sub">${esc(row.service ?? "")} · ${row.exposure === "internet" ? "internet-facing" : "internal"}${tags}</span></span></button></li>`;
}

export function renderFleet(snap, sel, changed, { onAdvisory, onArtifact }) {
  const select = document.getElementById("adv-select");
  const counts = document.getElementById("counts");
  const list = document.getElementById("fleet-list");

  if (!snap.advisories.length) {
    select.innerHTML = '<option>No release yet</option>';
    select.disabled = true;
    counts.innerHTML = "";
    list.innerHTML = '<p class="empty">No malicious release has been published yet.<br>Step forward to 11:12:20.</p>';
    return;
  }
  select.disabled = false;
  select.innerHTML = snap.advisories
    .map((a) => `<option value="${esc(a.id)}" ${a.id === sel.advisory ? "selected" : ""}>${esc(advisoryLabel(a))}</option>`)
    .join("");
  select.title = sel.advisory ?? "";

  const adv = snap.advisories.find((a) => a.id === sel.advisory) ?? snap.advisories[0];
  const c = adv.counts;
  counts.innerHTML = `<span class="exposed">${mark("EXPOSED")}<b>${c.EXPOSED}</b> exposed</span>
    <span>${mark("UNKNOWN")}<b>${c.UNKNOWN}</b> not determined</span><span>${mark("CLEARED")}<b>${c.CLEARED}</b> cleared</span>`;

  if (adv.rows.find((r) => r.artifact === sel.artifact)?.verdict === "CLEARED") showCleared = true;

  const rows = [...adv.rows].sort((a, b) => VERDICT_RANK[a.verdict] - VERDICT_RANK[b.verdict] || a.artifact.localeCompare(b.artifact));
  list.innerHTML = GROUPS.map(([verdict, title]) => {
    const group = rows.filter((r) => r.verdict === verdict);
    if (!group.length) return "";
    const collapsible = verdict === "CLEARED";
    const open = !collapsible || showCleared;
    const head = collapsible
      ? `<button type="button" class="group-head" id="cleared-toggle" aria-expanded="${open}">${open ? "▾" : "▸"} ${title} (${group.length})</button>`
      : `<h3 class="group-head">${title} (${group.length})</h3>`;
    const items = open
      ? `<ul class="rows">${group.map((r) => rowHtml(r, r.artifact === sel.artifact, changed.has(rowKey(adv.id, r.artifact)))).join("")}</ul>`
      : "";
    return head + items;
  }).join("");

  select.onchange = () => onAdvisory(select.value);
  list.onclick = (e) => {
    if (e.target.closest("#cleared-toggle")) { showCleared = !showCleared; onArtifact(sel.artifact); return; }
    const b = e.target.closest("[data-art]");
    if (b) onArtifact(b.dataset.art);
  };
}
