import * as api from "./api.js";
import { createAgent } from "./agent.js";
import { renderDecisions } from "./decisions.js";
import { renderEvidence } from "./evidence.js";
import { renderFleet, rowKey } from "./fleet.js";
import { VERDICT_RANK, esc, factView } from "./format.js";
import { createTimeline } from "./timeline.js";

const state = { meta: null, snap: null, prev: null, stop: null, sel: { advisory: null, artifact: null } };
const $ = (id) => document.getElementById(id);

function toast(html) {
  const el = $("toast");
  el.innerHTML = html;
  el.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (el.hidden = true), 6500);
}

/** Keep the user's selection if it still exists; otherwise pick the most urgent thing on screen. */
function reconcileSelection(snap) {
  const advisories = snap.advisories;
  if (!advisories.length) { state.sel = { advisory: null, artifact: null }; return; }
  if (!advisories.some((a) => a.id === state.sel.advisory)) {
    const latestHot = [...advisories].reverse().find((a) => a.counts.EXPOSED > 0);
    state.sel.advisory = (latestHot ?? advisories[advisories.length - 1]).id;
  }
  const adv = advisories.find((a) => a.id === state.sel.advisory);
  if (!adv.rows.some((r) => r.artifact === state.sel.artifact)) {
    const first = [...adv.rows].sort((a, b) => VERDICT_RANK[a.verdict] - VERDICT_RANK[b.verdict])[0];
    state.sel.artifact = first?.artifact ?? null;
  }
}

/** Rows whose verdict is new or different since the previous snapshot, so the UI can flash them. */
function changedRows(prev, snap) {
  const seen = new Map();
  prev?.advisories.forEach((a) => a.rows.forEach((r) => seen.set(rowKey(a.id, r.artifact), r.verdict)));
  const changed = new Set();
  snap.advisories.forEach((a) => a.rows.forEach((r) => {
    const k = rowKey(a.id, r.artifact);
    if (r.verdict === "EXPOSED" && seen.get(k) !== "EXPOSED") changed.add(k);
  }));
  return changed;
}

function renderBanners(snap) {
  const parts = [];
  const scripted = snap.events.find((e) => e.scripted);
  if (scripted) {
    parts.push(`<div class="banner scripted"><b>Hypothetical event applied.</b> ${esc(scripted.note)} It is scripted for this demo and is not a real advisory record.</div>`);
  }
  if (snap.reopened.length) {
    const names = snap.reopened.map((r) => `<b>${esc(r.artifact)}</b>`).join(", ");
    parts.push(`<div class="banner reopen">${snap.reopened.length === 1 ? "1 decision" : `${snap.reopened.length} decisions`} reopened: ${names}. Only decisions that assumed a fact the new event contradicts were touched.</div>`);
  }
  $("banner").innerHTML = parts.join("");
}

function render(changed = new Set()) {
  const { snap, sel } = state;
  const ctx = { live: api.isLive(), queries: state.meta.queries };
  renderFleet(snap, sel, changed, {
    onAdvisory: (id) => { state.sel.advisory = id; state.sel.artifact = null; reconcileSelection(snap); render(); },
    onArtifact: (id) => { state.sel.artifact = id; render(); },
  });
  renderEvidence(snap, sel, ctx, { onApprove, onVerify });
  renderDecisions(snap, sel, (advisory, artifact) => { state.sel = { advisory, artifact }; render(); });
  renderBanners(snap);
}

async function onApprove(advisory, artifact, approver) {
  try {
    const res = await api.approve(advisory, artifact, state.stop, approver);
    state.prev = state.snap;
    state.snap = res.snapshot;
    render();
  } catch (err) {
    toast(`Could not record the decision: ${esc(err.message)}`);
  }
}

async function onVerify(advisory, artifact) {
  try { return await api.verifyReceipt(advisory, artifact, state.stop); }
  catch (err) { return { ok: false, detail: err.message }; }
}

async function onStop(stop) {
  state.stop = stop;
  const prev = state.snap;
  const snap = await api.getSnapshot(stop);
  if (state.stop !== stop) return; // the user moved on while this was loading
  const newlyReopened = snap.reopened.filter((r) => !prev?.reopened.some((p) => p.decision === r.decision));
  state.prev = prev;
  state.snap = snap;
  reconcileSelection(snap);
  if (newlyReopened.length) {
    state.sel = { advisory: newlyReopened[0].advisory, artifact: newlyReopened[0].artifact };
  } else if (stop.kind === "advisory") {
    // jump to the newest exposure when a malicious release lands
    const adv = snap.advisories.find((a) => a.id === stop.advisory);
    const hit = adv?.rows.find((r) => r.verdict === "EXPOSED");
    if (adv && hit) state.sel = { advisory: adv.id, artifact: hit.artifact };
  }
  render(changedRows(prev, snap));
  if (newlyReopened.length) {
    const r = newlyReopened[0];
    toast(`<b>Decision reopened:</b> ${esc(r.artifact)} was ${esc(r.before)}, now ${esc(r.now)}.<br><span class="small">What changed: ${esc(r.broken.map((b) => factView(b).label).join("; "))}.</span>`);
  }
}

async function boot() {
  const meta = await api.init();
  state.meta = meta;
  $("incident-name").textContent = `${meta.incident.name} · 2026-08-04`;
  const live = api.isLive();
  const modeBadge = $("badge-mode");
  modeBadge.textContent = live ? "Live graph" : "Recorded snapshots";
  modeBadge.classList.add(live ? "live" : "static");
  $("badge-agent").textContent = meta.agent.backend === "llm" ? `Agent: ${meta.agent.model}` : "Agent: built-in planner (no model)";
  if (meta.repo) { const a = $("repo-link"); a.href = meta.repo; a.hidden = false; }

  createAgent({ suggestions: meta.suggestions, live, getStop: () => state.stop, ask: api.ask });
  const timeline = createTimeline({ stops: meta.timeline, onChange: onStop });
  // Land on the moment that tells the story (the keyv release) unless the URL names a stop: ?start=N
  const param = new URLSearchParams(location.search).get("start");
  const hero = meta.timeline.find((s) => s.kind === "advisory" && s.label.startsWith("keyv"));
  timeline.go(param !== null ? Number(param) : (hero?.index ?? 0));
}

boot().catch((err) => {
  console.error(err);
  $("incident-name").textContent = "Could not load data";
  toast(`<b>Could not load the incident:</b> ${esc(err.message)}`);
});
