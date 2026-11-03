// Clean Room Intake front end: no framework, polls the API while a file is in the booth.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const TRACK = [["queued", "queued"], ["sandbox_up", "booth up"], ["opening", "opened"], ["extracting", "fields read"], ["destroyed", "booth destroyed"]];
let current = null, timer = null, shownAttempts = 0;

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.detail || r.statusText), { status: r.status });
  return body;
}

// ---------- sample inbox and upload ----------
async function loadSamples() {
  const names = await api("/api/samples");
  $("samples").innerHTML = names.filter((n) => !n.endsWith(".docx") || !names.includes(n.replace(".docx", ".eml")))
    .map((n) => `<button data-s="${esc(n)}">${esc(label(n))}</button>`).join("·");
  $("samples").onclick = (e) => { const s = e.target.dataset.s; if (s) start({ sample: s }); };
}
const label = (n) => n.replace(/_TESTFILE/, " (test file)").replace(/\.(pdf|docx|eml|jpg)$/, " .$1").replace(/_/g, " ");

const drop = $("drop");
drop.onclick = () => $("file").click();
$("file").onchange = (e) => e.target.files[0] && upload(e.target.files[0]);
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]); };

async function upload(file) {
  const fd = new FormData(); fd.append("file", file);
  const { id } = await api("/api/intake", { method: "POST", body: fd });
  follow(id);
}
async function start(body) {
  const { id } = await api("/api/intake", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  follow(id);
}

// ---------- following one file through the booth ----------
function follow(id) {
  current = id; shownAttempts = 0;
  $("log").innerHTML = ""; $("pin").className = "pin"; $("drawer").classList.remove("out");
  clearInterval(timer); timer = setInterval(() => poll(id), 500); poll(id); refreshQueue();
}

async function poll(id) {
  const j = await api(`/api/intake/${id}`);
  if (id !== current) return;
  renderBooth(j); renderSlip(j);
  if (j.done) { clearInterval(timer); refreshQueue(); }
}

function renderBooth(j) {
  const t0 = j.states[0].at, rel = (t) => (t - t0).toFixed(3).padStart(7, "0");
  const lines = [], attempts = (j.tries || []).flatMap((t) => t.receipt.attempts);
  const aLines = [...new Set(attempts.map((a) => describe(a)))].map((d) => `<span class="x">  ✕ ${esc(d)}</span>`);   // one line per thing tried
  for (const s of j.states.slice(1)) {
    const msg = { sandbox_up: "room up · gVisor · no network", opening: "file handed in, read-only", retry: "step failed, model rewrites it",
      extracting: "text out through the drawer", extracted: "fields read", blocked: "fields read · every attempt hit a wall",
      failed: "couldn't read the file", destroyed: "room destroyed" }[s.state] || s.state;
    if (s.state === "extracting") lines.push(...aLines.splice(0));   // what the file tried happened while it was open
    lines.push(`<span class="${s.state === "destroyed" ? "ok" : ""}">${rel(s.at)}  ${esc(msg)}</span>`);
  }
  lines.push(...aLines);
  $("log").innerHTML = lines.join("\n") || `<span class="dim">Waiting for a clean room…</span>`;
  if (attempts.length > shownAttempts) {
    const pin = $("pin"); pin.classList.add("on", "hit"); setTimeout(() => pin.classList.remove("hit"), 150);
    shownAttempts = attempts.length;
  }
  const rec = j.tries?.at(-1)?.receipt;
  if (rec) $("spec").textContent = `room ${rec.room} · NET ${rec.network} · FS read-only · MEM ${rec.caps.memory_mb} MB · ` +
    `CPU ${rec.caps.cpus} · ${rec.caps.seconds} s · secrets inside: ${rec.secrets_inside}`;
  $("test").textContent = /TESTFILE/.test(j.file) ? "Our own harmless test file" : "";
  if (j.done && j.state !== "failed") $("drawer").classList.add("out");
}

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

function renderSlip(j) {
  const f = j.fields || {}, el = $("slip");
  const reached = new Set(j.states.map((s) => s.state));
  const track = TRACK.map(([k, l], i) => {
    const done = reached.has(k) || (k === "extracting" && (reached.has("extracted") || reached.has("blocked")));
    const now = !done && i > 0 && reached.has(TRACK[i - 1][0]);
    return `<span><i class="dot ${done ? "done" : now ? "now" : ""}"></i>${l}</span>`;
  }).join("");
  const money = (v) => (v == null ? "—" : "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 }));
  const bank = f.bank && (f.bank.routing || f.bank.account_last4) ? `${esc(f.bank.name || "")} routing ${esc(f.bank.routing || "?")} · ****${esc(f.bank.account_last4 || "?")}` : "";
  const rows = [["Invoice", [f.invoice_no, f.invoice_date].filter(Boolean).join(" · ")], ["Amount", money(f.total)],
    ["Due", f.due_date], ["Pay by", { ach: "ACH", check: "Check", card: "Card" }[f.pay_method] || ""], ["Bank", bank], ["Sender", j.sender]]
    .filter(([, v]) => v).map(([k, v]) => `<div class="f"><span class="k">${k}</span><span class="v">${esc(v)}</span></div>`).join("");
  const notes = (j.notes || []).map((n) => `<div class="note">${esc(n)}</div>`).join("");
  const holds = (j.flags || []).map((x) => `<div class="hold"><b>HOLD</b> · ${esc(x.text)}</div>`).join("");
  const held = (j.flags || []).some((x) => x.blocks) && !j.approved;
  const btn = !j.done ? "" : j.paid ? `<div class="note">On the pay list.</div>`
    : `<button class="btn" id="pay" ${held ? "disabled title='The controller has to approve the hold first'" : ""}>Send to pay list</button>` +
      (held ? `<button class="btn ghost" id="appr">Controller: approve</button>` : "");
  el.className = "slip"; el.innerHTML =
    `<h2>${esc(f.vendor || (j.done ? "Unknown vendor" : "In the booth…"))}</h2>` +
    `<div class="sub">${esc(j.file)} · ${j.done ? "came back through the drawer as text only" : "being opened on the other side"}</div>` +
    `<div class="track">${track}</div>${rows}${j.error ? `<div class="hold">${esc(j.error)}</div>` : ""}${notes}${holds}${btn}`;
  const pay = $("pay"); if (pay) pay.onclick = async () => { await api(`/api/intake/${j.id}/pay`, { method: "POST" }).catch((e) => alert(e.message)); poll(j.id); };
  const ap = $("appr"); if (ap) ap.onclick = async () => { await api(`/api/intake/${j.id}/approve`, { method: "POST" }); poll(j.id); };
}

async function refreshQueue() {
  const items = await api("/api/intakes");
  $("queue").innerHTML = items.map((i) => `<div class="chip ${i.id === current ? "on" : ""}" data-id="${i.id}">` +
    `${esc(i.vendor || label(i.file))}${i.total != null ? " · $" + Number(i.total).toFixed(2) : ""}` +
    `${i.flagged && !i.approved ? ' · <span class="held">HOLD</span>' : ""}${i.paid ? " ✓" : ""}${i.done ? "" : " …"}</div>`).join("");
  $("queue").onclick = (e) => { const id = e.target.closest(".chip")?.dataset.id; if (id) follow(id); };
}

// ---------- controller receipts ----------
async function showReceipts() {
  const items = await api("/api/intakes");
  $("rtable").innerHTML = `<tr><th>File</th><th>Vendor</th><th>Amount</th><th>Attempts stopped</th><th>Hold</th><th></th></tr>` +
    items.map((i) => `<tr><td>${esc(i.file)}</td><td>${esc(i.vendor || "")}</td><td>${i.total != null ? "$" + Number(i.total).toFixed(2) : ""}</td>` +
      `<td>${i.blocked ? "yes" : "none"}</td><td>${i.flagged ? (i.approved ? "approved" : "HOLD") : ""}</td>` +
      `<td><a href="#" data-id="${i.id}">receipt</a></td></tr>`).join("");
  $("rtable").onclick = async (e) => {
    const id = e.target.dataset.id; if (!id) return; e.preventDefault();
    const j = await api(`/api/intake/${id}`);
    $("rdetail").innerHTML = (j.tries || []).map((t, n) => { const r = t.receipt; return `<div class="receipt">Receipt · ${esc(j.file)} · try ${n + 1}<br>` +
      `room ${esc(r.room)} · image ${esc(r.image)} · runtime ${esc(r.runtime)}<hr>NET ${esc(r.network)} · FS read-only<br>` +
      `MEM ${r.caps.memory_mb} MB · CPU ${r.caps.cpus} · ${r.caps.seconds} s · pids ${r.caps.pids}<br>secrets inside: ${r.secrets_inside}<hr>` +
      (r.attempts.map((a) => `<span class="x">✕ ${esc(describe(a))}</span>`).join("<br>") || "no attempts") +
      `<hr>${r.killed_by ? "killed by " + esc(r.killed_by) + "<br>" : ""}opened ${new Date(r.started * 1000).toISOString()}<br>` +
      `destroyed ${new Date(r.destroyed * 1000).toISOString()}</div>`; }).join("<br>");
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
