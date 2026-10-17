// Depth ruler: the page is itself a dependency chain. Four ticks (question, replay, method, graph) and a small bob that
// springs to whichever "hop" you are reading. Only drawn on wide screens, where the gutter has room for it.
import { createSpring } from "./spring.js";

const rail = document.getElementById("depth");
const bob = document.getElementById("depth-bob");
const sections = [".hero", "#replay", "#how", "#hood"].map((q) => document.querySelector(q));
if (rail && bob && sections.every(Boolean)) {
  const ticks = [...rail.querySelectorAll(".depth-tick")];
  let height = 0;
  const spring = createSpring(0, (y) => { bob.style.transform = `translate(-50%, ${y}px)`; }, { damping: 0.8, response: 0.5 });
  let current = -1;

  const measure = () => { height = rail.querySelector(".depth-line").getBoundingClientRect().height; spring.set(Math.max(0, current) * (height / 3)); };
  const pick = () => {
    const line = innerHeight * 0.4;
    let hop = 0;
    sections.forEach((s, i) => { if (s.getBoundingClientRect().top <= line) hop = i; });
    if (hop === current) return;
    current = hop;
    ticks.forEach((t, i) => t.classList.toggle("on", i <= hop));
    spring.to(hop * (height / 3));
  };
  let queued = false;
  addEventListener("scroll", () => { if (queued) return; queued = true; requestAnimationFrame(() => { queued = false; pick(); }); }, { passive: true });
  addEventListener("resize", () => { measure(); pick(); });
  measure();
  pick();
}
