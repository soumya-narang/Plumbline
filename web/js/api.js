// Data layer. Talks to the live API when one answers, otherwise reads the exported snapshots.
// Both produce exactly the same shapes, so the rest of the UI never needs to know which it is using.

let mode = "static";
const staticCache = new Map();

async function getJson(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const detail = await res.json().then((b) => b.detail, () => null); // the server's reason, when it gave one
    throw new Error(typeof detail === "string" ? detail : `${url}: ${res.status}`);
  }
  return res.json();
}

export const isLive = () => mode === "live";

export async function init() {
  try {
    const res = await fetch("api/meta");
    if (res.ok && (res.headers.get("content-type") || "").includes("json")) {
      mode = "live";
      return await res.json();
    }
  } catch {
    /* no backend: fall through to the static export */
  }
  mode = "static";
  return getJson("data/meta.json");
}

export async function getSnapshot(stop) {
  if (mode === "live") return getJson(`api/snapshot?at=${encodeURIComponent(stop.at)}`);
  if (!staticCache.has(stop.index)) staticCache.set(stop.index, await getJson(`data/snapshots/${stop.index}.json`));
  return staticCache.get(stop.index);
}

export async function ask(question, stop) {
  if (mode === "live") {
    return getJson("api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, at: stop.at }),
    });
  }
  const recorded = await getJson(`data/agent/${stop.index}.json`);
  if (!(question in recorded)) throw new Error("Only the suggested questions are available in the static site.");
  return recorded[question];
}

export async function approve(advisory, artifact, stop, approver) {
  return getJson("api/approve", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ advisory, artifact, at: stop.at, approver }),
  });
}

export async function verifyReceipt(advisory, artifact, stop) {
  const receipt = await getJson(
    `api/receipt?advisory=${encodeURIComponent(advisory)}&artifact=${encodeURIComponent(artifact)}&at=${encodeURIComponent(stop.at)}`,
  );
  return getJson("api/verify", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(receipt),
  });
}

export async function getGraph(artifact) {
  if (mode === "live") return getJson(`api/graph?artifact=${encodeURIComponent(artifact)}`);
  return getJson(`data/graphs/${artifact.replace("/", "__")}.json`);
}

/** Namespace form, for modules that prefer `api.getGraph(...)`. */
export const api = { getGraph, isLive };
