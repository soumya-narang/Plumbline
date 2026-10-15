import * as api from "./api.js";
import { createAgent } from "./agent.js";
import { renderDecisions } from "./decisions.js";
import { renderEvidence } from "./evidence.js";
import { renderFleet, rowKey } from "./fleet.js";
import { VERDICT_RANK, esc, factView, plural } from "./format.js";
import { createTimeline } from "./timeline.js";

const state = { meta: null, snap: null, stop: null, sel: { advisory: null, artifact: null }, tab: "evidence", pinnedTab: false };
const $ = (id) => document.getElementById(id);
const TABS = ["evidence", "decisions", "ask"];

function toast(html) {
  const el = $("toast");
  el.innerHTML = html;
  el.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (el.hidden = true), 6500);
}

function setTab(name) {
  state.tab = name;
  TABS.forEach((t) => {
    $(`tab-${t}`).setAttribute("aria-selected", String(t === name));
    $(`panel-${t}`).hidden = t !== name;
  });
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

/** Rows that became exposed since the previous snapshot, so the list can flag them. */
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

/** One notice at a time: the thing that changed, and why. */
function renderNotice(snap) {
  const el = $("notice");
  if (!snap.reopened.length) { el.innerHTML = ""; return; }
  const r = snap.reopened[0];
  const names = snap.reopened.map((x) => esc(x.artifact)).join(", ");
  el.innerHTML = `<div class="notice"><div><strong>${plural(snap.reopened.length, "decision")} reopened: ${names}</strong>
      <span class="why">${esc(factView(r.broken[0]).label)} was assumed, until a <span class="hypo-tag">hypothetical</span> advisory revision named it. The event is scripted for this demonstration and is not a real record.</span></div>
    <button type="button" class="btn ghost" id="review">Review</button></div>`;
  $("review").onclick = () => { state.sel = { advisory: r.advisory, artifact: r.artifact }; setTab("evidence"); render(); $("detail").focus(); };
}

function render(changed = new Set()) {
  const { snap, sel } = state;
  const ctx = { live: api.isLive(), queries: state.meta.queries };
  renderFleet(snap, sel, changed, {
    onAdvisory: (id) => { state.sel.advisory = id; state.sel.artifact = null; reconcileSelection(snap); render(); },
    onArtifact: (id) => { state.sel.artifact = id; setTab("evidence"); render(); },
  });
  renderEvidence(snap, sel, ctx, { onApprove, onVerify });
  renderDecisions(snap, sel, (advisory, artifact) => { state.sel = { advisory, artifact }; setTab("evidence"); render(); });
  renderNotice(snap);
}

async function onApprove(advisory, artifact, approver) {
  try {
    const res = await api.approve(advisory, artifact, state.stop, approver);
    state.snap = res.snapshot;
    render();
  } catch (err) {
    toast(`<b>Not recorded.</b> ${esc(err.message)}`);
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
  if (state.stop !== stop) return; // the viewer moved on while this was loading
  const newlyReopened = snap.reopened.filter((r) => !prev?.reopened.some((p) => p.decision === r.decision));
  state.snap = snap;
  reconcileSelection(snap);
  if (newlyReopened.length) {
    state.sel = { advisory: newlyReopened[0].advisory, artifact: newlyReopened[0].artifact };
    if (!state.pinnedTab) setTab("evidence");
  } else if (stop.kind === "advisory") {
    // jump to the newest exposure when a malicious release lands
    const adv = snap.advisories.find((a) => a.id === stop.advisory);
    const hit = adv?.rows.find((r) => r.verdict === "EXPOSED");
    if (adv && hit) state.sel = { advisory: adv.id, artifact: hit.artifact };
  }
  render(changedRows(prev, snap));
}

function initTheme() {
  const root = document.documentElement;
  const btn = $("theme-btn");
  let stored = null;
  try { stored = localStorage.getItem("plumbline.theme"); } catch { /* storage unavailable */ }
  const wanted = new URLSearchParams(location.search).get("theme") ?? stored;
  if (wanted === "light" || wanted === "dark") root.dataset.theme = wanted;
  const effective = () => root.dataset.theme ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const paint = () => { btn.textContent = effective() === "dark" ? "Switch to light" : "Switch to dark"; };
  btn.addEventListener("click", () => {
    root.dataset.theme = effective() === "dark" ? "light" : "dark";
    try { localStorage.setItem("plumbline.theme", root.dataset.theme); } catch { /* storage unavailable */ }
    paint();
  });
  paint();
}

function initTabs() {
  TABS.forEach((t) => $(`tab-${t}`).addEventListener("click", () => setTab(t)));
  $("tab-evidence").parentElement.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const next = TABS[(TABS.indexOf(state.tab) + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    setTab(next);
    $(`tab-${next}`).focus();
    e.stopPropagation();
  });
}

async function boot() {
  initTheme();
  initTabs();
  const meta = await api.init();
  state.meta = meta;
  $("incident-name").textContent = meta.incident.name;
  const live = api.isLive();
  const mode = $("badge-mode");
  mode.textContent = live ? "Live graph" : "Recorded snapshots";
  mode.classList.toggle("live", live);
  $("badge-agent").textContent = meta.agent.backend === "llm" ? `Agent: ${meta.agent.model}` : "Agent: built-in planner, no model";
  if (meta.repo) { const a = $("repo-link"); a.href = meta.repo; a.hidden = false; }

  createAgent({ suggestions: meta.suggestions, live, getStop: () => state.stop, ask: api.ask });
  const timeline = createTimeline({ stops: meta.timeline, onChange: onStop });
  // Land on the moment that tells the story (the keyv release) unless the URL names a stop: ?start=N
  const param = new URLSearchParams(location.search).get("start");
  const hero = meta.timeline.find((s) => s.kind === "advisory" && s.label.startsWith("keyv"));
  timeline.go(param !== null ? Number(param) : (hero?.index ?? 0));
  const tab = new URLSearchParams(location.search).get("tab");
  if (TABS.includes(tab)) { state.pinnedTab = true; setTab(tab); } // a ?tab= link stays on that tab
}

boot().catch((err) => {
  console.error(err);
  $("incident-name").textContent = "Could not load the incident";
  toast(`<b>Load failed.</b> ${esc(err.message)}`);
});
