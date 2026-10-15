// Small, dependency-free helpers shared by every panel.

const ENTITIES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escape text for safe interpolation into HTML. Everything that comes from data goes through this. */
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ENTITIES[c]);

export const clock = (iso) => iso.slice(11, 19);
export const hhmm = (iso) => iso.slice(11, 16);

/** "pkg:npm/%40cacheable/net@2.1.1" -> "@cacheable/net@2.1.1" */
export const purlLabel = (purl) => decodeURIComponent(String(purl).replace(/^pkg:npm\//, ""));

export const VERDICT_RANK = { EXPOSED: 0, UNKNOWN: 1, CLEARED: 2 };
export const VERDICT_WORD = { EXPOSED: "Exposed", UNKNOWN: "Not determined", CLEARED: "Cleared" };

/** The state marker: solid square exposed, hatched not determined, open circle cleared. */
export const mark = (verdict) => `<i class="mark ${verdict}" aria-hidden="true"></i>`;

export const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Drawings number their revisions with letters; the incident's stops are the revisions. */
export const revLetter = (i) => String.fromCharCode(65 + i);

const REASONS = {
  no_lockfile: {
    title: "No lockfile at the pinned commit",
    body: "Without a lockfile the exact versions this project installs are not determined, so any answer would be a guess.",
    settle: "Commit a lockfile, or resolve the dependency tree and run the survey again.",
  },
  lockfile_format_unsupported: {
    title: "Lockfile format not read",
    body: "A lockfile exists, but this build only reads npm v2 and v3 lockfiles. It is treated as not determined, never as safe.",
    settle: "Add a reader for this format, or supply an npm lockfile.",
  },
};
export const reasonText = (reason) =>
  REASONS[reason] ?? { title: String(reason).replaceAll("_", " "), body: "", settle: "" };

/** Turn a stored assumption (fact id) into plain language. */
export function factView(id) {
  const [kind, ...rest] = id.split(":");
  const key = rest.join(":");
  if (kind === "lock_snapshot") {
    return { label: "The lockfile has not changed since it was pinned", why: `sha256 ${key.slice(0, 12)}…` };
  }
  if (kind === "not_affected") {
    const advisory = key.split(":")[0];
    const version = purlLabel(key.slice(advisory.length + 1));
    return { label: `${version} is not named by ${advisory}`, why: "Stops holding if the advisory is revised to include it." };
  }
  return { label: id, why: "" };
}

export function highlightCypher(text) {
  const keywords = /\b(MATCH|WHERE|WITH|RETURN|ORDER BY|LIMIT|AS|OPTIONAL|UNWIND|MERGE|CREATE|SET|CALL|YIELD|IS NOT NULL|IS NULL|IN|NOT|AND|OR|COUNT|COLLECT|MAX)\b/g;
  return esc(text)
    .split("\n")
    .map((line) => {
      const i = line.indexOf("//");
      const code = i >= 0 ? line.slice(0, i) : line;
      const comment = i >= 0 ? `<span class="c">${line.slice(i)}</span>` : "";
      return code.replace(keywords, '<span class="k">$1</span>') + comment;
    })
    .join("\n");
}

/** Recorded replay approvals are not a person; say so instead of printing a username. */
export const approverLabel = (a) => (a === "replay" ? "the recorded replay" : a);

/** A hash in groups of eight, the way a drawing number is easier to compare by eye. */
export const grouped = (hash, n = 32) => hash.slice(0, n).match(/.{1,8}/g).join(" ");

/**
 * A revision cloud: the scalloped outline a drafter draws around anything that changed on a new revision.
 * Arcs bulge outward around the rectangle; `pathLength="1"` lets one CSS rule animate it being drawn.
 */
export function cloudSvg(w, h, scallop = 13) {
  const pad = 9;
  const W = w + pad * 2;
  const H = h + pad * 2;
  const r = scallop * 0.62;
  const edge = (len) => Math.max(2, Math.round(len / scallop));
  const pts = [];
  const along = (x0, y0, x1, y1, n) => {
    for (let i = 0; i < n; i++) pts.push([x0 + ((x1 - x0) * i) / n, y0 + ((y1 - y0) * i) / n]);
  };
  along(0, 0, W, 0, edge(W));
  along(W, 0, W, H, edge(H));
  along(W, H, 0, H, edge(W));
  along(0, H, 0, 0, edge(H));
  let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < pts.length; i++) {
    const [x, y] = pts[(i + 1) % pts.length];
    d += ` A${r.toFixed(1)} ${r.toFixed(1)} 0 0 0 ${x.toFixed(1)} ${y.toFixed(1)}`;
  }
  return `<svg class="cloud" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-hidden="true"><path d="${d}" pathLength="1"/></svg>`;
}

/** Draw a revision cloud around every element marked data-cloud, sized to its box after layout. */
export function attachClouds(root) {
  requestAnimationFrame(() => {
    root.querySelectorAll("[data-cloud]").forEach((el) => {
      el.querySelector(":scope > .cloud")?.remove();
      const { width, height } = el.getBoundingClientRect();
      if (width < 4) return;
      el.insertAdjacentHTML("beforeend", cloudSvg(width, height));
    });
  });
}
