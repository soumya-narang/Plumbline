import {
  VERDICT_WORD, approverLabel, clock, esc, factView, grouped, highlightCypher, mark, plural, reasonText,
} from "./format.js";
import { brokenFacts, memorySvg } from "./memory.js";

const X = 14; // x of the plumb line
const GAP = 44; // vertical distance between joints
const TOP = 12;

/** The evidence path as a plumb line: a line hung from the service, ending in a bob at the malicious version. */
function plumbSvg(row, published) {
  const path = row.path;
  const ys = path.map((_, i) => TOP + (i + 1) * GAP);
  const bottom = ys.at(-1);
  const parts = [`<path class="line" style="--len:${bottom - TOP}" d="M${X} ${TOP} V${bottom}"/>`];

  parts.push(`<g class="row" style="--d:0s"><path class="bar" d="M${X - 12} ${TOP} H${X + 12}"/>
    <text class="svc" x="${X + 26}" y="${TOP + 4}">${esc(row.service ?? "service")}</text>
    <text class="sub" x="${X + 26}" y="${TOP + 21}">${esc(row.artifact)}</text></g>`);

  path.forEach((name, i) => {
    const y = ys[i];
    const top = i === 0 ? TOP : ys[i - 1];
    parts.push(`<text class="rel" style="--d:${((i + 1) / path.length) * 0.7}s" x="${X + 10}" y="${(top + y) / 2 + 3}">${i === 0 ? "LOCKS" : "REQUIRES"}</text>`);
    const last = i === path.length - 1;
    const d = `${((i + 1) / path.length) * 0.7}s`;
    const note = last
      ? `malicious version${published ? `, published ${clock(published)} UTC` : ""}`
      : i === 0 ? "direct dependency" : "";
    parts.push(last
      ? `<g class="bobg" style="--d:${d}"><rect class="halo" x="${X - 9}" y="${y - 9}" width="18" height="18" rx="4"/><rect class="poison" x="${X - 9}" y="${y - 9}" width="18" height="18" rx="4"/></g>`
      : `<circle class="joint" style="--d:${d}" cx="${X}" cy="${y}" r="5"/>`);
    parts.push(`<g class="row ${last ? "bad" : ""}" style="--d:${d}"><text class="nm" x="${X + 26}" y="${y + 4}">${esc(name)}</text>
      ${note ? `<text class="sub" x="${X + 26}" y="${y + 21}">${esc(note)}</text>` : ""}</g>`);
  });

  const H = bottom + 26;
  return `<svg class="plumb-svg" viewBox="0 0 520 ${H}" role="img" aria-label="Dependency path from ${esc(row.service ?? "the service")}: ${esc(path.join(", then "))}">${parts.join("")}</svg>`;
}

function assumptions(items, brokenIds, brokenAt) {
  if (!items.length) return "";
  return `<ol class="assumptions">${items.map((a) => {
    const f = factView(a.id);
    const broken = brokenIds.has(a.id);
    return `<li class="${broken ? "broken" : ""}"><span><span class="txt">${esc(f.label)}</span>
      <span class="why">${broken ? `No longer true since ${esc(clock(brokenAt))} UTC` : esc(f.why)}</span></span></li>`;
  }).join("")}</ol>`;
}

function decisionBlock(row, snap, ctx) {
  const d = row.decision && snap.decisions.find((x) => x.decision === row.decision.id);
  if (d) {
    return `<dl class="stamp"><dt>Status</dt><dd style="font-family:var(--text)">${esc(VERDICT_WORD[d.verdict])}, ${esc(d.status)}</dd>
      <dt>Approved by</dt><dd style="font-family:var(--text)">${esc(approverLabel(d.approver))} at ${esc(clock(d.created))} UTC</dd></dl>`;
  }
  if (!ctx.live) return '<p class="hint" style="margin-top:0">Nothing recorded yet. Approving is available in the live deployment.</p>';
  let name = "";
  try { name = localStorage.getItem("plumbline.approver") ?? ""; } catch { /* storage unavailable */ }
  return `<div class="approve"><input id="approver" placeholder="Your name" value="${esc(name)}" maxlength="80" aria-label="Approver name">
    <button type="button" id="approve">Approve</button></div>
    <p class="hint">Approving records the facts this verdict assumes. A model can propose; only a person approves.</p>`;
}

