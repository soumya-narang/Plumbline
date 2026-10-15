// Small, dependency-free helpers shared by every panel.

const ENTITIES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escape text for safe interpolation into HTML. Everything that comes from data goes through this. */
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ENTITIES[c]);

export const clock = (iso) => iso.slice(11, 19);

export const PIN = `<svg class="pin" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M9.5 1.5l5 5-2 .8-2.6 2.6.3 3.1-1 1-3-3-4 4-.8-.8 4-4-3-3 1-1 3.1.3L9.7 3.5z" fill="currentColor"/></svg>`;

/** "pkg:npm/%40cacheable/net@2.1.1" -> "@cacheable/net@2.1.1" */
export const purlLabel = (purl) => decodeURIComponent(String(purl).replace(/^pkg:npm\//, ""));

export const VERDICT_RANK = { EXPOSED: 0, UNKNOWN: 1, CLEARED: 2 };

const REASONS = {
  no_lockfile: {
    title: "No lockfile at the pinned commit",
    body: "Without a lockfile the exact versions this project installs are not determined, so any answer would be a guess.",
    settle: "Commit a lockfile, or resolve the dependency tree and re-run.",
  },
  lockfile_format_unsupported: {
    title: "Lockfile format not parsed",
    body: "A lockfile exists, but this build only reads npm v2/v3 lockfiles. It is treated as unknown, never as safe.",
    settle: "Add a parser for this format, or supply an npm lockfile.",
  },
};
export const reasonText = (reason) =>
  REASONS[reason] ?? { title: String(reason).replaceAll("_", " "), body: "", settle: "" };

/** Turn a stored assumption (fact id) into plain language. */
export function factView(id) {
  const [kind, ...rest] = id.split(":");
  const key = rest.join(":");
  if (kind === "lock_snapshot") {
    return { label: "The lockfile has not changed", why: `Pinned lockfile sha256 ${key.slice(0, 10)}…` };
  }
  if (kind === "not_affected") {
    const advisory = key.split(":")[0];
    const version = purlLabel(key.slice(advisory.length + 1));
    return { label: `${version} is not named by ${advisory}`, why: "Breaks if the advisory is revised to include it." };
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

export const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Recorded replay approvals are not a person; say so instead of printing a username. */
export const approverLabel = (a) => (a === "replay" ? "the recorded replay" : a);
