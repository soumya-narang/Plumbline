import {
  VERDICT_WORD, approverLabel, attachClouds, clock, esc, factView, grouped, highlightCypher, mark, plural, reasonText,
} from "./format.js";

const X = 118; // x of the plumb line inside the drawing
const GAP = 66; // vertical distance between joints
const TOP = 44;

/** The evidence path as a plumb line: a dimensioned line hung from the service, ending in a bob. */
function plumbSvg(row, published) {
  const path = row.path;
  const ys = [TOP, ...path.map((_, i) => TOP + (i + 1) * GAP)];
  const bottom = ys.at(-1);
  const H = bottom + 54;
  const len = bottom - TOP;
  const hops = path.length - 1;
  const parts = [];

  // dimension line along the left, with arrowheads, as on a drawing
  if (hops >= 1) {
    const y0 = ys[1];
    const mid = (y0 + bottom) / 2;
    parts.push(`<line class="ext" x1="${X - 16}" x2="30" y1="${y0}" y2="${y0}"/><line class="ext" x1="${X - 16}" x2="30" y1="${bottom}" y2="${bottom}"/>
      <line class="dim" x1="34" x2="34" y1="${y0 + 8}" y2="${bottom - 8}"/>
      <path class="dimhead" d="M34 ${y0} L30 ${y0 + 9} L38 ${y0 + 9} Z"/><path class="dimhead" d="M34 ${bottom} L30 ${bottom - 9} L38 ${bottom - 9} Z"/>
      <text class="dimtxt" transform="translate(20 ${mid}) rotate(-90)" text-anchor="middle">${plural(hops, "hop")}</text>`);
  }

  parts.push(`<path class="line" style="--len:${len}" d="M${X} ${TOP} V${bottom}"/>`);

  // the service hangs the line from a bar
  parts.push(`<g class="row" style="--d:0s"><path d="M${X - 18} ${TOP} H${X + 18}" stroke="currentColor" stroke-width="2.5" style="stroke:var(--ink)"/>
    <text class="svc" x="${X + 30}" y="${TOP + 1}">${esc(row.service ?? "service")}</text>
    <text class="sub" x="${X + 30}" y="${TOP + 18}">${esc(row.artifact)} · ${row.exposure === "internet" ? "internet-facing" : "internal"}</text></g>`);

  path.forEach((name, i) => {
    const y = ys[i + 1];
    const last = i === path.length - 1;
    const d = `${((i + 1) / path.length) * 0.8}s`;
    const note = last
      ? `malicious version${published ? ` · published ${clock(published)} UTC` : ""}`
      : i === 0 ? "direct dependency" : "transitive dependency";
    if (last) {
      parts.push(`<g class="bobg" style="--d:${d}"><circle class="halo" cx="${X}" cy="${y}" r="11"/><circle class="bob" cx="${X}" cy="${y}" r="11"/></g>`);
    } else {
      parts.push(`<circle class="joint" style="--d:${d}" cx="${X}" cy="${y}" r="5.5"/>`);
    }
    parts.push(`<g class="row ${last ? "bad" : ""}" style="--d:${d}"><text class="nm" x="${X + 30}" y="${y + 4}">${esc(name)}</text>
      <text class="sub" x="${X + 30}" y="${y + 21}">${esc(note)}</text></g>`);
  });

  return `<svg class="plumb-svg" viewBox="0 0 600 ${H}" role="img" aria-label="Dependency path from ${esc(row.service ?? "the service")}: ${esc(path.join(", then "))}">${parts.join("")}</svg>`;
}

function notes(items, brokenIds, brokenAt, revFor) {
  if (!items.length) return "";
  return `<ol class="notes">${items.map((a) => {
    const f = factView(a.id);
    const broken = brokenIds.has(a.id);
    const delta = broken ? `<span class="delta"><i></i>${esc(revFor(brokenAt))}</span>` : "";
    return `<li class="${broken ? "broken" : ""}" ${broken ? "data-cloud" : ""}><span><span class="txt">${esc(f.label)}</span>
      <span class="why">${broken ? `No longer true since ${esc(clock(brokenAt))} UTC` : esc(f.why)}</span></span>${delta}</li>`;
  }).join("")}</ol>`;
}

function decisionBlock(row, snap, ctx) {
  const d = row.decision && snap.decisions.find((x) => x.decision === row.decision.id);
  if (d) {
    return `<dl class="stamp"><dt>Decision</dt><dd>${esc(VERDICT_WORD[d.verdict])} · ${esc(d.status)}</dd>
      <dt>Approved by</dt><dd>${esc(approverLabel(d.approver))} at ${esc(clock(d.created))} UTC</dd></dl>`;
  }
  if (!ctx.live) {
    return `<p class="hint">No decision is recorded for this artifact yet. Approving is available in the live deployment.</p>`;
  }
  let name = "";
  try { name = localStorage.getItem("plumbline.approver") ?? ""; } catch { /* storage unavailable */ }
  return `<div class="approve"><input id="approver" placeholder="Your name" value="${esc(name)}" maxlength="80" aria-label="Approver name">
    <button type="button" id="approve">Approve</button></div>
    <p class="hint">Approving records the facts this verdict assumes. A model can propose; only a person approves.</p>`;
}

