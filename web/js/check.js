const $ = (id) => document.getElementById(id);
let tenant = null;

const SAMPLE_NOTES = {
  "exposed-hand-authored.json": "A small lockfile written for the demo. keyv 6.0.0 sits three packages below the dependency you chose.",
  "exposed-real-nodemailer-edited.json": "nodemailer's real lockfile (180 packages). Its keyv was 4.5.4, safe; this copy changes that one version to the poisoned 6.0.0. The path is real: eslint, file-entry-cache, flat-cache, keyv. You can confirm it with npm (see the README); npm also complains that 6.0.0 breaks flat-cache's version range, which is what a hand edit looks like.",
  "clear-real-nodemailer.json": "nodemailer's real lockfile, untouched. It does contain keyv (4.5.4), so a naive text search would flag it; the graph says it is not an affected version.",
};

const WHY = {
  affected_version_locked: "An affected version is locked in this project.",
  safe_version_locked: "The package is here, but at a version the advisory does not name.",
  package_absent: "The package is not in this lockfile.",
  no_lockfile: "No lockfile, so this cannot be decided.",
  lockfile_format_unsupported: "This lockfile format cannot be read.",
};
const ASSUME = {
  lock_snapshot: "Assumes the lockfile matches what is deployed.",
  not_affected: "Assumes the advisory's list of affected versions is complete.",
};

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}
const svgEl = (tag, attrs = {}) => {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

/** Draws only the installs on a poisoned path, left to right from the direct dependency to the poisoned version. */
function drawPaths(exposed, graph) {
  const byKey = new Map(graph.nodes.map((n) => [n[0], n]));
  const col = new Map();
  const edges = new Set();
  for (const f of exposed) {
    f.path_keys.forEach((k, i) => {
      col.set(k, Math.max(col.get(k) ?? 0, i));
      if (i) edges.add(f.path_keys[i - 1] + "\u0000" + k);
    });
  }
  const cols = [];
  for (const [k, c] of col) (cols[c] ||= []).push(k);
  const W = 190, H = 58, X0 = 16, Y0 = 20;
  const width = X0 * 2 + cols.length * W;
  const height = Y0 * 2 + Math.max(...cols.map((c) => c.length)) * H;
  const svg = svgEl("svg", { class: "g", viewBox: `0 0 ${width} ${height}`, role: "img",
    "aria-label": "Dependency paths from your direct dependencies to the poisoned versions" });
  const pos = new Map();
  cols.forEach((keys, c) => keys.forEach((k, r) => pos.set(k, [X0 + c * W, Y0 + r * H])));
  for (const e of edges) {
    const [a, b] = e.split("\u0000").map((k) => pos.get(k));
    svg.append(svgEl("path", { class: "edge", d: `M${a[0] + 150} ${a[1] + 18} C${a[0] + 170} ${a[1] + 18} ${b[0] - 20} ${b[1] + 18} ${b[0]} ${b[1] + 18}` }));
  }
  const bad = new Set(exposed.map((f) => f.path_keys.at(-1)));
  for (const [k, [x, y]] of pos) {
    const n = byKey.get(k);
    const g = svgEl("g");
    g.append(svgEl("rect", { class: "n" + (bad.has(k) ? " bad" : ""), x, y, width: 150, height: 36, rx: 8 }));
    const t = svgEl("text", { x: x + 10, y: y + 15 }); t.textContent = (n?.[1] ?? k).slice(0, 22);
    const s = svgEl("text", { class: "sub", x: x + 10, y: y + 28 }); s.textContent = n ? n[2] : "";
    g.append(t, s); svg.append(g);
  }
  return svg;
}

function show(r, graph) {
  tenant = r.tenant;
  const exposed = r.findings.filter((f) => f.verdict === "EXPOSED");
  const unknown = r.findings.filter((f) => f.verdict === "UNKNOWN");
  const head = el("div", "headline " + (exposed.length ? "hot" : unknown.length ? "unsure" : "cold"));
  if (exposed.length) {
    const fix = [...new Set(exposed.flatMap((f) => f.pulled_by || []))];
    head.append(el("b", null, "Exposed: the poisoned release is in this project"),
      el("span", null, `${exposed.length} affected ${exposed.length === 1 ? "package" : "packages"} locked. ` + (fix.length ? `Bump ${fix.join(", ")} to remove the way in.` : "")));
  } else if (unknown.length) {
    head.append(el("b", null, "Could not be decided"), el("span", null, "See the findings below for what is missing."));
  } else {
    head.append(el("b", null, "Clear: none of the poisoned versions are locked"),
      el("span", null, `Checked ${r.packages} installed packages against ${r.findings.length} affected packages from the incident.`));
  }
  $("headline").replaceChildren(head);

  $("stats").replaceChildren(
    ...[`${r.packages} installs in the graph`, `${r.work.graph.requirements} requirement edges`, `${r.findings.length} advisories checked`].map((t) => el("span", null, t)));

  const list = $("list"); list.replaceChildren();
  const cleared = el("details", "cleared");
  const order = { EXPOSED: 0, UNKNOWN: 1, CLEARED: 2 };
  for (const f of [...r.findings].sort((a, b) => order[a.verdict] - order[b.verdict])) {
    const card = el("div", "f");
    const h = el("h3"); h.append(el("span", "tag " + f.verdict, f.verdict), el("span", "mono", f.package), el("span", "note", f.advisory));
    card.append(h);
    if (f.path && f.path.length) card.append(el("div", "path", f.path.join("  →  ")));
    card.append(el("p", null, WHY[f.reason] || f.reason));
    if (f.verdict === "CLEARED" && f.evidence && f.evidence.length)
      card.append(el("p", null, "Locked: " + f.evidence.map((e) => `${e.name}@${e.version}`).join(", ") + "."));
    if (f.pulled_by && f.pulled_by.length) card.append(el("div", "fix", "Pulled in by " + f.pulled_by.join(", ") + "."));
    if (f.verdict !== "UNKNOWN" && f.assumptions && f.assumptions.length)
      card.append(el("p", null, [...new Set(f.assumptions.map((a) => ASSUME[a.kind] || a.kind))].join(" ")));
    (f.verdict === "CLEARED" ? cleared : list).append(card);
  }
  const nClear = r.findings.filter((f) => f.verdict === "CLEARED").length;
  if (nClear) {
    cleared.prepend(el("summary", null, `${nClear} cleared ${nClear === 1 ? "advisory" : "advisories"}`));
    if (!exposed.length && !unknown.length) cleared.open = true;
    list.append(cleared);
  }

  const gw = $("graphwrap"); gw.replaceChildren();
  const q = $("queries"); q.replaceChildren();
  $("gh").hidden = false;
  if (exposed.length) {
    gw.append(el("p", "note", "The installs on the poisoned paths, as returned by the path query. Everything else in your graph was not touched."));
    gw.append(drawPaths(exposed, graph));
  } else {
    gw.append(el("p", "note", `The match query ran over all ${r.packages} installs and found no install of an affected version, so the path query had nothing to follow.`));
  }
  q.append(el("p", "note", "These Cypher queries ran against your graph for each advisory (queries/ in the repository):"));
  for (const w of r.work.queries) {
    const h = el("h4", null, w.name + " "); h.append(el("span", null, "– " + w.role));
    q.append(h, el("pre", null, w.cypher));
  }

  $("meta").textContent = `Expires ${new Date(r.expires).toLocaleTimeString()}`;
  $("out").style.display = "block";
  $("out").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function call(url, opts) {
  const res = await fetch(url, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `request failed (${res.status})`);
  return body;
}

$("go").onclick = async () => {
  const err = $("err"); err.style.display = "none";
  if (tenant) { call("/api/check/" + tenant, { method: "DELETE" }).catch(() => {}); tenant = null; }
  $("go").disabled = true;
  try {
    const r = await call("/api/check", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ lockfile: $("lock").value, label: $("label").value }) });
    show(r, await call(`/api/check/${r.tenant}/graph`));
  } catch (e) { err.textContent = e.message; err.style.display = "block"; }
  $("go").disabled = false;
};

$("del").onclick = async () => {
  if (!tenant) return;
  await call("/api/check/" + tenant, { method: "DELETE" }).catch(() => {});
  tenant = null; $("out").style.display = "none";
};

$("file").onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  $("lock").value = await f.text();
  $("sample-note").textContent = `Loaded ${f.name} (${Math.round(f.size / 1024)} KB).`;
};

$("sample").onchange = async (e) => {
  const name = e.target.value;
  if (!name) return;
  $("lock").value = await (await fetch("samples/" + name)).text();
  $("sample-note").textContent = SAMPLE_NOTES[name];
  $("label").value = name.replace(/\.json$/, "");
};