export function renderEvidence(snap, sel, ctx, handlers) {
  const body = document.getElementById("evidence-body");
  const adv = snap.advisories.find((a) => a.id === sel.advisory);
  const row = adv?.rows.find((r) => r.artifact === sel.artifact);
  if (!adv || !row) {
    body.innerHTML = '<p class="empty" style="padding:8px 0">Nothing to show yet. Step the timeline to the first malicious release.</p>';
    return;
  }
  const reopened = snap.reopened.find((r) => r.advisory === adv.id && r.artifact === row.artifact);
  const brokenIds = new Set(reopened?.broken ?? []);

  let statement;
  let main = "";
  if (row.verdict === "EXPOSED") {
    const bad = row.evidence.map((e) => `${e.name}@${e.version}`).join(", ");
    statement = row.hops === 0
      ? `It depends directly on ${bad}, a malicious release${row.evidence.some((e) => e.dev) ? " (development only)" : ""}.`
      : `It reaches ${bad}, a malicious release, through ${plural(row.hops, "package")}${row.evidence.some((e) => e.dev) ? " (development only)" : ""}.`;
    main = `<div class="section">${plumbSvg(row, adv.published)}</div>
      ${row.pulled_by?.length ? `<div class="fix"><span class="fix-k">Fix</span><p>Bump ${row.pulled_by.map((p) => `<code>${esc(p)}</code>`).join(", ")}. ${row.pulled_by.length === 1 ? "It is" : "They are"} the only ${row.pulled_by.length === 1 ? "way" : "ways"} in.</p></div>` : ""}`;
  } else if (row.verdict === "CLEARED") {
    statement = row.evidence.length
      ? `It locks ${row.evidence.length === 1 ? "this version" : "these versions"} of ${adv.package}, none of which ${adv.id} names.`
      : `${adv.package} does not appear in its lockfile.`;
    main = row.evidence.length ? `<div class="section"><h4>Locked versions</h4><div class="vers">${row.evidence.map((e) => `<span>${esc(e.name)}@${esc(e.version)}</span>`).join("")}</div></div>` : "";
  } else {
    const r = reasonText(row.reason);
    statement = `${r.title}.`;
    main = `<div class="section"><div class="refusal"><strong>Refusing to guess</strong>${esc(r.body)}<p class="hint"><b>What would settle it:</b> ${esc(r.settle)}</p></div></div>`;
  }

  const why = reopened
    ? `<div class="section reopened"><h4>Why this decision was reopened</h4>
        <p style="margin-bottom:8px">It was approved as <b>${esc(VERDICT_WORD[reopened.before])}</b> on the assumptions below. One stopped being true, so it is now <b>${esc(VERDICT_WORD[reopened.now])}</b>.</p>
        ${memorySvg(snap.decisions, brokenFacts(snap), { focus: reopened.decision })}
        ${assumptions((snap.decisions.find((d) => d.decision === reopened.decision)?.assumption_ids ?? []).map((id) => ({ id })), brokenIds, reopened.broken_at)}</div>`
    : "";
  const assumed = !reopened && row.assumptions.length
    ? `<h5>What this verdict assumes</h5>${assumptions(row.assumptions, brokenIds, "")}`
    : "";

  const proof = row.receipt || (row.verdict === "EXPOSED" && ctx.queries?.q2)
    ? `<h5>Proof</h5>
        ${row.receipt ? `<dl class="stamp"><dt>Receipt</dt><dd>${esc(grouped(row.receipt))}</dd><dt>Check</dt>
          <dd style="font-family:var(--text)"><button type="button" class="link" id="verify" ${ctx.live ? "" : 'disabled title="Verification re-derives the verdict from the live graph"'}>Re-derive from the graph</button><span id="verify-result" class="result" aria-live="polite"></span></dd></dl>` : ""}
        ${row.verdict === "EXPOSED" && ctx.queries?.q2 ? `<pre class="cypher">${highlightCypher(ctx.queries.q2)}</pre>` : ""}`
    : "";
  const how = assumed || proof
    ? `<details class="proof"${reopened || row.verdict === "EXPOSED" ? " open" : ""}><summary>How this was decided</summary>${assumed}${proof}</details>`
    : "";

  body.innerHTML = `<div class="verdict ${row.verdict}">${mark(row.verdict)} ${esc(VERDICT_WORD[row.verdict])}</div>
    <div class="ev-head"><h3>${esc(row.artifact)}</h3>${row.synthetic ? '<span class="tag">planted fixture</span>' : ""}</div>
    <p class="ev-meta">${esc(row.service ?? "")} · ${row.exposure === "internet" ? "faces the internet" : "internal"}</p>
    <p class="statement">${esc(statement)}</p>
    ${main}${why}
    <div class="section"><h4>Decision</h4>${decisionBlock(row, snap, ctx)}</div>${how}`;


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
    out.textContent = `${res.ok ? "✓ Verified" : "✗ Failed"}: ${res.detail}`;
    e.target.disabled = false;
  });
}