export function renderEvidence(snap, sel, ctx, handlers) {
  const body = document.getElementById("evidence-body");
  const sub = document.getElementById("ev-sub");
  const adv = snap.advisories.find((a) => a.id === sel.advisory);
  const row = adv?.rows.find((r) => r.artifact === sel.artifact);
  if (!adv || !row) {
    sub.textContent = "";
    body.innerHTML = '<p class="empty">Nothing to draw yet. Step the timeline to the first malicious release.</p>';
    return;
  }
  sub.textContent = `${adv.id} · ${adv.package}`;
  const reopened = snap.reopened.find((r) => r.advisory === adv.id && r.artifact === row.artifact);
  const brokenIds = new Set(reopened?.broken ?? []);
  const reach = row.exposure === "internet" ? "internet-facing" : "internal";

  let statement = "";
  let main = "";
  if (row.verdict === "EXPOSED") {
    statement = `Its lockfile pins ${row.evidence.map((e) => `${e.name}@${e.version}`).join(", ")}, which ${adv.id} names as malicious${row.evidence.some((e) => e.dev) ? " (a development dependency)" : ""}.`;
    main = `<section class="block"><span class="label">Path · ${row.hops === 0 ? "direct dependency" : plural(row.hops, "hop")}</span>${plumbSvg(row, adv.published)}</section>`;
  } else if (row.verdict === "CLEARED") {
    statement = row.evidence.length
      ? `It locks ${row.evidence.length === 1 ? "this version" : "these versions"} of ${adv.package}, none of which ${adv.id} names.`
      : `${adv.package} does not appear in its lockfile.`;
    main = row.evidence.length ? `<section class="block"><span class="label">Locked versions</span><div class="vers">${row.evidence.map((e) => `<span>${esc(e.name)}@${esc(e.version)}</span>`).join("")}</div></section>` : "";
  } else {
    const r = reasonText(row.reason);
    statement = r.title + ".";
    main = `<section class="block"><div class="refusal"><strong>Refusing to guess</strong>${esc(r.body)}<p class="hint" style="margin-top:8px"><b>What would settle it:</b> ${esc(r.settle)}</p></div></section>`;
  }

  const notesBlock = row.assumptions.length
    ? `<section class="block"><span class="label">General notes · what this verdict assumes</span>${notes(row.assumptions, brokenIds, reopened?.broken_at ?? "", ctx.revFor)}</section>`
    : "";

  const reopenedBlock = reopened
    ? `<section class="block"><span class="label">Revision · decision reopened</span>
        <p class="statement" style="margin-bottom:10px">Approved as <b>${esc(VERDICT_WORD[reopened.before])}</b> on the assumptions below. One stopped being true, so it is now <b>${esc(VERDICT_WORD[reopened.now])}</b>.</p>
        ${notes((snap.decisions.find((d) => d.decision === reopened.decision)?.assumption_ids ?? []).map((id) => ({ id })), brokenIds, reopened.broken_at, ctx.revFor)}</section>`
    : "";

  const receipt = row.receipt
    ? `<section class="block"><span class="label">Receipt</span><dl class="stamp"><dt>Hash</dt><dd>${esc(grouped(row.receipt))}</dd>
        <dt>Check</dt><dd><button type="button" class="link" id="verify" ${ctx.live ? "" : 'disabled title="Verification re-derives the verdict from the live graph"'}>Re-derive from the graph</button><span id="verify-result" class="result" aria-live="polite"></span></dd></dl></section>`
    : "";

  const query = row.verdict === "EXPOSED" && ctx.queries?.q2
    ? `<section class="block"><details><summary>The Cypher behind this path</summary><pre class="cypher">${highlightCypher(ctx.queries.q2)}</pre></details></section>`
    : "";

  body.innerHTML = `<div class="d-title"><h3>${esc(row.artifact)}</h3>${row.synthetic ? '<span class="tag">planted fixture</span>' : ""}</div>
    <p class="d-meta">${esc(row.service ?? "")} · ${reach} · declared, not discovered</p>
    <div class="verdict-line ${row.verdict}">${mark(row.verdict)}<span class="word">${esc(VERDICT_WORD[row.verdict])}</span></div>
    <p class="statement">${esc(statement)}</p>
    ${main}${reopenedBlock}${reopened ? "" : notesBlock}
    <section class="block"><span class="label">Decision</span>${decisionBlock(row, snap, ctx)}</section>${receipt}${query}`;

  attachClouds(body);

  body.querySelector("#approve")?.addEventListener("click", () => {
    const input = body.querySelector("#approver");
    const name = input.value.trim();
    if (!name) { input.focus(); return; }
    try { localStorage.setItem("plumbline.approver", name); } catch { /* storage unavailable */ }
    handlers.onApprove(adv.id, row.artifact, name);
  });
  body.querySelector("#verify")?.addEventListener("click", async (e) => {
    const out = body.querySelector("#verify-result");
    e.target.disabled = true;
    out.className = "result";
    out.textContent = "Re-deriving from the graph…";
    const res = await handlers.onVerify(adv.id, row.artifact);
    out.className = `result ${res.ok ? "ok" : "bad"}`;
    out.textContent = `${res.ok ? "Verified" : "Failed"}: ${res.detail}`;
    e.target.disabled = false;
  });
}
