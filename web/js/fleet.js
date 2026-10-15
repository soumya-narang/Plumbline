import { VERDICT_RANK, VERDICT_WORD, esc, mark, purlLabel } from "./format.js";

export const rowKey = (advisory, artifact) => `${advisory}|${artifact}`;

const GROUPS = [
  ["EXPOSED", "Exposed"],
  ["UNKNOWN", "Not determined · refusing to guess"],
  ["CLEARED", "Cleared · relative to stated assumptions"],
];

let showCleared = false;

function tab(adv, selected) {
  const first = purlLabel(adv.affected_purls[0] ?? adv.package).replace(/^@[^/]+\//, "");
  const more = adv.affected_purls.length > 1 ? ` +${adv.affected_purls.length - 1}` : "";
  return `<button type="button" role="tab" class="adv-tab" aria-selected="${selected}" data-adv="${esc(adv.id)}" title="${esc(adv.id)}">
    ${adv.counts.EXPOSED ? '<span class="hot">■</span> ' : ""}${esc(first)}${more}</button>`;
}

function decisionTag(row) {
  if (!row.decision) return "";
  return row.decision.status === "reopened" ? '<span class="tag change">revised</span>' : '<span class="tag">decided</span>';
}

function rowHtml(adv, row, selected, flash) {
  return `<tr data-art="${esc(row.artifact)}" aria-selected="${selected}" class="${flash ? "flash" : ""}" tabindex="0">
    <td class="markcell">${mark(row.verdict)}</td>
    <td><span class="name">${esc(row.artifact)}</span>${row.synthetic ? '<span class="tag">planted</span>' : ""}${decisionTag(row)}
      <div class="sub">${esc(row.service ?? "")}</div></td>
    <td class="reach">${row.exposure === "internet" ? "internet" : "internal"}</td>
    <td class="state ${row.verdict}">${esc(VERDICT_WORD[row.verdict])}</td></tr>`;
}

export function renderFleet(snap, sel, changed, { onAdvisory, onArtifact }) {
  const tabs = document.getElementById("adv-tabs");
  const summary = document.getElementById("counts");
  const list = document.getElementById("fleet-list");
  const sub = document.getElementById("fleet-sub");

  if (!snap.advisories.length) {
    tabs.innerHTML = "";
    summary.innerHTML = "";
    sub.textContent = "";
    list.innerHTML = '<p class="empty">No malicious release has been published yet.<br>Step forward to 11:12:20.</p>';
    return;
  }

  sub.textContent = `${snap.advisories[0].rows.length} artifacts`;
  tabs.innerHTML = snap.advisories.map((a) => tab(a, a.id === sel.advisory)).join("");
  const adv = snap.advisories.find((a) => a.id === sel.advisory) ?? snap.advisories[0];
  const c = adv.counts;
  summary.innerHTML = [["exposed", "EXPOSED", c.EXPOSED, "Exposed"], ["unknown", "UNKNOWN", c.UNKNOWN, "Not determined"], ["cleared", "CLEARED", c.CLEARED, "Cleared"]]
    .map(([cls, v, n, text]) => `<div class="${cls}"><span class="n">${n}</span><span class="label">${mark(v)} ${text}</span></div>`)
    .join("");

  const selectedRow = adv.rows.find((r) => r.artifact === sel.artifact);
  if (selectedRow?.verdict === "CLEARED") showCleared = true;

  const rows = [...adv.rows].sort((a, b) => VERDICT_RANK[a.verdict] - VERDICT_RANK[b.verdict] || a.artifact.localeCompare(b.artifact));
  const body = GROUPS.map(([verdict, title]) => {
    const group = rows.filter((r) => r.verdict === verdict);
    if (!group.length) return "";
    const head = verdict === "CLEARED"
      ? `<tr class="gtitle"><td colspan="4"><button type="button" class="cleared-toggle" id="cleared-toggle" aria-expanded="${showCleared}" style="padding:0;border:0">${showCleared ? "−" : "+"} ${title} (${group.length})</button></td></tr>`
      : `<tr class="gtitle"><td colspan="4"><span class="label">${title} (${group.length})</span></td></tr>`;
    const visible = verdict !== "CLEARED" || showCleared;
    return head + (visible ? group.map((r) => rowHtml(adv, r, r.artifact === sel.artifact, changed.has(rowKey(adv.id, r.artifact)))).join("") : "");
  }).join("");

  list.innerHTML = `<table class="sched"><thead><tr><th></th><th>Artifact · service</th><th>Reach</th><th style="text-align:right">State</th></tr></thead><tbody>${body}</tbody></table>`;

  tabs.onclick = (e) => { const b = e.target.closest("[data-adv]"); if (b) onAdvisory(b.dataset.adv); };
  const pick = (el) => { if (el?.dataset.art) onArtifact(el.dataset.art); };
  list.onclick = (e) => {
    if (e.target.closest("#cleared-toggle")) { showCleared = !showCleared; onArtifact(sel.artifact); return; }
    pick(e.target.closest("tr[data-art]"));
  };
  list.onkeydown = (e) => {
    if (e.key === "Enter" || e.key === " ") { const tr = e.target.closest("tr[data-art]"); if (tr) { e.preventDefault(); pick(tr); } }
  };
}
