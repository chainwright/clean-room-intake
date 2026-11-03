// Clean Room Intake front end (direction A + B's postmarks and receipt stubs). No framework.
// The room finishes in tenths of a second; the page reveals each step with a short dwell so a person can follow it.
// The real timings stay in the text (+0.15 s), so the speed is never faked.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const money = (v) => (v == null ? "—" : "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const hhmmss = (t) => new Date(t * 1000).toLocaleTimeString("en-US", { hour12: false });
const DWELL = { state: 500, attempt: 700 };
let current = null, timer = null, ticker = null, view = null;

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.detail || r.statusText), { status: r.status });
  return body;
}

// a file that couldn't be read ends in "destroyed" like any other: look for "failed" anywhere in its history
const failedOf = (j) => (j.states || []).some((s) => s.state === "failed");

// ---------- what a file tried, in words ----------
const attemptsOf = (j) => (j.tries || []).flatMap((t) => t.receipt.attempts);
function host(detail) {
  const m = /https?:\/\/([^\/'"]+)/.exec(detail) || /\('([^']+)',\s*\d+/.exec(detail);
  return m ? m[1] : "an address";
}
function describe(a) {
  if (a.what === "getenv") return `tried to read ${a.detail} · nothing there`;
  if (a.what === "browser") return /[?&]d=/.test(a.detail) ? `the page tried to send its title to ${host(a.detail)}`
    : /\.(png|gif|jpe?g|svg|webp)/i.test(a.detail) ? `the page tried to load an image from ${host(a.detail)}`
    : `the page tried to reach ${host(a.detail)}`;
  if (a.what.startsWith("socket") || a.what === "urllib.Request") return `tried to reach ${host(a.detail)}`;
  if (a.what === "open") return `tried to open ${a.detail} · read-only room`;
  return `tried ${a.what} · stopped`;
}
const distinct = (j) => [...new Set(attemptsOf(j).map(describe))];

// ---------- sample inbox and upload ----------
const label = (n) => ({ bonneville: "Bonneville", granite: "Granite Peak", jordan: "Jordan River (test)", red: "Red Butte (scan)",
  wasatch: "Wasatch (test, HTML)", damaged: "Damaged PDF" })[n.split("_")[0]] || n;
async function loadSamples() {
  const names = (await api("/api/samples")).filter((n) => !(n.endsWith(".docx") && n.startsWith("granite")));  // the .eml carries it
  $("samples").innerHTML = names.map((n) => `<button data-s="${esc(n)}">${esc(label(n))}</button>`).join("·");
  $("samples").onclick = (e) => { e.stopPropagation(); const s = e.target.dataset.s; if (s) start({ sample: s }); };
}
const drop = $("drop");
$("breakin").onclick = async (e) => {
  e.stopPropagation();
  try { follow((await api("/api/breakin", { method: "POST" })).id); } catch (err) { deny(err); }
};
drop.onclick = (e) => { if (e.target === drop) $("file").click(); };
$("file").onchange = (e) => e.target.files[0] && upload(e.target.files[0]);
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]); };
async function upload(file) {
  const fd = new FormData(); fd.append("file", file);
  try { follow((await api("/api/intake", { method: "POST", body: fd })).id); } catch (e) { deny(e); }
}
// a refusal (busy, over the hourly share, file too big) is said in one plain line under the drop zone
function deny(e) {
  let n = $("deny");
  if (!n) { n = document.createElement("p"); n.id = "deny"; n.className = "deny"; drop.after(n); }
  n.textContent = e.message || "Something went wrong. Try again in a moment."; clearTimeout(n.t); n.t = setTimeout(() => n.remove(), 8000);
}
async function start(body) {
  try { follow((await api("/api/intake", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).id); }
  catch (e) { deny(e); }
}

// ---------- following one file: fetch fast, reveal at a human pace ----------
function follow(id, instant = false) {
  current = id; view = { j: null, beats: [], shown: 0, last: 0, instant, filled: false, phase: null, reached: new Set() };
  $("log").className = "log"; $("log").style.display = ""; $("log").innerHTML = ""; $("drawer").style.top = ""; $("pins").innerHTML = ""; $("stub").innerHTML = ""; $("drawer").classList.remove("out");
  $("slip").className = "slip"; $("slip").innerHTML = "";
  clearInterval(timer); clearInterval(ticker);
  timer = setInterval(() => poll(id), 300); poll(id);
  ticker = setInterval(tick, 50);
  refreshQueue();
}
async function poll(id) {
  const j = await api(`/api/intake/${id}`);
  if (id !== current) return;
  view.j = j; view.beats = beats(j);
  if (j.done) clearInterval(timer);
}

// every step the page will show, in order: states, with the file's attempts while it was open
function beats(j) {
  if (j.kind === "breakin") return breakinBeats(j);
  const out = [], perTry = (j.tries || []).map((t) => [...new Set((t.receipt.attempts || []).map(describe))]);
  let room = -1;
  for (const s of j.states.slice(1)) {
    if (s.state === "opening") {            // each attempt lands under the room that made it (a retry gets a new room)
      room++;
      out.push({ kind: "state", state: s.state, at: s.at });
      (perTry[room] || []).forEach((d) => out.push({ kind: "attempt", text: d, at: s.at }));
      continue;
    }
    if (s.state === "extracting") {
      const hid = (j.notes || []).find((n) => /instruction/i.test(n));
      if (hid) out.push({ kind: "state", note: "hidden instructions inside the file · read as data, not obeyed", at: s.at });
    }
    if (s.state === "retry") {             // say WHY the last step failed: the error the room handed back
      const prev = (j.tries || [])[room]?.receipt,
        why = s.why || (prev?.error ? prev.error.split(":")[0] : prev ? "no readable text" : "");
      out.push({ kind: "state", state: s.state, at: s.at, why });
      continue;
    }
    out.push({ kind: "state", state: s.state, at: s.at });
  }
  return out;
}

// break-in test: each room's attacks land before that room is killed; the outcome is what really happened
function breakinBeats(j) {
  const out = [], rooms = (j.tries || []).map((t) => t.receipt.room);
  let k = 0;
  for (const s of j.states.slice(1)) {
    if (s.state === "breakin") {
      const room = rooms[k], r = j.tries[k]?.receipt; k++;
      (j.probes || []).filter((p) => p.room === room).forEach((p) => out.push({ kind: "attempt", probe: p, at: s.at }));
      if (r) out.push({ kind: "state", state: "room_end", note2: r.exit_code === 137 ? `room killed by its own memory cap (exit 137) · next room`
        : r.exit_code ? `room stopped by its own caps (exit ${r.exit_code})` : "room closed", at: s.at });
      continue;
    }
    out.push({ kind: "state", state: s.state, at: s.at });
  }
  return out;
}
const probeLine = (p) => `${p.attack} · ${p.outcome}`;

function tick() {
  const v = view; if (!v || !v.j) return;
  const next = v.beats[v.shown];
  const now = performance.now();
  if (next && (v.instant || now - v.last >= DWELL[next.kind])) { v.shown++; v.last = now; render(); }
  if (!next && v.j.done && v.shown >= v.beats.length && !v.filled) { v.filled = true; render(); finish(); }
}

// ---------- the room (right) ----------
const WORDS = { writing_step: "the model writes the extraction step · Vultr Serverless Inference", reading_fields: "the model reads the fields from the text, as data",
  sandbox_up: "room up · gVisor on Vultr · no network · no secrets", opening: "file handed in, read-only", retry: "step failed, the model rewrites it",
  extracting: "only text passed through the drawer", extracted: "fields read", failed: "couldn't read the file", destroyed: "room destroyed ✓" };

function render() {
  const v = view, j = v.j, t0 = j.states[0].at, rel = (t) => `+${(t - t0).toFixed(2)} s`;
  const shown = v.beats.slice(0, v.shown), tried = shown.filter((b) => b.kind === "attempt");
  let last = null, html = "";
  for (const b of shown) {
    if (b.kind === "attempt" && b.probe) {
      html += `<span class="t">${b.probe.t != null ? "+" + Number(b.probe.t).toFixed(2) + " s" : ""}</span>` +
        (b.probe.held ? `<span class="m x">✕ ${esc(probeLine(b.probe))}</span>` : `<span class="m got">⚠ ${esc(probeLine(b.probe))} · GOT THROUGH</span>`);
      continue;
    }
    if (b.kind === "attempt") { html += `<span class="t"></span><span class="m x">✕ ${esc(b.text)}</span>`; continue; }
    if (b.note2) { html += `<span class="t"></span><span class="m dim">${esc(b.note2)}</span>`; continue; }
    if (b.note) { html += `<span class="t"></span><span class="m n">✕ ${esc(b.note)}</span>`; continue; }
    const t = rel(b.at), msg = b.state === "blocked" ? `fields read · ${tried.length} attempt${tried.length === 1 ? "" : "s"} stopped`
      : b.state === "writing_step" && j.model ? `${j.model} writes the extraction step · Vultr Serverless Inference`
      : b.state === "retry" && b.why ? `step failed: ${b.why} · the model rewrites it` : (WORDS[b.state] || b.state);
    html += `<span class="t">${t === last ? "" : t}</span><span class="m">${esc(msg)}</span>`;
    last = t;
  }
  const lastState = [...shown].reverse().find((b) => b.kind === "state" && b.state)?.state;
  if (!j.done && v.shown >= v.beats.length && ["writing_step", "reading_fields", "opening", "retry"].includes(lastState))
    html += `<span class="t"></span><span class="m dim">…</span>`;
  const log = $("log"); log.innerHTML = html || `<span class="t"></span><span class="m dim">Waiting for a clean room…</span>`;
  const xs = [...log.querySelectorAll(".x")];
  if (xs.length !== $("pins").children.length) {   // a ring where the newest attempt hit, pins stay for the earlier ones
    $("pins").innerHTML = xs.map((x, i) => `<div class="pin ${i === xs.length - 1 ? "hit" : ""}" style="top:${x.offsetTop + log.offsetTop + 4}px"></div>`).join("");
    const g = document.querySelector(".glass"); g.classList.add("hit"); setTimeout(() => g.classList.remove("hit"), 250);
  }
  $("test").textContent = j.kind === "breakin" ? "BREAK-IN TEST · our own attack script" : /TESTFILE/.test(j.file) ? "TEST FILE · ours, harmless" : "";
  const reached = new Set(shown.filter((b) => b.kind === "state").map((b) => b.state).concat(["queued"]));
  if (reached.has("extracting") && j.state !== "failed") $("drawer").classList.add("out");
  renderSlip(j, reached, v.filled);
}

function finish() {
  const j = view.j, id = current;
  $("log").classList.add("shred");                    // the room is wiped, only the receipt stub stays
  setTimeout(() => {
    if (id !== current) return;
    $("log").style.display = "none"; $("pins").innerHTML = "";   // nothing left over there but the receipt
    $("stub").innerHTML = stub(j);
    const st = $("stub").firstElementChild;                      // the drawer sits on the receipt it delivered
    if (st) $("drawer").style.top = `${st.offsetTop + st.offsetHeight + 14}px`;   // just under the receipt it delivered
  }, view.instant ? 0 : 600);
  refreshQueue(true);
}

function lived(j) {   // the container's own life, from its receipt (model calls happen outside the room)
  const r = j.tries?.at(-1)?.receipt;
  return r ? Math.max(0, r.destroyed - r.started).toFixed(2) : "0.00";
}
// the record as the room left it: exit codes, errors, every attempt verbatim, the code that ran. Nothing summarised.
function rawRecord(j) {
  const parts = (j.tries || []).map((t, i) => {
    const r = t.receipt, life = Math.max(0, r.destroyed - r.started).toFixed(2);
    const head = `# room ${r.room} · try ${i + 1} · exit ${r.exit_code ?? "?"}${r.killed_by ? ` (killed: ${r.killed_by})` : ""} · lived ${life} s`;
    const err = r.error ? `\n! ${r.error}` : "";
    const att = (r.attempts || []).length ? "\n" + r.attempts.map((a) => `+${Number(a.t || 0).toFixed(3)}s ${a.what} ${a.detail}`).join("\n") : "\n(no attempts recorded)";
    const code = j.kind === "breakin" ? "" : `\n--- step the model wrote (Vultr Serverless Inference) ---\n${t.step || ""}`;
    return head + err + att + code;
  });
  return `<details class="raw"><summary>raw record</summary><pre>${esc(parts.join("\n\n"))}</pre></details>`;
}

function breakinStub(j) {
  const ps = j.probes || [], held = ps.filter((p) => p.held).length, r = j.tries?.[0]?.receipt; if (!r) return "";
  const rooms = j.tries.map((t) => `${t.receipt.room.toUpperCase()} · lived ${Math.max(0, t.receipt.destroyed - t.receipt.started).toFixed(2)} s · exit ${t.receipt.exit_code}`);
  return `<div class="stub"><div class="st ${held === ps.length ? "stopped" : "got"}">${ps.length - held} OF ${ps.length} GOT THROUGH</div>Break-in test · our attack script<hr>` +
    `NET ${esc(r.network)} · FS read-only<br>MEM ${r.caps.memory_mb}&nbsp;MB · CPU&nbsp;${r.caps.cpus} · ${r.caps.seconds}&nbsp;s<br>secrets inside: ${r.secrets_inside ?? "not measured"}${r.env_names?.length ? ` (sees ${esc(r.env_names.join(", "))})` : ""} · runtime ${esc(r.runtime)}<hr>` +
    ps.map((p) => p.held ? `<span class="x">✕ ${esc(p.attack)}</span>` : `<span class="got">⚠ ${esc(p.attack)} · got through</span>`).join("<br>") +
    `<hr>${rooms.map(esc).join("<br>")}<br>both rooms destroyed ✓${rawRecord(j)}</div>`;
}
function stub(j) {
  if (j.kind === "breakin") return breakinStub(j);
  const r = j.tries?.at(-1)?.receipt; if (!r) return "";
  const tried = distinct(j);
  const held = (j.flags || []).some((x) => x.blocks) && !j.approved;
  const flagged = (j.flags || []).some((x) => x.blocks), hidden = (j.notes || []).some((n) => /instruction/i.test(n));
  const callable = (j.flags || []).some((x) => ["bank_changed", "sender_domain", "new_vendor", "remit_changed", "pay_method_changed"].includes(x.code));
  const st = failedOf(j) ? `<div class="st held">COULDN'T READ · ASK FOR A NEW COPY</div>`
    : held ? `<div class="st held">HOLD · needs you</div>` : flagged ? `<div class="st held">${callable ? "APPROVED · CALL NOTED" : "APPROVED AFTER REVIEW"}</div>`
    : tried.length ? `<div class="st stopped">${tried.length} STOPPED</div>` : hidden ? `<div class="st held">HIDDEN INSTRUCTIONS FOUND</div>`
    : `<div class="st clean">clean</div>`;
  const short = (d) => d.replace(/^the page tried to send its title to (\S+)/, "page title → $1").replace(/^the page tried to load an image from (\S+)/, "image ← $1")
    .replace(/^the page tried to reach |^tried to (reach|read) /, "").replace(" · nothing there", " · not there");
  return `<div class="stub">${st}No. ${esc(r.room.toUpperCase())}<br>${esc(j.file)}<hr>` +
    `NET ${esc(r.network)} · FS read-only<br>MEM ${r.caps.memory_mb}&nbsp;MB · CPU&nbsp;${r.caps.cpus} · ${r.caps.seconds}&nbsp;s<br>secrets inside: ${r.secrets_inside ?? "not measured"}${r.env_names?.length ? ` (sees ${esc(r.env_names.join(", "))})` : ""} · runtime ${esc(r.runtime)}<hr>` +
    (tried.length ? tried.map((d) => `<span class="x">✕ ${esc(short(d))}</span>`).join("<br>") : "Attempts stopped: none") +
    (hidden ? `<br><span class="x">✕ hidden instructions in the text · read as data, not obeyed</span>` : "") +
    ((j.control || []).length ? `<hr><span class="ctl">control · the same hosts from the server, outside the room:</span><br>` +
      j.control.map((c) => `<span class="ok">✓ ${esc(c.host.replace(/^https?:\/\//, ""))} answers (${esc(c.result)}) in ${c.ms} ms</span>`).join("<br>") : "") +
    `<hr>${j.tries.length > 1 ? "last room" : "room"} lived ${lived(j)} s · destroyed ✓${j.tries.length > 1 ? ` · ${j.tries.length} tries, a fresh room each` : ""}${rawRecord(j)}</div>`;
}

// ---------- the slip (left) ----------
function holdShort(j) {
  const bank = (j.flags || []).some((x) => x.code === "bank_changed"), dom = (j.flags || []).find((x) => x.code === "sender_domain");
  const vendor = ((j.fields || {}).vendor || "the vendor").split(" ").slice(0, 2).join(" ");
  const what = [bank ? "New bank account" : "", dom ? `sent from a look-alike address (${esc(dom.domain.slice(dom.usual.length) || dom.domain)})` : ""].filter(Boolean).join(", ");
  const other = (j.flags || []).filter((x) => !["bank_changed", "sender_domain"].includes(x.code)).map((x) => esc(x.text)).join(" ");
  if (!what) return `<div class="hold"><b>HOLD</b> · ${other || "Needs a check."}</div>`;
  return `<div class="hold"><b>HOLD</b> · ${what}. Call ${esc(vendor)} on the number you have on file.${other ? " " + other : ""}</div>`;
}
function senderRow(j) {
  const dom = (j.flags || []).find((x) => x.code === "sender_domain"); if (!dom) return "";
  const d = esc(dom.domain), u = esc(dom.usual);
  const marked = d.startsWith(u) ? `${u}<b>${d.slice(u.length)}</b>` : `<b>${d}</b>`;
  return `<span class="dom">${marked}</span> <span class="was" style="display:inline;text-decoration:none">(usual: ${u})</span>`;
}
function holdHtml(j) {
  const bank = (j.flags || []).find((x) => x.code === "bank_changed"), dom = (j.flags || []).find((x) => x.code === "sender_domain");
  const vendor = (j.fields || {}).vendor || "the vendor";
  const parts = [];
  if (bank) parts.push(`New bank account. Paid to ${esc(bank.was)} on ${esc(bank.last_date.slice(0, 5))} (${esc(bank.last_invoice)}). This invoice asks for ${esc(bank.now)}.`);
  if (dom) {
    const d = esc(dom.domain), u = esc(dom.usual);
    const marked = d.startsWith(u) ? `${u}<b>${d.slice(u.length)}</b>` : d;
    parts.push(`Sent from <span class="dom">${marked}</span>, not their usual <span class="dom">${u}</span>.`);
  }
  (j.flags || []).filter((x) => !["bank_changed", "sender_domain"].includes(x.code)).forEach((x) => parts.push(esc(x.text)));
  return `<div class="hold"><b>HOLD</b> · ${parts.join("<br>")}${bank || dom ? ` Call ${esc(vendor.split(" ").slice(0, 2).join(" "))} on the number you have on file.` : ""}</div>`;
}

function renderBreakinSlip(j, filled) {
  const el = $("slip"), ps = j.probes || [], held = ps.filter((p) => p.held).length;
  const rows = !filled ? `<div class="f ghost"><span class="k">attacks</span><span class="v">·</span></div>`
    : ps.map((p, i) => `<div class="f fill" style="animation-delay:${i * 80}ms"><span class="k">${esc(p.attack)}</span>` +
      `<span class="v ${p.held ? "" : "gotv"}">${p.held ? "stopped" : "GOT THROUGH"} · <span class="how">${esc(p.how)}</span></span></div>`).join("");
  const stamp = filled ? `<div class="stamp ${held === ps.length ? "" : "got"}">${ps.length - held} OF ${ps.length}<br>GOT THROUGH</div>` : "";
  el.className = "slip";
  el.innerHTML = stamp + `<h2>${filled ? "Break-in test" : "Attacking the room…"}</h2>` +
    `<div class="sub">Our own attack script, run in fresh rooms with exactly the walls a stranger's file gets. No model involved.</div>` +
    (filled ? `<div class="tried">${held === ps.length ? `Every attack stopped at the glass. Nothing reached the server, the network or the key.` : `${ps.length - held} attack${ps.length - held === 1 ? "" : "s"} got through. See the receipt.`}</div>` : "") + rows;
}

function renderSlip(j, reached, filled) {
  if (j.kind === "breakin") return renderBreakinSlip(j, filled);
  const f = j.fields || {}, el = $("slip");
  const MARKS = [["queued", "RECEIVED"], ["opening", "OPENED IN ROOM"], ["extracting", "COPIED AS TEXT"], ["destroyed", "DESTROYED"]];
  const phase = filled ? "done" : "room";
  if (view.phase === phase && phase === "room") {          // same skeleton: only land the marks that just arrived
    [...el.querySelectorAll(".pm")].forEach((m, i) => {
      const k = MARKS[i][0];
      if (reached.has(k) && !view.reached.has(k)) { m.classList.remove("wait"); m.classList.add("land"); view.reached.add(k); }
    });
    return;
  }
  const marks = MARKS.map(([k, w]) => {
    const fresh = reached.has(k) && !view.reached.has(k);
    if (reached.has(k)) view.reached.add(k);
    return `<div class="pm ${reached.has(k) ? (fresh ? "land" : "") : "wait"}">${w}</div>`;
  }).join("");
  view.phase = phase;
  const tried = distinct(j), held = (j.flags || []).some((x) => x.blocks) && !j.approved;
  const stamp = !filled ? "" : tried.length ? `<div class="stamp">${tried.length} ATTEMPT${tried.length === 1 ? "" : "S"}<br>STOPPED AT THE GLASS</div>`
    : held ? `<div class="stamp hold">${(j.flags || []).some((x) => ["bank_changed", "sender_domain", "new_vendor", "remit_changed", "pay_method_changed"].includes(x.code)) ? "HOLD · CALL VENDOR" : "HOLD · LOOK FIRST"}</div>` : "";
  const top = !filled ? "" : held ? holdShort(j) :
    tried.length ? `<div class="tried">The file tried ${tried.length} thing${tried.length === 1 ? "" : "s"} while it was open. ${tried.length === 1 ? "It" : tried.length === 2 ? "Both" : "All"} stopped at the glass${(j.control || []).some((c) => /HTTP/.test(c.result)) ? " (outside the room, the same addresses answer)" : ""}. Your fields are below.</div>` : "";
  const bankFlag = (j.flags || []).find((x) => x.code === "bank_changed");
  const bank = f.bank && (f.bank.routing || f.bank.account_last4)
    ? (bankFlag ? `<span class="was">${esc(bankFlag.was)}</span>` : "") + `${esc((f.bank.name || "").replace(" (EXAMPLE)", ""))} · routing ${esc(f.bank.routing || "?")} · ****${esc(f.bank.account_last4 || "?")}` : "";
  const pay = { ach: "ACH", check: "Check", card: "Card" }[f.pay_method] || "";
  let rows = [["Amount", f.total != null ? money(f.total) : "", "amt"], ["Invoice", [f.invoice_no, f.invoice_date].filter(Boolean).join(" · ")],
    ["Due", f.due_date], ["Pay by", [pay, f.remit_to].filter(Boolean).join(" · ")], ["Bank", bank, "raw"]];
  if (held) rows = [rows[4], ["Sender", senderRow(j), "raw"], ...rows.slice(0, 4)];          // the evidence first
  const fields = !filled ? ["Amount", "Invoice", "Due", "Pay by"].map((k) => `<div class="f ghost"><span class="k">${k}</span><span class="v">·</span></div>`).join("")
    : rows.filter(([, v]) => v).map(([k, v, c], i) =>
    `<div class="f fill" style="animation-delay:${i * 80}ms"><span class="k">${k}</span><span class="v ${c === "amt" ? "amt" : ""}">${c === "raw" ? v : esc(v)}</span></div>`).join("");
  const ver = !filled || !(j.verify || []).length ? "" : `<div class="ver">checked against the file's own text, not the model's answer: ` +
    j.verify.map((v) => `<span class="${v.found ? "ok" : "no"}">${esc(v.field)} ${v.found ? "✓" : "✕ not in the file"}</span>`).join(" · ") + `</div>`;
  const notes = !filled ? "" : (j.notes || []).map((n) => {
    const q = /“([^”]+)”/.exec(n);                     // the hidden text itself, quoted, so nobody has to take our word for it
    return `<div class="note">${esc(n.replace(/\s*“[^”]+”/, ""))}${q ? `<div class="quote">${esc(q[1])}</div>` : ""}</div>`;
  }).join("");
  const btn = !filled ? "" : j.paid ? `<div class="note">On the pay list.</div>`
    : held ? `<button class="btn" disabled>Waiting for controller</button><a class="btn ghost" href="#receipts">Open controller receipts</a>`
    : failedOf(j) ? "" : `<button class="btn" id="pay">Send to pay list</button>`;
  const sub = j.sender ? `From <span class="dom">${esc((/<([^>]+)>/.exec(j.sender) || [, j.sender])[1])}</span> · <span class="fn">${esc(j.file)}</span>`
    : `<span class="fn">${esc(j.file)}</span>${/TESTFILE/.test(j.file) ? " · our test file" : ""}`;
  el.innerHTML = stamp + `<h2>${esc(filled ? (f.vendor || "Unknown vendor") : "In the room…")}</h2><div class="sub">${sub}</div>` +
    `<div class="marks">${marks}</div>${top}${held && filled ? btn : ""}${fields}${ver}${filled && j.error ? `<div class="tried">${esc(j.error)}</div>` : ""}${notes}${held && filled ? "" : btn}`;
  const p = $("pay"); if (p) p.onclick = async () => { await api(`/api/intake/${j.id}/pay`, { method: "POST" }).catch((e) => alert(e.message)); reload(j.id); };
  const a = $("appr"); if (a) a.onclick = async () => { await api(`/api/intake/${j.id}/approve`, { method: "POST" }); reload(j.id); };
}
async function reload(id) { view.j = await api(`/api/intake/${id}`); render(); refreshQueue(); }

// ---------- queue: one chip per file name, the latest run ----------
async function refreshQueue(flash) {
  const items = await api("/api/intakes"), seen = new Set(), latest = [];
  for (const i of items) if (!seen.has(i.file)) { seen.add(i.file); latest.push(i); }
  $("queue").innerHTML = latest.slice(0, 6).map((i) => {
    const playing = i.id === current && view && !view.filled;     // the page is still playing this one out: no verdict yet
    const word = !i.done || playing ? "in the room…" : i.kind === "breakin" ? `${i.held} of ${i.probes} stopped`
      : i.failed ? "couldn't read" : i.flagged && !i.approved ? "HOLD" : i.stopped ? `${i.stopped} stopped` : i.paid ? "on the pay list" : "ready";
    const cls = word === "HOLD" || word === "couldn't read" ? "held" : /stopped/.test(word) ? "stopped" : "";
    if (i.kind === "breakin") return `<div class="chip ${i.id === current ? "on" : ""}" data-id="${i.id}"><span class="vn">Break-in test</span>&nbsp;·&nbsp;<span class="w ${cls}">${word}</span></div>`;
    return `<div class="chip ${i.id === current ? "on" : ""}" data-id="${i.id}"><span class="vn">${esc(i.vendor || label(i.file))}</span>` +
      `${i.total != null ? "&nbsp;·&nbsp;" + money(i.total) : ""}&nbsp;·&nbsp;<span class="w ${cls}">${word}</span></div>`;
  }).join("");
  $("queue").onclick = (e) => { const id = e.target.closest(".chip")?.dataset.id; if (id) follow(id, true); };
  const done = items.filter((i) => i.done), files = done.filter((i) => i.kind !== "breakin").length, c = $("count");
  // the clerk's own files only; our break-in test is counted on its own, never added to the files' numbers
  const stopped = done.reduce((n, i) => n + (i.kind === "breakin" ? 0 : i.stopped), 0);
  const got = done.reduce((n, i) => n + (i.kind === "breakin" ? 0 : i.got_out || 0), 0);   // measured: completed requests in the room's net log
  const bk = done.filter((i) => i.kind === "breakin").at(-1);
  c.textContent = done.length ? `${files} file${files === 1 ? "" : "s"} opened · ${stopped} attempt${stopped === 1 ? "" : "s"} stopped · ${got} got out` +
    (bk ? ` · break-in test: ${bk.probes - bk.held} of ${bk.probes} got through` : "") : "";
  if (flash) { c.classList.remove("flash"); void c.offsetWidth; c.classList.add("flash"); }
}

// ---------- controller: receipt stubs ----------
async function showReceipts() {
  const items = (await api("/api/intakes")).filter((i) => i.done);
  const rank = (j) => ((j.flags || []).some((x) => x.blocks) && !j.approved ? 0 : distinct(j).length ? 1 : 2);
  const full = (await Promise.all(items.map((i) => api(`/api/intake/${i.id}`)))).sort((a, b) => rank(a) - rank(b));
  $("stubs").innerHTML = full.map((j) => {
    const s = stub(j);
    if (!(j.flags || []).length) return s;
    const h = holdShort(j).replace(/^<div class="hold"><b>HOLD<\/b> · /, "").replace(/<\/div>$/, "") +
      `<details><summary>details</summary>${holdHtml(j).replace(/^<div class="hold"><b>HOLD<\/b> · /, "").replace(/<\/div>$/, "")}</details>`;
    const callable = (j.flags || []).some((x) => x.blocks && ["bank_changed", "sender_domain", "new_vendor", "remit_changed", "pay_method_changed"].includes(x.code));
    const noted = j.approval_note ? `<br><span class="ctl">call note: ${esc(j.approval_note)}</span>` : "";
    return s.slice(0, -6) + `<hr><b class="${j.approved ? "" : "held"}">${j.approved ? "Approved" : "HOLD"}</b> · ${h}` + noted +
      (j.approved ? "" : (callable ? `<br><input class="note" data-note="${j.id}" maxlength="200" placeholder="call note: who called, which number on file">` : "") +
        `<br><button class="btn" data-ap="${j.id}">Approve</button><span class="err" data-err="${j.id}"></span>`) + "</div>";
  }).join("") || `<div class="empty">No files opened yet.</div>`;
  $("stubs").onclick = async (e) => {
    const id = e.target.dataset.ap; if (!id) return;
    const note = document.querySelector(`input[data-note="${id}"]`)?.value || "";
    try {
      await api(`/api/intake/${id}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note }) });
      showReceipts();
    } catch (err) { const el = document.querySelector(`[data-err="${id}"]`); if (el) el.textContent = " " + err.message; }
  };
}

function route() {
  const rec = location.hash === "#receipts";
  $("view-desk").hidden = rec; $("view-receipts").hidden = !rec;
  $("nav-desk").classList.toggle("on", !rec); $("nav-receipts").classList.toggle("on", rec);
  if (rec) showReceipts();
}
window.onhashchange = route;
route(); loadSamples(); refreshQueue();
