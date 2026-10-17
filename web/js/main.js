import * as api from "./api.js";
import { createAgent } from "./agent.js";
import { renderDecisions } from "./decisions.js";
import { renderEvidence } from "./evidence.js";
import { renderFleet, rowKey } from "./fleet.js";
import { VERDICT_RANK, esc, factView, plural } from "./format.js";
import { createMap } from "./map.js";
import { initBench } from "./bench.js";
import { refreshWork } from "./work.js";
import { initHood } from "./hood.js";
import { createRail } from "./rail.js";
import { createSpring } from "./spring.js";

const state = { meta: null, snap: null, stop: null, sel: { advisory: null, artifact: null }, tab: "evidence", pinnedTab: false };
const $ = (id) => document.getElementById(id);
const TABS = ["evidence", "graph", "decisions", "ask"];
const params = new URLSearchParams(location.search);
const pinned = { artifact: params.get("artifact") };
let map;

function toast(html) {
  const el = $("toast");
  el.innerHTML = html;
  el.hidden = false;
  el.classList.remove("out");
  void el.offsetWidth; // restart the entrance if one is already showing
  el.classList.add("in");
  clearTimeout(toast.t);
  // it leaves the way it came
  toast.t = setTimeout(() => { el.classList.replace("in", "out"); toast.t = setTimeout(() => (el.hidden = true), 320); }, 6500);
}

/** The selected-tab underline is one element that slides between tabs on two springs (position and width), so a second
 *  tap redirects it mid-flight instead of waiting for it to arrive. */
const ink = { el: null, x: null, w: null };
function initInk() {
  const bar = $("tab-evidence").parentElement;
  ink.el = Object.assign(document.createElement("span"), { className: "tab-ink" });
  ink.el.setAttribute("aria-hidden", "true");
  bar.appendChild(ink.el);
  const apply = () => { ink.el.style.transform = `translate3d(${ink.x.value}px,0,0)`; ink.el.style.width = `${ink.w.value}px`; };
  ink.x = createSpring(0, apply, { damping: 1, response: 0.38 });
  ink.w = createSpring(0, apply, { damping: 1, response: 0.38 });
  addEventListener("resize", () => moveInk(true));
  moveInk(true);
  document.fonts?.ready.then(() => moveInk(true)); // tab widths change when the web font arrives
}
function moveInk(snap = false) {
  const tab = $(`tab-${state.tab}`);
  if (!ink.el || !tab.offsetWidth) return;
  snap ||= ink.w.value === 0;
  snap ? (ink.x.set(tab.offsetLeft), ink.w.set(tab.offsetWidth)) : (ink.x.to(tab.offsetLeft), ink.w.to(tab.offsetWidth));
}

function setTab(name) {
  state.tab = name;
  TABS.forEach((t) => {
    $(`tab-${t}`).setAttribute("aria-selected", String(t === name));
    $(`panel-${t}`).hidden = t !== name;
  });
  if (name === "decisions") refreshWork();
  moveInk();
}

/** Which exposed service to open on: the deepest path is the most instructive, and among equals the richest graph reads best. */
async function richestExposed(rows) {
  const hot = rows.filter((r) => r.verdict === "EXPOSED");
  if (hot.length < 2) return hot[0];
  const sized = await Promise.all(hot.map(async (r) => [r, await map.size(r.artifact)]));
  return sized.sort((a, b) => (b[0].hops ?? 0) - (a[0].hops ?? 0) || b[1] - a[1])[0][0];
}

