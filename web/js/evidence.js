import { PIN, approverLabel, esc, factView, highlightCypher, plural, reasonText } from "./format.js";

const stamp = (v) => `<span class="stamp ${v}">${v}</span>`;

function factList(assumptions, brokenIds, brokenAt) {
  if (!assumptions.length) return "";
  return `<ul class="facts">${assumptions
    .map((a) => {
      const f = factView(a.id);
      const broken = brokenIds.has(a.id);
      return `<li class="fact ${broken ? "broken" : ""}">${PIN}<span><span class="label">${esc(f.label)}</span>
        <span class="why">${broken ? `Broken at ${esc(brokenAt.slice(11, 19))} UTC` : esc(f.why)}</span></span></li>`;
    })
    .join("")}</ul>`;
}

function chain(row) {
  const parts = [
    `<span class="node origin" style="animation-delay:0ms">${esc(row.service ?? "service")}<small>${esc(row.artifact)} · ${esc(row.exposure ?? "")}</small></span>`,
  ];
  row.path.forEach((p, i) => {
    const last = i === row.path.length - 1;
    const note = last ? "malicious version" : i === 0 ? "direct dependency" : "transitive";
    parts.push(`<span class="link" style="animation-delay:${i * 170 + 90}ms"></span>`);
    parts.push(`<span class="node ${last ? "bad" : ""}" style="animation-delay:${(i + 1) * 170}ms">${esc(p)}<small>${note}</small></span>`);
  });
  return `<div class="chain" role="img" aria-label="Dependency path: ${esc(row.path.join(" then "))}">${parts.join("")}</div>`;
}

function decisionBlock(row, snap, ctx) {
  const d = row.decision && snap.decisions.find((x) => x.decision === row.decision.id);
  if (d) {
    return `<dl class="kv"><dt>Decision</dt><dd>${esc(d.verdict)} · <b>${esc(d.status)}</b></dd>
      <dt>Approved by</dt><dd>${esc(approverLabel(d.approver))} at ${esc(d.created.slice(11, 19))} UTC</dd></dl>`;
  }
  if (!ctx.live) {
    return `<p class="muted small">No decision recorded yet. Approving is available in the live deployment.</p>`;
  }
  const name = localStorage.getItem("plumbline.approver") ?? "";
  return `<div class="ask"><input id="approver" placeholder="Your name (required)" value="${esc(name)}" maxlength="80" aria-label="Approver name">
    <button type="button" class="btn primary" id="approve">Approve ${row.verdict.toLowerCase()} verdict</button></div>
    <p class="muted small">Approving records the facts this verdict assumes. A model can propose; only a person approves.</p>`;
}

export function renderEvidence(snap, sel, ctx, handlers) {
  const body = document.getElementById("evidence-body");
  const sub = document.getElementById("ev-sub");
  const adv = snap.advisories.find((a) => a.id === sel.advisory);
  const row = adv?.rows.find((r) => r.artifact === sel.artifact);
  if (!adv || !row) {
    sub.textContent = "";
    body.innerHTML = '<p class="empty">Pick an artifact to see why it has its verdict.</p>';
    return;
  }
  sub.textContent = `${adv.id} · ${adv.package}`;
  const reopened = snap.reopened.find((r) => r.advisory === adv.id && r.artifact === row.artifact);
  const brokenIds = new Set(reopened?.broken ?? []);

  let main = "";
  if (row.verdict === "EXPOSED") {
    main = `<p class="lede">Its lockfile pins ${esc(row.evidence.map((e) => `${e.name}@${e.version}`).join(", "))}, which ${esc(adv.id)} names as malicious${row.evidence.some((e) => e.dev) ? " (development dependency)" : ""}.</p>
      <div class="section"><h4>Evidence path · ${row.hops === 0 ? "direct dependency" : plural(row.hops, "hop")}</h4>${chain(row)}</div>`;
  } else if (row.verdict === "CLEARED") {
    const versions = row.evidence.map((e) => `<span class="chip">${esc(e.name)}@${esc(e.version)}</span>`).join(" ");
    main = `<p class="lede">${row.evidence.length ? `It locks ${versions}, none of which ${esc(adv.id)} names.` : `The package does not appear in its lockfile.`}
      This holds only while the assumptions below stay true.</p>
      <div class="section"><h4>Assumptions this verdict rests on</h4>${factList(row.assumptions, brokenIds, reopened?.broken_at ?? "")}</div>`;
  } else {
    const r = reasonText(row.reason);
    main = `<div class="refusal"><b>Refusing to guess.</b> ${esc(r.title)}.<p class="muted" style="margin-top:4px">${esc(r.body)}</p>
      <p class="small" style="margin-top:6px"><b>What would settle it:</b> ${esc(r.settle)}</p></div>`;
  }

  const reopenedBlock = reopened
    ? `<div class="section"><h4>Reopened decision</h4>
        <p class="lede" style="margin-bottom:8px">It was approved as <b>${esc(reopened.before)}</b>, assuming the facts below. One of them stopped being true, so it is now <b>${esc(reopened.now)}</b>.</p>
        ${factList(snap.decisions.find((d) => d.decision === reopened.decision)?.assumption_ids.map((id) => ({ id })) ?? [], brokenIds, reopened.broken_at)}</div>`
    : "";

  const receipt = row.receipt
    ? `<div class="section"><h4>Receipt</h4>
        <dl class="kv"><dt>Hash</dt><dd class="mono">${esc(row.receipt.slice(0, 32))}…</dd></dl>
        <p style="margin-top:8px"><button type="button" class="btn" id="verify" ${ctx.live ? "" : 'disabled title="Verification re-derives the verdict from the live graph"'}>Re-derive and verify</button>
        <span id="verify-result" class="result" aria-live="polite"></span></p></div>`
    : "";

  const query = row.verdict === "EXPOSED" && ctx.queries?.q2
    ? `<div class="section"><details><summary>The Cypher behind this path</summary><pre class="cypher">${highlightCypher(ctx.queries.q2)}</pre></details></div>`
    : "";

  body.innerHTML = `<div class="ev-title">${stamp(row.verdict)}<h3>${esc(row.artifact)}</h3>
      ${row.synthetic ? '<span class="tag planted">planted fixture</span>' : ""}</div>
    <p class="muted small" style="margin-bottom:10px">${esc(row.service ?? "")} · ${row.exposure === "internet" ? "internet-facing" : "internal"} · declared</p>
    ${main}${reopenedBlock}
    <div class="section"><h4>Decision</h4>${decisionBlock(row, snap, ctx)}</div>${receipt}${query}`;

  body.querySelector("#approve")?.addEventListener("click", () => {
    const name = body.querySelector("#approver").value.trim();
    if (!name) { body.querySelector("#approver").focus(); return; }
    localStorage.setItem("plumbline.approver", name);
    handlers.onApprove(adv.id, row.artifact, name);
  });
  body.querySelector("#verify")?.addEventListener("click", async (e) => {
    const out = body.querySelector("#verify-result");
    e.target.disabled = true;
    out.className = "result";
    out.textContent = " Re-deriving from the graph…";
    const res = await handlers.onVerify(adv.id, row.artifact);
    out.className = `result ${res.ok ? "ok" : "bad"}`;
    out.textContent = ` ${res.ok ? "Verified" : "Failed"}: ${res.detail}`;
    e.target.disabled = false;
  });
}
