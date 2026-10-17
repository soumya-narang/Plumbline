// Critically-damped-by-default springs, in Apple's terms: a damping ratio and a response (seconds), not mass/stiffness.
// A spring has no fixed duration. Re-targeting it mid-flight keeps the current value AND velocity, so motion is never cut.

export const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Create a one-dimensional spring.
 * @param {number} value  starting value
 * @param {(v:number)=>void} onUpdate  called every frame with the live (presentation) value
 * @param {{damping?:number, response?:number}} cfg  damping 1 = no overshoot; <1 bounces. response = seconds to arrive.
 */
export function createSpring(value, onUpdate, { damping = 1, response = 0.4 } = {}) {
  let k = 0;
  let c = 0;
  const tune = (d, r) => { const omega = (2 * Math.PI) / r; k = omega * omega; c = 2 * d * omega; };
  const base = { damping, response };
  tune(damping, response);
  let x = value;
  let v = 0; // units per second
  let target = value;
  let raf = 0;
  let last = 0;

  function frame(now) {
    // fixed sub-steps keep the integration stable on slow frames
    let dt = Math.min(0.064, (now - last) / 1000);
    last = now;
    while (dt > 0) {
      const h = Math.min(dt, 1 / 240);
      v += (-k * (x - target) - c * v) * h;
      x += v * h;
      dt -= h;
    }
    if (Math.abs(x - target) < 0.0005 && Math.abs(v) < 0.005) {
      x = target;
      v = 0;
      raf = 0;
      onUpdate(x);
      return;
    }
    onUpdate(x);
    raf = requestAnimationFrame(frame);
  }

  function kick() {
    if (raf) return;
    last = performance.now();
    raf = requestAnimationFrame(frame);
  }

  return {
    /** Animate to a new target from wherever we are now, optionally inheriting a velocity (units/s). */
    to(next, { velocity, damping: d = base.damping, response: r = base.response } = {}) {
      tune(d, r); // a flick can ask for a little bounce; everything else falls back to the critically damped default
      target = next;
      if (velocity != null) v = velocity;
      if (reducedMotion()) { x = next; v = 0; cancelAnimationFrame(raf); raf = 0; onUpdate(x); return; }
      kick();
    },
    /** Jump without animating (used while the finger is down: touch and content move together). */
    set(next) { cancelAnimationFrame(raf); raf = 0; x = target = next; v = 0; onUpdate(x); },
    get value() { return x; },
    get velocity() { return v; },
    get target() { return target; },
    stop() { cancelAnimationFrame(raf); raf = 0; },
  };
}

/** Where a flick will come to rest if it decelerates like scroll does. velocity in units/s; returns a distance. */
export function project(velocity, decelerationRate = 0.998) {
  return ((velocity / 1000) * decelerationRate) / (1 - decelerationRate);
}

/** Progressive resistance past an edge: the further out, the less the element follows. */
export function rubberband(overshoot, dimension, constant = 0.55) {
  const o = Math.abs(overshoot);
  return Math.sign(overshoot) * ((o * dimension * constant) / (dimension + constant * o));
}

/** Keeps the last few samples of a pointer so we know how fast it was moving when released. */
export function velocityTracker(window = 100) {
  let samples = [];
  return {
    add(pos, t = performance.now()) {
      samples.push([pos, t]);
      while (samples.length > 2 && t - samples[0][1] > window) samples.shift();
    },
    /** units per second over the recent window */
    get() {
      if (samples.length < 2) return 0;
      const [p0, t0] = samples[0];
      const [p1, t1] = samples[samples.length - 1];
      return t1 > t0 ? ((p1 - p0) / (t1 - t0)) * 1000 : 0;
    },
    reset() { samples = []; },
  };
}
