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

// ---------- what a file tried, in words ----------
const attemptsOf = (j) => (j.tries || []).flatMap((t) => t.receipt.attempts);
function host(detail) {
  const m = /https?:\/\/([^\/'"]+)/.exec(detail) || /\('([^']+)',\s*\d+/.exec(detail);
  return m ? m[1] : "an address";
}
function describe(a) {
  if (a.what === "getenv") return `tried to read ${a.detail} · nothing there`;
  if (a.what === "browser") return /[?&]d=/.test(a.detail) ? `the page tried to send its title to ${host(a.detail)} · no network`
    : /\.(png|gif|jpe?g|svg|webp)/i.test(a.detail) ? `the page tried to load an image from ${host(a.detail)} · no network`
    : `the page tried to reach ${host(a.detail)} · no network`;
  if (a.what.startsWith("socket") || a.what === "urllib.Request") return `tried to reach ${host(a.detail)} · no network`;
  if (a.what === "open") return `tried to open ${a.detail} · read-only room`;
  return `tried ${a.what} · stopped`;
}
const distinct = (j) => [...new Set(attemptsOf(j).map(describe))];

// ---------- sample inbox and upload ----------
const label = (n) => ({ bonneville: "Bonneville", granite: "Granite Peak", jordan: "Jordan River (test)", red: "Red Butte (scan)",
  wasatch: "Wasatch (test, HTML)" })[n.split("_")[0]] || n;
async function loadSamples() {
  const names = (await api("/api/samples")).filter((n) => !(n.endsWith(".docx") && n.startsWith("granite")));  // the .eml carries it
  $("samples").innerHTML = names.map((n) => `<button data-s="${esc(n)}">${esc(label(n))}</button>`).join("·");
  $("samples").onclick = (e) => { e.stopPropagation(); const s = e.target.dataset.s; if (s) start({ sample: s }); };
}
const drop = $("drop");
drop.onclick = (e) => { if (e.target === drop) $("file").click(); };
$("file").onchange = (e) => e.target.files[0] && upload(e.target.files[0]);
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]); };
async function upload(file) { const fd = new FormData(); fd.append("file", file); follow((await api("/api/intake", { method: "POST", body: fd })).id); }
async function start(body) {
  follow((await api("/api/intake", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).id);
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
  const out = [], tried = distinct(j);
  for (const s of j.states.slice(1)) {
    if (s.state === "extracting") {
      tried.forEach((d) => out.push({ kind: "attempt", text: d, at: s.at }));
      if ((j.notes || []).some((n) => /Instruction-like/.test(n))) out.push({ kind: "state", note: "instructions inside the file · read as data, not obeyed", at: s.at });
    }
    out.push({ kind: "state", state: s.state, at: s.at });
  }
  return out;
}

function tick() {
  const v = view; if (!v || !v.j) return;
  const next = v.beats[v.shown];
  const now = performance.now();
  if (next && (v.instant || now - v.last >= DWELL[next.kind])) { v.shown++; v.last = now; render(); }
  if (!next && v.j.done && v.shown >= v.beats.length && !v.filled) { v.filled = true; render(); finish(); }
}

// ---------- the room (right) ----------
const WORDS = { sandbox_up: "room up · gVisor on Vultr · no network · no secrets", opening: "file handed in, read-only", retry: "step failed, the model rewrites it",
  extracting: "only text passed through the drawer", extracted: "fields read", failed: "couldn't read the file", destroyed: "room destroyed ✓" };

function render() {
  const v = view, j = v.j, t0 = j.states[0].at, rel = (t) => `+${(t - t0).toFixed(2)} s`;
  const shown = v.beats.slice(0, v.shown), tried = shown.filter((b) => b.kind === "attempt");
  let last = null, html = "";
  for (const b of shown) {
    if (b.kind === "attempt") { html += `<span class="t"></span><span class="m x">✕ ${esc(b.text)}</span>`; continue; }
    if (b.note) { html += `<span class="t"></span><span class="m n">✕ ${esc(b.note)}</span>`; continue; }
    const t = rel(b.at), msg = b.state === "blocked" ? `fields read · ${tried.length} attempt${tried.length === 1 ? "" : "s"} stopped` : (WORDS[b.state] || b.state);
    html += `<span class="t">${t === last ? "" : t}</span><span class="m">${esc(msg)}</span>`;
    last = t;
  }
  const log = $("log"); log.innerHTML = html || `<span class="t"></span><span class="m dim">Waiting for a clean room…</span>`;
  const xs = [...log.querySelectorAll(".x")];
  if (xs.length !== $("pins").children.length) {   // a ring where the newest attempt hit, pins stay for the earlier ones
    $("pins").innerHTML = xs.map((x, i) => `<div class="pin ${i === xs.length - 1 ? "hit" : ""}" style="top:${x.offsetTop + log.offsetTop + 4}px"></div>`).join("");
    const g = document.querySelector(".glass"); g.classList.add("hit"); setTimeout(() => g.classList.remove("hit"), 250);
  }
  $("test").textContent = /TESTFILE/.test(j.file) ? "TEST FILE · ours, harmless" : "";
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

function lived(j) {
  const at = (k) => j.states.find((s) => s.state === k)?.at;
  const a = at("sandbox_up") ?? j.states[0].at, b = at("destroyed") ?? a;
  return Math.max(0, b - a).toFixed(2);
}
function stub(j) {
  const r = j.tries?.at(-1)?.receipt; if (!r) return "";
  const tried = distinct(j);
  const held = (j.flags || []).some((x) => x.blocks) && !j.approved;
  const st = held ? `<div class="st held">HOLD · needs you</div>` : tried.length ? `<div class="st stopped">${tried.length} STOPPED</div>` : `<div class="st clean">clean</div>`;
  const short = (d) => d.replace(/^the page tried to send its title to (\S+)/, "page title → $1").replace(/^the page tried to load an image from (\S+)/, "image ← $1")
    .replace(/^the page tried to reach |^tried to (reach|read) /, "").replace(" · nothing there", " · not there");
  return `<div class="stub">${st}No. ${esc(r.room.toUpperCase())}<br>${esc(j.file)}<hr>` +
    `NET ${esc(r.network)} · FS read-only<br>MEM ${r.caps.memory_mb}&nbsp;MB · CPU&nbsp;${r.caps.cpus} · ${r.caps.seconds}&nbsp;s<br>secrets inside: ${r.secrets_inside} · runtime ${esc(r.runtime)}<hr>` +
    (tried.length ? tried.map((d) => `<span class="x">✕ ${esc(short(d))}</span>`).join("<br>") : "Attempts stopped: none") +
    `<hr>room lived ${lived(j)} s · destroyed ✓${j.tries.length > 1 ? ` · ${j.tries.length} tries` : ""}</div>`;
}

// ---------- the slip (left) ----------
function holdShort(j) {
  const bank = (j.flags || []).some((x) => x.code === "bank_changed"), dom = (j.flags || []).find((x) => x.code === "sender_domain");
  const vendor = ((j.fields || {}).vendor || "the vendor").split(" ").slice(0, 2).join(" ");
  const what = [bank ? "New bank account" : "", dom ? `sent from a look-alike address (${esc(dom.domain.slice(dom.usual.length) || dom.domain)})` : ""].filter(Boolean).join(", ");
  return `<div class="hold"><b>HOLD</b> · ${what || "Needs a check"}. Call ${esc(vendor)} on the number you have on file.</div>`;
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
  return `<div class="hold"><b>HOLD</b> · ${parts.join("<br>")} Call ${esc(vendor.split(" ").slice(0, 2).join(" "))} on the number you have on file.</div>`;
}

function renderSlip(j, reached, filled) {
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
    : held ? `<div class="stamp hold">HOLD · CALL VENDOR</div>` : "";
  const top = !filled ? "" : held ? holdShort(j) :
    tried.length ? `<div class="tried">The file tried ${tried.length} thing${tried.length === 1 ? "" : "s"} while it was open. ${tried.length === 1 ? "It" : tried.length === 2 ? "Both" : "All"} stopped at the glass. Your fields are below.</div>` : "";
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
  const notes = !filled ? "" : (j.notes || []).map((n) => `<div class="note">${esc(n)}</div>`).join("");
  const btn = !filled ? "" : j.paid ? `<div class="note">On the pay list.</div>`
    : held ? `<button class="btn" disabled>Waiting for controller</button><button class="btn ghost" id="appr">Controller: approve</button>`
    : j.state === "failed" ? "" : `<button class="btn" id="pay">Send to pay list</button>`;
  const sub = j.sender ? `From <span class="dom">${esc((/<([^>]+)>/.exec(j.sender) || [, j.sender])[1])}</span> · <span class="fn">${esc(j.file)}</span>`
    : `<span class="fn">${esc(j.file)}</span>${/TESTFILE/.test(j.file) ? " · our own harmless test file" : ""}`;
  el.innerHTML = stamp + `<h2>${esc(filled ? (f.vendor || "Unknown vendor") : "In the room…")}</h2><div class="sub">${sub}</div>` +
    `<div class="marks">${marks}</div>${top}${held && filled ? btn : ""}${fields}${filled && j.error ? `<div class="tried">${esc(j.error)}</div>` : ""}${notes}${held && filled ? "" : btn}`;
  const p = $("pay"); if (p) p.onclick = async () => { await api(`/api/intake/${j.id}/pay`, { method: "POST" }).catch((e) => alert(e.message)); reload(j.id); };
  const a = $("appr"); if (a) a.onclick = async () => { await api(`/api/intake/${j.id}/approve`, { method: "POST" }); reload(j.id); };
}
async function reload(id) { view.j = await api(`/api/intake/${id}`); render(); refreshQueue(); }

// ---------- queue: one chip per file name, the latest run ----------
async function refreshQueue(flash) {
  const items = await api("/api/intakes"), seen = new Set(), latest = [];
  for (const i of items) if (!seen.has(i.file)) { seen.add(i.file); latest.push(i); }
  $("queue").innerHTML = latest.slice(0, 6).map((i) => {
    const word = !i.done ? "in the room…" : i.flagged && !i.approved ? "HOLD" : i.stopped ? `${i.stopped} stopped` : i.paid ? "on the pay list" : "ready";
    const cls = word === "HOLD" ? "held" : /stopped/.test(word) ? "stopped" : "";
    return `<div class="chip ${i.id === current ? "on" : ""}" data-id="${i.id}"><span class="vn">${esc(i.vendor || label(i.file))}</span>` +
      `${i.total != null ? "&nbsp;·&nbsp;" + money(i.total) : ""}&nbsp;·&nbsp;<span class="w ${cls}">${word}</span></div>`;
  }).join("");
  $("queue").onclick = (e) => { const id = e.target.closest(".chip")?.dataset.id; if (id) follow(id, true); };
  const opened = items.filter((i) => i.done).length, c = $("count");
  c.textContent = opened ? `${opened} file${opened === 1 ? "" : "s"} opened · 0 got out` : "";
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
    const h = holdHtml(j).replace(/^<div class="hold"><b>HOLD<\/b> · /, "").replace(/<\/div>$/, "");
    return s.slice(0, -6) + `<hr><b class="${j.approved ? "" : "held"}">${j.approved ? "Approved" : "HOLD"}</b> · ${h}` +
      (j.approved ? "" : `<br><button class="btn" data-ap="${j.id}">Approve</button>`) + "</div>";
  }).join("") || `<div class="empty">No files opened yet.</div>`;
  $("stubs").onclick = async (e) => { const id = e.target.dataset.ap; if (id) { await api(`/api/intake/${id}/approve`, { method: "POST" }); showReceipts(); } };
}

function route() {
  const rec = location.hash === "#receipts";
  $("view-desk").hidden = rec; $("view-receipts").hidden = !rec;
  $("nav-desk").classList.toggle("on", !rec); $("nav-receipts").classList.toggle("on", rec);
  if (rec) showReceipts();
}
window.onhashchange = route;
route(); loadSamples(); refreshQueue();
