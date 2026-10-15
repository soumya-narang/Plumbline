import { clock, esc } from "./format.js";

const KIND_LABEL = { start: "start", advisory: "publish", approval: "approve", revision: "revised*" };

function shortLabel(stop) {
  if (stop.kind === "advisory") return stop.label.replace(" published", "").split("/").pop();
  if (stop.kind === "approval") return stop.artifact.split("/").pop();
  return KIND_LABEL[stop.kind];
}

export function createTimeline({ stops, onChange }) {
  const rail = document.getElementById("tl-rail");
  const prev = document.getElementById("tl-prev");
  const next = document.getElementById("tl-next");
  const play = document.getElementById("tl-play");
  const label = document.getElementById("tl-label");
  const clockEl = document.getElementById("tl-clock");
  let index = 0;
  let timer = null;

  rail.innerHTML = stops
    .map(
      (s) => `<li class="stop ${s.kind}" data-i="${s.index}">
        <button type="button" aria-label="${esc(s.label)} at ${clock(s.at)} UTC${s.scripted ? " (hypothetical)" : ""}">
          <span class="dot"></span><span class="t">${clock(s.at)}</span><span class="k" title="${esc(s.label)}">${esc(shortLabel(s))}</span>
        </button></li>`,
    )
    .join("");

  function paint() {
    const stop = stops[index];
    rail.querySelectorAll(".stop").forEach((el, i) => {
      el.classList.toggle("passed", i <= index);
      el.classList.toggle("current", i === index);
      el.querySelector("button").setAttribute("aria-current", i === index ? "step" : "false");
    });
    clockEl.textContent = clock(stop.at);
    label.textContent = stop.scripted ? `${stop.label} · scripted` : stop.label;
    prev.disabled = index === 0;
    next.disabled = index === stops.length - 1;
  }

  function go(i, { announce = true } = {}) {
    index = Math.max(0, Math.min(stops.length - 1, i));
    paint();
    if (announce) onChange(stops[index], index);
  }

  function stopPlaying() {
    clearInterval(timer);
    timer = null;
    play.textContent = "▶";
    play.setAttribute("aria-label", "Play the incident");
  }

  function startPlaying() {
    if (index === stops.length - 1) go(0);
    play.textContent = "❚❚";
    play.setAttribute("aria-label", "Pause");
    timer = setInterval(() => {
      if (index >= stops.length - 1) return stopPlaying();
      go(index + 1);
    }, 2200);
  }

  rail.addEventListener("click", (e) => {
    const li = e.target.closest(".stop");
    if (li) {
      stopPlaying();
      go(Number(li.dataset.i));
    }
  });
  prev.addEventListener("click", () => { stopPlaying(); go(index - 1); });
  next.addEventListener("click", () => { stopPlaying(); go(index + 1); });
  play.addEventListener("click", () => (timer ? stopPlaying() : startPlaying()));
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "ArrowRight") { stopPlaying(); go(index + 1); }
    if (e.key === "ArrowLeft") { stopPlaying(); go(index - 1); }
  });

  return { go, current: () => stops[index], stopPlaying };
}
