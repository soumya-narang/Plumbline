import * as api from "./api.js";
import { createAgent } from "./agent.js";
import { renderDecisions } from "./decisions.js";
import { renderEvidence } from "./evidence.js";
import { renderFleet, rowKey } from "./fleet.js";
import { VERDICT_RANK, VERDICT_WORD, esc, factView, revLetter } from "./format.js";
import { createTimeline } from "./timeline.js";

const state = { meta: null, snap: null, prev: null, stop: null, sel: { advisory: null, artifact: null } };
const $ = (id) => document.getElementById(id);

function toast(html) {
  const el = $("toast");
  el.innerHTML = html;
  el.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (el.hidden = true), 7000);
}

/** The revision letter of the timeline stop at a given instant, for the delta markers. */
const revFor = (iso) => {
  const stop = state.meta.timeline.find((s) => s.at === iso);
  return stop ? revLetter(stop.index) : "?";
};

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

/** Rows that became exposed since the previous snapshot, so the schedule can flag them. */
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
    parts.push(`<div class="aside hypo"><span class="label">Hypothetical event</span><p>${esc(scripted.note)} It is scripted for this demonstration and is not a real advisory record.</p></div>`);
  }
  if (snap.reopened.length) {
    const names = snap.reopened.map((r) => `<b>${esc(r.artifact)}</b>`).join(", ");
    const letter = revFor(snap.reopened[0].broken_at);
    parts.push(`<div class="aside change"><span class="label">Revision ${esc(letter)}</span><p>${snap.reopened.length === 1 ? "One decision was" : `${snap.reopened.length} decisions were`} reopened: ${names}. Only decisions that assumed a fact the new event contradicts were touched.</p></div>`);
  }
  $("banner").innerHTML = parts.join("");
}

function renderTitleBlock() {
  const { snap, sel, stop } = state;
  const live = api.isLive();
  $("tb-drawing").textContent = sel.advisory ? `Exposure to ${sel.advisory}` : "Exposure survey";
  $("tb-source").textContent = live ? "Live FalkorDB graph" : "Recorded snapshots";
  $("tb-rev").textContent = stop ? revLetter(stop.index) : "A";
  void snap;
}

function render(changed = new Set()) {
  const { snap, sel } = state;
  const ctx = { live: api.isLive(), queries: state.meta.queries, revFor };
  renderFleet(snap, sel, changed, {
    onAdvisory: (id) => { state.sel.advisory = id; state.sel.artifact = null; reconcileSelection(snap); render(); },
    onArtifact: (id) => { state.sel.artifact = id; render(); },
  });
  renderEvidence(snap, sel, ctx, { onApprove, onVerify });
  renderDecisions(snap, sel, (advisory, artifact) => { state.sel = { advisory, artifact }; render(); }, revFor);
  renderBanners(snap);
  renderTitleBlock();
}

async function onApprove(advisory, artifact, approver) {
  try {
    const res = await api.approve(advisory, artifact, state.stop, approver);
    state.prev = state.snap;
    state.snap = res.snapshot;
    render();
  } catch (err) {
    toast(`<span class="label">Not recorded</span>${esc(err.message)}`);
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
    toast(`<span class="label">Decision reopened</span><b>${esc(r.artifact)}</b> was ${esc(VERDICT_WORD[r.before])}, now ${esc(VERDICT_WORD[r.now])}.<br>${esc(r.broken.map((b) => factView(b).label).join("; "))}.`);
  }
}

function initTheme() {
  const root = document.documentElement;
  const btn = $("theme-btn");
  let stored = null;
  try { stored = localStorage.getItem("plumbline.theme"); } catch { /* storage unavailable */ }
  const wanted = new URLSearchParams(location.search).get("theme") ?? stored;
  if (wanted === "light" || wanted === "dark") root.dataset.theme = wanted;
  const effective = () => root.dataset.theme ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const paint = () => { btn.textContent = effective() === "dark" ? "Blueprint" : "Vellum"; };
  btn.addEventListener("click", () => {
    root.dataset.theme = effective() === "dark" ? "light" : "dark";
    try { localStorage.setItem("plumbline.theme", root.dataset.theme); } catch { /* storage unavailable */ }
    paint();
  });
  paint();
}

async function boot() {
  initTheme();
  const meta = await api.init();
  state.meta = meta;
  $("incident-name").textContent = meta.incident.name;
  const live = api.isLive();
  const mode = $("badge-mode");
  mode.textContent = live ? "Live graph" : "Recorded snapshots";
  mode.classList.toggle("live", live);
  $("badge-agent").textContent = meta.agent.backend === "llm" ? `Agent · ${meta.agent.model}` : "Agent · built-in planner, no model";
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
  $("incident-name").textContent = "Could not load the incident";
  toast(`<span class="label">Load failed</span>${esc(err.message)}`);
});
