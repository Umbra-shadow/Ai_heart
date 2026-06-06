// Guardianity hackathon demo — UI logic (chat · heart on/off · read-only settings).
const $ = (s) => document.querySelector(s);
const log = $("#log"), form = $("#form"), text = $("#text"),
      send = $("#send"), heart = $("#heart"), heartState = $("#heartState"),
      statusEl = $("#status"), settingsEl = $("#settings"), thinkingEl = $("#thinking"),
      warmth = $("#warmth"), warmthVal = $("#warmthVal");

heart.addEventListener("change", () => {
  heartState.textContent = heart.checked ? "ON" : "OFF";
});

// Live feeling dial — updates the label as you drag; the value rides with each
// turn (no reload). 0 = raw vessel, higher = stronger feeling steering.
if (warmth) warmth.addEventListener("input", () => {
  warmthVal.textContent = parseFloat(warmth.value).toFixed(2).replace(/\.00$/, ".0");
});

function add(role, body, meta) {
  const el = document.createElement("div");
  el.className = "msg " + role;
  if (meta) el.classList.add(meta.cls || "");
  if (meta && meta.tag) {
    const t = document.createElement("span");
    t.className = "tag"; t.textContent = meta.tag; el.appendChild(t);
  }
  el.appendChild(document.createTextNode(body));
  log.appendChild(el); log.scrollTop = log.scrollHeight;
  return el;
}

async function poll() {
  try {
    const s = await (await fetch("/api/status")).json();
    const badge = $("#modeBadge");
    if (badge) badge.textContent = "vessel: " + (s.mode || "?") + " · " + (s.vessel || "");
    if (s.ready) { statusEl.textContent = "ready · " + (s.vessel || "") + " · " + (s.mode || ""); statusEl.className = "status ok"; }
    else if (s.error) { statusEl.textContent = "error: " + s.error; statusEl.className = "status err"; }
    else { statusEl.textContent = "waking — loading the model…"; statusEl.className = "status"; }
  } catch (e) { statusEl.textContent = "server unreachable"; statusEl.className = "status err"; }
}

async function loadSettings() {
  try {
    const s = await (await fetch("/api/settings")).json();
    settingsEl.innerHTML = "";
    for (const [k, v] of Object.entries(s)) {
      const row = document.createElement("div"); row.className = "row";
      row.innerHTML = `<span class="k">${k}</span><span class="v">${String(v)}</span>`;
      settingsEl.appendChild(row);
    }
  } catch (e) { settingsEl.textContent = "settings unavailable"; }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = text.value.trim(); if (!msg) return;
  add("you", msg);
  text.value = ""; send.disabled = true;
  const thinking = add("bot", "…", { cls: "gov", tag: heart.checked ? "heart · thinking" : "raw vessel · thinking" });
  try {
    const r = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: msg, heart_on: heart.checked,
                             warmth_coef: warmth ? parseFloat(warmth.value) : undefined }),
    });
    const d = await r.json();
    thinking.remove();
    // the model's reasoning goes to the side panel (latest turn only — it replaces,
    // it does not pile up); the chat shows just the answer.
    if (thinkingEl) thinkingEl.textContent = (d.thinking && d.thinking.trim()) ? d.thinking : "—";
    if (d.error) { add("bot", d.error, { cls: "refused", tag: "error" }); }
    else {
      let tag;
      if (!d.heart_on) tag = "raw vessel (heart off)";
      else if (d.refused) tag = "heart · refused-with-care (" + d.decision + ")";
      else tag = "heart · " + (d.decision || "allow");
      if (d.offline) tag += " · ⚠ heart offline (bypassed)";
      if (typeof d.elapsed === "number") tag += " · " + d.elapsed + "s";
      const cls = d.refused ? "refused" : (d.heart_on ? "gov" : "raw");
      add("bot", d.reply || "(empty)", { cls, tag });
    }
  } catch (err) {
    thinking.remove();
    add("bot", "request failed: " + err, { cls: "refused", tag: "error" });
  } finally { send.disabled = false; text.focus(); }
});

poll(); loadSettings();
setInterval(poll, 4000);
setInterval(loadSettings, 8000);
