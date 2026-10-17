// Materialise-in on scroll: surfaces arrive with a spring-eased blur, rise and scale. Everything stays visible if IntersectionObserver is missing.
const targets = document.querySelectorAll(".chain, .band h2, .band-lede, .deck, .habit, .hood-copy, .hood-code");
if ("IntersectionObserver" in window) {
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
  let habit = 0;
  targets.forEach((el) => {
    el.classList.add("js-reveal");
    if (el.classList.contains("habit")) el.style.setProperty("--rd", `${habit++ * 90}ms`);
    io.observe(el);
  });
}
