// "What if the advisory grows?" Lets a visitor add a version to an advisory as of the moment on screen and watch which
// decisions reopen. The revision is theirs alone, hypothetical, and never written to the recorded incident.
import { esc } from "./format.js";
import { isLive } from "./api.js";

const root = document.getElementById("whatif");

export function renderWhatIf(snap, { onRevise, onClear }) {
  if (!root) return;
  if (!isLive()) { root.innerHTML = ""; return; }
  const mine = snap.events.filter((e) => e.visitor);
  const advisories = snap.advisories;
  if (!advisories.length) { root.innerHTML = ""; return; }

  root.innerHTML = `<h4 class="wq-head">Try a what-if</h4>
    <p class="dnote">Suppose an advisory also named another version, starting at the time on the clock. Any decision that assumed otherwise reopens. This is hypothetical and only you see it.${snap.decisions.length ? "" : " There are no decisions yet at this moment, so step the timeline forward past the approvals first."}</p>
    <form class="whatif" id="whatif-form">
      <label class="sr" for="wi-adv">Advisory</label>
      <select id="wi-adv">${advisories.map((a) => `<option value="${esc(a.id)}">${esc(a.package)} · ${esc(a.id)}</option>`).join("")}</select>
      <label class="sr" for="wi-ver">Version to add</label>
      <input id="wi-ver" placeholder="6.0.1" maxlength="30" autocomplete="off" pattern="\\d+\\.\\d+\\.\\d+(-[0-9A-Za-z.]+)?" required>
      <button class="btn" type="submit">Add version</button>
    </form>
    <p class="wi-msg" id="wi-msg" role="status"></p>
    ${mine.length ? `<ul class="wlist">${mine.map((e) => `<li class="witem"><span class="wtag">what-if</span><span class="who">${esc(e.add_purls.map((p) => p.replace("pkg:npm/", "")).join(", "))}</span><span class="by">added to ${esc(e.advisory)}, hypothetical</span></li>`).join("")}</ul>
    <button class="link" id="wi-clear" type="button">Remove my what-ifs</button>` : ""}`;

  const msg = root.querySelector("#wi-msg");
  root.querySelector("#whatif-form").onsubmit = async (e) => {
    e.preventDefault();
    msg.textContent = "";
    try {
      await onRevise(root.querySelector("#wi-adv").value, root.querySelector("#wi-ver").value.trim());
    } catch (err) {
      msg.textContent = err.message;
    }
  };
  root.querySelector("#wi-clear")?.addEventListener("click", onClear);
}