/** Keep the user's selection if it still exists; otherwise pick the most urgent thing on screen. */
async function reconcileSelection(snap) {
  const advisories = snap.advisories;
  if (!advisories.length) { state.sel = { advisory: null, artifact: null }; return; }
  if (!advisories.some((a) => a.id === state.sel.advisory)) {
    const latestHot = [...advisories].reverse().find((a) => a.counts.EXPOSED > 0);
    state.sel.advisory = (latestHot ?? advisories[advisories.length - 1]).id;
  }
  const adv = advisories.find((a) => a.id === state.sel.advisory);
  if (!adv.rows.some((r) => r.artifact === state.sel.artifact)) {
    const first = (await richestExposed(adv.rows)) ?? [...adv.rows].sort((a, b) => VERDICT_RANK[a.verdict] - VERDICT_RANK[b.verdict])[0];
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
    <button type="button" class="btn" id="review">Review</button></div>`;
  $("review").onclick = () => { state.sel = { advisory: r.advisory, artifact: r.artifact }; setTab("evidence"); render(); $("sheet").focus(); };
}

/** One plain sentence for the moment on screen, so the three panels below have something to be read against. */
function renderStory(snap, sel) {
  const el = $("story");
  const adv = snap.advisories.find((a) => a.id === sel.advisory);
  if (!adv) { el.innerHTML = "Nothing malicious has been published yet, so every service is clear. Press play, or drag the weight down the line."; return; }
  const { EXPOSED: hot, UNKNOWN: unsure, CLEARED: clear } = adv.counts;
  const bits = [`<b class="hot">${plural(hot, "service")}</b> lock${hot === 1 ? "s" : ""} it`];
  if (unsure) bits.push(`<b class="unsure">${unsure}</b> can't be judged without a lockfile`);
  bits.push(`<b class="clear">${clear}</b> ${clear === 1 ? "is" : "are"} clear`);
  el.innerHTML = `<b>${esc(adv.package)}</b> was just poisoned. ${bits.join(", ")}. Pick a service to see how it gets in.`;
}

function render(changed = new Set()) {
  const { snap, sel } = state;
  renderStory(snap, sel);
  const ctx = { live: api.isLive(), queries: state.meta.queries };
  renderFleet(snap, sel, changed, {
    onAdvisory: async (id) => { state.sel.advisory = id; state.sel.artifact = null; await reconcileSelection(snap); render(); },
    onArtifact: (id) => { state.sel.artifact = id; setTab("evidence"); render(); },
  });
  renderEvidence(snap, sel, ctx, { onApprove, onVerify });
  renderDecisions(snap, sel, (advisory, artifact) => { state.sel = { advisory, artifact }; setTab("evidence"); render(); });
  renderNotice(snap);
  map.show(snap, sel);
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
  await reconcileSelection(snap);
  if (state.stop !== stop) return;
  if (newlyReopened.length) {
    state.sel = { advisory: newlyReopened[0].advisory, artifact: newlyReopened[0].artifact };
    if (!state.pinnedTab) setTab("evidence");
  } else if (stop.kind === "advisory") {
    // jump to the newest exposure when a malicious release lands
    const adv = snap.advisories.find((a) => a.id === stop.advisory);
    const hit = adv && (await richestExposed(adv.rows));
    if (state.stop !== stop) return;
    if (adv && hit) state.sel = { advisory: adv.id, artifact: hit.artifact };
  }
  const pin = pinned.artifact;
  pinned.artifact = null; // a link's ?artifact= applies to the first view only
  if (pin) {
    for (const a of snap.advisories) if (a.rows.some((r) => r.artifact === pin && r.verdict === "EXPOSED")) { state.sel = { advisory: a.id, artifact: pin }; break; }
  }
  render(changedRows(prev, snap));
}

function initTheme() {
  const root = document.documentElement;
  const btn = $("theme-btn");
  let stored = null;
  try { stored = localStorage.getItem("plumbline.theme"); } catch { /* storage unavailable */ }
  const wanted = params.get("theme") ?? stored;
  if (wanted === "light" || wanted === "dark") root.dataset.theme = wanted;
  const effective = () => root.dataset.theme ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const paint = () => { btn.dataset.mode = effective(); btn.setAttribute("aria-pressed", String(effective() === "dark")); };
  btn.addEventListener("click", () => {
    root.classList.add("theming"); // ease dark <-> light instead of a hard brightness jump
    clearTimeout(initTheme.t);
    initTheme.t = setTimeout(() => root.classList.remove("theming"), 450);
    root.dataset.theme = effective() === "dark" ? "light" : "dark";
    try { localStorage.setItem("plumbline.theme", root.dataset.theme); } catch { /* storage unavailable */ }
    paint();
    requestAnimationFrame(() => dispatchEvent(new Event("themechange"))); // the canvas reads its colours from CSS
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { paint(); dispatchEvent(new Event("themechange")); });
  paint();
}

/** The nav floats transparent over the red hero, then turns into a frosted white bar once the hero has scrolled away. */
function initNav() {
  const nav = $("nav");
  new IntersectionObserver(([e]) => nav.classList.toggle("solid", !e.isIntersecting), { rootMargin: "-64px 0px 0px 0px" }).observe(document.querySelector(".hero"));
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
  initInk();
  initNav();
  map = createMap();
  const meta = await api.init();
  state.meta = meta;
  initHood(meta);
  initBench();
  $("incident-name").textContent = meta.incident.name;
  const live = api.isLive();
  const mode = $("badge-mode");
  mode.textContent = live ? "Live graph" : "Recorded snapshots";
  mode.classList.toggle("live", live);
  $("badge-agent").textContent = meta.agent.backend === "llm" ? `Agent: ${meta.agent.model}` : "Agent: built-in planner, no model";
  document.querySelector(".tryit-live").hidden = !live;
  document.querySelector(".tryit-static").hidden = live;
  $("nav-check").hidden = !live; // the checker needs the live server
  if (meta.repo) { const a = $("repo-link"); a.href = meta.repo; a.hidden = false; }

  createAgent({ suggestions: meta.suggestions, live, getStop: () => state.stop, ask: api.ask });
  const rail = createRail({ stops: meta.timeline, onChange: onStop });
  // Land on the moment that tells the story (the keyv release) unless the URL names a stop: ?start=N
  const param = params.get("start");
  const story = meta.timeline.find((s) => s.kind === "advisory" && s.label.startsWith("keyv"));
  const start = param !== null ? Number(param) : (story?.index ?? 0);
  rail.drop(start); // the one orchestrated moment: the bob swings onto its knot
  if (param !== null) $("rail-hint")?.classList.add("gone");
  const tab = params.get("tab");
  if (TABS.includes(tab)) { state.pinnedTab = true; setTab(tab); } // a ?tab= link stays on that tab
}

boot().catch((err) => {
  console.error(err);
  $("incident-name").textContent = "Could not load the incident";
  toast(`<b>Load failed.</b> ${esc(err.message)}`);
});
