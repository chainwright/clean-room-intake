// Clean Room Intake front end (direction A + B's postmarks and receipt stubs). No framework; polls while a file is in the room.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const money = (v) => (v == null ? "—" : "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const hhmmss = (t) => new Date(t * 1000).toLocaleTimeString("en-US", { hour12: false });
let current = null, timer = null, shown = { attempts: 0, file: null, stub: false };

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
  if (a.what.startsWith("socket") || a.what === "urllib.Request") return `tried to reach ${host(a.detail)} · no network`;
  if (a.what === "open") return `tried to open ${a.detail} · read-only room`;
  return `tried ${a.what} · stopped`;
}
const distinct = (j) => [...new Set(attemptsOf(j).map(describe))];

// ---------- sample inbox and upload ----------
const label = (n) => n.replace(/_TESTFILE/, " (test file)").replace(/\.(pdf|docx|eml|jpg)$/, "").replace(/_/g, " ");
async function loadSamples() {
  const names = (await api("/api/samples")).filter((n) => !(n.endsWith(".docx") && n.startsWith("granite")));  // the .eml carries it
  $("samples").innerHTML = names.map((n) => `<button data-s="${esc(n)}">${esc(label(n))}</button>`).join("·");
  $("samples").onclick = (e) => { const s = e.target.dataset.s; if (s) start({ sample: s }); };
}
const drop = $("drop");
drop.onclick = () => $("file").click();
$("file").onchange = (e) => e.target.files[0] && upload(e.target.files[0]);
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]); };
async function upload(file) { const fd = new FormData(); fd.append("file", file); follow((await api("/api/intake", { method: "POST", body: fd })).id); }
async function start(body) {
  follow((await api("/api/intake", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).id);
}

// ---------- following one file ----------
function follow(id) {
  current = id; shown = { attempts: 0, file: id, stub: false };
  $("log").className = "log"; $("log").innerHTML = ""; $("pins").innerHTML = ""; $("stub").innerHTML = "";
  $("drawer").classList.remove("out");
  const s = $("slip"); s.className = "slip enter"; requestAnimationFrame(() => requestAnimationFrame(() => s.classList.remove("enter")));
  clearInterval(timer); timer = setInterval(() => poll(id), 400); poll(id); refreshQueue();
}
async function poll(id) {
  const j = await api(`/api/intake/${id}`);
  if (id !== current) return;
  renderRoom(j); renderSlip(j);
  if (j.done) { clearInterval(timer); refreshQueue(); }
}

// ---------- the room (right) ----------
function renderRoom(j) {
  const t0 = j.states[0].at, rel = (t) => `+${(t - t0).toFixed(2)} s`;
  const words = { sandbox_up: "room up · gVisor · no network · no secrets", opening: "file handed in, read-only", retry: "step failed, the model rewrites it",
    extracting: "only text passed through the drawer", extracted: "fields read", failed: "couldn't read the file", destroyed: "room destroyed ✓" };
  const tried = distinct(j), lines = [];
  let last = null;
  for (const s of j.states.slice(1)) {
    if (s.state === "extracting") tried.forEach((d) => lines.push(`<span class="x">          ✕ ${esc(d)}</span>`));
    const t = rel(s.at);
    const msg = s.state === "blocked" ? `fields read · ${tried.length} attempt${tried.length === 1 ? "" : "s"} stopped` : (words[s.state] || s.state);
    lines.push(`<span>${t === last ? " ".repeat(t.length) : t}  ${esc(msg)}</span>`);   // same moment: one timestamp
    last = t;
  }
  const log = $("log");
  log.innerHTML = lines.join("\n") || `<span class="dim">Waiting for a clean room…</span>`;
  if (tried.length > shown.attempts) {   // a red ring where each attempt line sits, then a pin that stays
    const xs = [...log.querySelectorAll(".x")];
    $("pins").innerHTML = xs.map((x) => `<div class="pin hit" style="top:${x.offsetTop + log.offsetTop + 4}px"></div>`).join("");
    shown.attempts = tried.length;
  }
  $("test").textContent = /TESTFILE/.test(j.file) ? "Our own harmless test file" : "";
  if (j.done && j.state !== "failed") $("drawer").classList.add("out");
  if (j.done && !shown.stub) { shown.stub = true; $("stub").innerHTML = stub(j); }
}

function stub(j) {
  const r = j.tries?.at(-1)?.receipt; if (!r) return "";
  const tried = distinct(j);
  return `<div class="stub">No. ${esc(r.room.toUpperCase())} · ${esc(j.file)}<hr>` +
    `NET ${esc(r.network)} · FS read-only · MEM ${r.caps.memory_mb} MB · CPU ${r.caps.cpus} · ${r.caps.seconds} s<br>secrets inside: ${r.secrets_inside} · runtime ${esc(r.runtime)}<hr>` +
    (tried.length ? tried.map((d) => `<span class="x">✕ ${esc(d)}</span>`).join("<br>") : "Attempts stopped: none") +
    `<hr>opened ${hhmmss(r.started)} · destroyed ${hhmmss(r.destroyed)}${j.tries.length > 1 ? ` · ${j.tries.length} tries` : ""}</div>`;
}

// ---------- the slip (left) ----------
function renderSlip(j) {
  const f = j.fields || {}, reached = new Set(j.states.map((s) => s.state)), el = $("slip");
  const at = (k) => j.states.find((s) => s.state === k)?.at;
  const marks = [["queued", "RECEIVED", at("queued")], ["opening", "OPENED IN ROOM"], ["extracting", "COPIED AS TEXT"], ["destroyed", "DESTROYED", at("destroyed")]]
    .map(([k, w, t]) => reached.has(k) ? `<div class="pm">${w}${t ? "<br>" + hhmmss(t) : ""}</div>` : `<div class="pm wait">${w}</div>`).join("");
  const tried = distinct(j), held = (j.flags || []).some((x) => x.blocks) && !j.approved;
  const stamp = !j.done ? "" : tried.length ? `<div class="stamp">${tried.length} ATTEMPT${tried.length === 1 ? "" : "S"}<br>STOPPED AT THE GLASS</div>`
    : held ? `<div class="stamp hold">HOLD · CALL VENDOR</div>` : "";
  const top = !j.done ? "" :
    held ? `<div class="hold"><b>HOLD</b> · ${esc(j.hold)}</div>` :
    tried.length ? `<div class="tried">The file tried ${tried.length} thing${tried.length === 1 ? "" : "s"} while it was open. ${tried.length === 1 ? "It" : tried.length === 2 ? "Both" : "All"} stopped at the glass. Your fields are below.</div>` : "";
  const bankFlag = (j.flags || []).find((x) => x.code === "bank_changed");
  const bank = f.bank && (f.bank.routing || f.bank.account_last4)
    ? (bankFlag ? `<span class="was">${esc(bankFlag.was)}</span>` : "") + `${esc((f.bank.name || "").replace(" (EXAMPLE)", ""))} · routing ${esc(f.bank.routing || "?")} · ****${esc(f.bank.account_last4 || "?")}` : "";
  const pay = { ach: "ACH", check: "Check", card: "Card" }[f.pay_method] || "";
  const rows = [["Amount", f.total != null ? money(f.total) : "", "amt"], ["Invoice", [f.invoice_no, f.invoice_date].filter(Boolean).join(" · ")],
    ["Due", f.due_date], ["Pay by", [pay, f.remit_to].filter(Boolean).join(" · ")], ["Bank", bank, "raw"], ["From", j.sender]]
    .filter(([, v]) => v).map(([k, v, c]) => `<div class="f"><span class="k">${k}</span><span class="v ${c === "amt" ? "amt" : ""}">${c === "raw" ? v : esc(v)}</span></div>`).join("");
  const notes = (j.notes || []).map((n) => `<div class="note">${esc(n)}</div>`).join("");
  const btn = !j.done ? "" : j.paid ? `<div class="note">On the pay list.</div>`
    : held ? `<button class="btn" disabled>Waiting for controller</button><button class="btn ghost" id="appr">Controller: approve</button>`
    : `<button class="btn" id="pay">Send to pay list</button>`;
  el.className = "slip"; el.innerHTML = stamp +
    `<h2>${esc(f.vendor || (j.done ? "Unknown vendor" : "In the room…"))}</h2>` +
    `<div class="sub">${esc(j.file)}${/TESTFILE/.test(j.file) ? " · our own harmless test file" : ""}</div>` +
    `<div class="marks">${marks}</div>${top}${rows}${j.error ? `<div class="hold">${esc(j.error)}</div>` : ""}${notes}${btn}`;
  const p = $("pay"); if (p) p.onclick = async () => { await api(`/api/intake/${j.id}/pay`, { method: "POST" }).catch((e) => alert(e.message)); poll(j.id); };
  const a = $("appr"); if (a) a.onclick = async () => { await api(`/api/intake/${j.id}/approve`, { method: "POST" }); poll(j.id); };
}

// ---------- queue: one chip per file name, the latest run ----------
async function refreshQueue() {
  const items = await api("/api/intakes"), seen = new Set(), latest = [];
  for (const i of items) if (!seen.has(i.file)) { seen.add(i.file); latest.push(i); }
  $("queue").innerHTML = latest.slice(0, 6).map((i) => {
    const word = !i.done ? "in the room…" : i.flagged && !i.approved ? "HOLD" : i.stopped ? `${i.stopped} stopped` : i.paid ? "on the pay list" : "ready";
    const cls = word === "HOLD" ? "held" : /stopped/.test(word) ? "stopped" : "";
    return `<div class="chip ${i.id === current ? "on" : ""}" data-id="${i.id}">${esc(i.vendor || label(i.file))}` +
      `${i.total != null ? " · " + money(i.total) : ""} · <span class="w ${cls}">${word}</span></div>`;
  }).join("");
  $("queue").onclick = (e) => { const id = e.target.closest(".chip")?.dataset.id; if (id) follow(id); };
  const opened = items.filter((i) => i.done).length;
  $("count").textContent = opened ? `${opened} file${opened === 1 ? "" : "s"} opened · 0 got out` : "";
}

// ---------- controller: receipt stubs ----------
async function showReceipts() {
  const items = (await api("/api/intakes")).filter((i) => i.done);
  const full = await Promise.all(items.map((i) => api(`/api/intake/${i.id}`)));
  $("stubs").innerHTML = full.map((j) => {
    const s = stub(j);
    if (!(j.flags || []).length) return s;
    return s.slice(0, -6) + `<hr><b>${j.approved ? "Approved" : "HOLD"}</b> · ${esc(j.hold)}` +
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
