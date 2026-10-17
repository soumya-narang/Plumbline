// The plumb bob in the hero is a real pendulum. Grab it and it follows your pointer around its pivot; let go and a spring swings it
// back to hanging straight, carrying the speed you released it at, so it overshoots and settles like a weight on a string.
import { createSpring, velocityTracker, reducedMotion } from "./spring.js";

const bob = document.querySelector(".swing");
if (bob) {
  const svg = bob.querySelector("svg");
  const MAX = 75; // degrees; a string can't swing past horizontal
  const tracker = velocityTracker(90);
  let pivot = { x: 0, y: 0 };
  let angle = 0;
  const spring = createSpring(0, (a) => { angle = a; bob.style.transform = `rotate(${a}deg)`; }, { damping: 0.28, response: 1.15 });

  bob.style.cursor = "grab";
  bob.style.touchAction = "none";
  bob.style.pointerEvents = "auto";

  const toAngle = (e) => {
    const dx = e.clientX - pivot.x;
    const dy = Math.max(24, e.clientY - pivot.y);
    return Math.max(-MAX, Math.min(MAX, (Math.atan2(-dx, dy) * 180) / Math.PI));
  };

  bob.addEventListener("pointerdown", (e) => {
    bob.setPointerCapture(e.pointerId);
    const r = bob.getBoundingClientRect();
    pivot = { x: r.left + r.width / 2, y: r.top }; // transform-origin is the top centre, so that is the pivot
    // start from what is on screen right now, not from where the entry animation was heading
    const live = getComputedStyle(bob).transform;
    if (live && live !== "none") { const [a, b] = live.slice(7, -1).split(",").map(Number); angle = (Math.atan2(b, a) * 180) / Math.PI; }
    bob.style.animation = "none";
    spring.set(angle);
    tracker.reset();
    bob.style.cursor = "grabbing";
    svg.style.transform = "scale(1.08)";
    e.preventDefault();
  });
  bob.addEventListener("pointermove", (e) => {
    if (!bob.hasPointerCapture(e.pointerId)) return;
    const a = toAngle(e); // already in CSS rotate terms: a pointer to the right gives a negative (counter-clockwise) angle
    tracker.add(a);
    spring.set(a);
  });
  const release = (e) => {
    if (!bob.hasPointerCapture(e.pointerId)) return;
    bob.releasePointerCapture(e.pointerId);
    bob.style.cursor = "grab";
    svg.style.transform = "";
    const v = Math.max(-900, Math.min(900, tracker.get()));
    spring.to(0, { velocity: reducedMotion() ? 0 : v });
  };
  bob.addEventListener("pointerup", release);
  bob.addEventListener("pointercancel", release);
}
