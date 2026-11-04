// Landing: the sealed bag. A still counter, a bag that moves on it (its own layer, shadow included), a real peel
// (a short clip between the sealed and the VOID photo), text typed on the bag's label, and that label torn off as the
// only thing that leaves the room. Motion is transform/opacity; nothing per-frame on :root; no backdrop-filter.
const $ = (id) => document.getElementById(id);
const W = 2752, H = 1536;
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const wait = (ms) => new Promise((r) => setTimeout(r, reduce ? 0 : ms));
const scene = $("scene"), bag = $("bag"), next = $("next");
let K = 1, OX = 0, OY = 0;

function fit() {
  if (innerWidth < 900) {                       // phone: the bag on top, full width; the text below it
    K = innerWidth / 1620; OX = -1120 * K; OY = 46;
    scene.style.transform = `translate(${OX}px,${OY}px) scale(${K})`;
    $("hero").style.setProperty("--bagh", `${1536 * K + 46}px`);
    $("hint").style.display = "none";
    return;
  }
  const vw = innerWidth, vh = Math.max(innerHeight, 680);
  K = Math.max(vh / H, (vw * 0.6) / (W * 0.52));
  OX = Math.min(0, vw * 0.755 - W * 0.745 * K); OY = Math.min(0, (vh - H * K) / 2 + vh * 0.03);
  scene.style.transform = `translate(${OX}px,${OY}px) scale(${K})`;
  const h = $("hint"); h.style.left = `${OX + 1180 * K}px`; h.style.top = `${OY + 760 * K}px`;   // beside the bag, pointing at it
}
addEventListener("resize", fit); fit();

// lines on the label: the money fact first
const LINES = [
  ["l0", "bank changed → ****9013", true],
  ["l1", "tried pay-update.example → refused", true],
  ["l2", "Granite Peak · $1,236.00 · Nov 14", false],
  ["l3", "opened in a gVisor room on Vultr", false],
];
async function type(el, text) {
  if (reduce) { el.textContent = text; return; }
  for (let i = 1; i <= text.length; i += 2) { el.textContent = text.slice(0, i + 1); await wait(12); }
}
const anim = (el, kf, o) => el.animate(kf, { fill: "forwards", ...o, duration: reduce ? 1 : o.duration });

let played = false, busy = false;
async function play() {
  if (busy) return; busy = true; played = true;
  $("hint").style.opacity = 0;
  // 1. the tug: the bag stretches toward you a little and the invoice stays in
  bag.animate([{ transform: "none" }, { transform: "translateY(-26px) scaleY(1.014)" }, { transform: "none" }], { duration: reduce ? 1 : 620, easing: "cubic-bezier(.3,1.6,.5,1)" });
  await wait(220);
  // 2. the seal peels: a real clip, then the VOID photo stays
  const v = $("peel");
  try {
    v.currentTime = 0; v.playbackRate = 1.5; v.style.opacity = 1; await v.play();
    await new Promise((r) => { v.onended = r; setTimeout(r, 3200); });
  } catch (e) {}
  $("bagVoid").style.opacity = 1; $("bagSealed").style.opacity = 0; v.style.opacity = 0;
  // 3. only text: typed on the bag's write-on label, money fact first
  for (const [id, t] of LINES) await type($(id), t);
  await wait(60);
  // 4. the label tears off and lands on our side of the counter; the HOLD stamp lands on it
  await tearOff();
  await wait(560);
  anim($("stamp"), [{ opacity: 0, transform: "rotate(-7deg) scale(1.6)" }, { opacity: 1, transform: "rotate(-7deg) scale(.97)", offset: .8 }, { opacity: 1, transform: "rotate(-7deg) scale(1)" }], { duration: 160, easing: "ease-out" });
  $("label").animate([{ translate: "0 0" }, { translate: "2px 2px" }, { translate: "-1px 0" }, { translate: "0 0" }], { duration: 120 });
  await wait(300);
  // 5. the used room: stamped destroyed, slides off away from the text; the next file arrives already sealed
  $("dtime").textContent = new Date().toTimeString().slice(0, 8);
  anim($("destroyed"), [{ opacity: 0, transform: "rotate(-9deg) scale(1.4)" }, { opacity: 1, transform: "rotate(-9deg) scale(1)" }], { duration: 150, easing: "ease-out" });
  await wait(320);
  anim(bag, [{ transform: "none", opacity: 1 }, { transform: "translate(1100px,520px) rotate(9deg)", opacity: 0 }], { duration: 620, easing: "cubic-bezier(.5,0,.75,0)" });
  await wait(260);
  anim(next, [{ transform: "translate(0,-1700px)" }, { transform: "translate(0,14px) scale(1.012)", offset: .8 }, { transform: "translate(0,0) scale(1)" }], { duration: 640, easing: "cubic-bezier(.2,.8,.2,1)" });
  await wait(700);
  $("replay").style.opacity = 1; busy = false;
}

async function tearOff() {
  const lab = $("label"), lines = $("labelLines");
  lines.innerHTML = LINES.map(([, t, red]) => `<div class="${red ? "red" : ""}">${t}</div>`).join("");
  const hr = $("hero").getBoundingClientRect(), end = lab.getBoundingClientRect();
  const sx = OX + 1530 * K, sy = OY + 900 * K, sw = 875 * K;
  const dx = sx - (end.left - hr.left), dy = sy - (end.top - hr.top), s = sw / end.width;
  const at = (x, y, r, sc) => `translate(${x}px,${y}px) rotate(${r}deg) scale(${sc})`;
  // the paper label replaces the printed one on the bag (same place, same angle), and the bag behind it loses its label
  lab.style.transform = at(dx, dy, 6.3, s); lab.style.opacity = 1;
  for (const [id] of LINES) $(id).style.opacity = 0;
  $("bagNolabel").style.opacity = 1; $("bagVoid").style.opacity = 0;
  // the perforation lets go: a jolt, then it lifts off and lands on our side of the counter
  await lab.animate([{ transform: at(dx, dy, 6.3, s) }, { transform: at(dx - 3, dy - 6, 5.6, s) }, { transform: at(dx, dy - 2, 6.0, s) }], { duration: reduce ? 1 : 140 }).finished;
  lab.animate([
    { transform: at(dx, dy - 2, 6.0, s), boxShadow: "0 0 0 #0000" },
    { transform: at(dx * .55, dy * .45 - 50, 2.5, ((s + 1) / 2) * 1.05), boxShadow: "0 34px 50px #0e1a2433", offset: .45 },
    { transform: at(0, 0, -1.5, 1), boxShadow: "0 1px 1px #0e1a2433,0 14px 30px #0e1a2424" },
  ], { duration: reduce ? 1 : 640, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
  lab.style.transform = "";
}

function reset() {
  for (const el of [bag, next, $("stamp"), $("label"), $("destroyed")]) el.getAnimations().forEach((a) => a.cancel());
  for (const [id] of LINES) { $(id).textContent = ""; $(id).style.opacity = 1; }
  $("bagVoid").style.opacity = 0; $("bagNolabel").style.opacity = 0; $("bagSealed").style.opacity = 1; $("label").style.opacity = 0; $("replay").style.opacity = 0;
}
$("replay").onclick = () => { reset(); setTimeout(play, 300); };

// the visitor can try to pull it out; otherwise it plays once on its own
let y0 = null;
bag.addEventListener("pointerdown", (e) => { if (!played) { y0 = e.clientY; bag.setPointerCapture(e.pointerId); } });
bag.addEventListener("pointermove", (e) => {
  if (y0 == null) return;
  const dy = Math.max(-40, Math.min(0, (e.clientY - y0) * 0.22));
  bag.style.transform = `translateY(${dy / K}px) scaleY(${1 + -dy / 2600})`;
  if (dy <= -30) { y0 = null; bag.style.transform = ""; play(); }
});
addEventListener("pointerup", () => { if (y0 != null) { y0 = null; bag.style.transform = ""; } });
document.fonts.ready.then(() => document.body.classList.add("fonts"));
// start only when the fonts, the photos and the peel clip are all here (a cold judge on a slow link sees a still
// poster that fades in, never a bag popping in halfway through the story)
const imgs = [...document.querySelectorAll("#scene img")].map((im) => (im.decode ? im.decode() : Promise.resolve()).catch(() => {}));
const clip = new Promise((r) => { const v = $("peel"); if (v.readyState >= 3) r(); else { v.addEventListener("canplaythrough", r, { once: true }); setTimeout(r, 8000); } });
Promise.all([document.fonts.ready, ...imgs, clip]).then(() => {
  document.body.classList.add("ready");
  setTimeout(() => { if (!played) $("hint").style.opacity = 1; }, 300);
  setTimeout(() => { if (!played) play(); }, reduce ? 0 : 1100);
});

// outside → inside: the dark room panel slides in from the right, and the label of the file we just watched (Granite
// Peak) moves to where the app shows it, so the same file crosses the wall with us; the app opens on that file
$("inside").addEventListener("pointerenter", () => fetch("app.html").catch(() => {}), { once: true });
$("inside").addEventListener("click", async (e) => {
  e.preventDefault();
  const target = e.currentTarget.href;
  for (const el of [$("copy"), document.querySelector("nav.top"), $("replay"), $("hint")]) anim(el, [{ opacity: 1 }, { opacity: 0 }], { duration: 200 });
  const room = $("behind");
  room.style.opacity = 1;
  anim(room, [{ transform: "translateX(100%)" }, { transform: "translateX(0)" }], { duration: 620, easing: "cubic-bezier(.7,0,.2,1)" });
  const lab = $("label");
  if (played) {
    lab.getAnimations().forEach((a) => { a.commitStyles(); a.cancel(); });
    const r = lab.getBoundingClientRect(), hr = $("hero").getBoundingClientRect();
    anim(lab, [{ transform: getComputedStyle(lab).transform }, { transform: `translate(${32 - (r.left - hr.left)}px,${320 - (r.top - hr.top)}px) rotate(0deg) scale(${(innerWidth * 0.62 - 64) / r.width})` }], { duration: 620, easing: "cubic-bezier(.7,0,.2,1)" });
  }
  anim(scene, [{ opacity: 1 }, { opacity: .15 }], { duration: 620 });
  await wait(600);
  location.href = target;
});

// the landing's own real run: the Granite Peak file goes through a real room on the server while the visitor watches
// the bag, so the label prints that room's id and "Look inside" opens that finished file in the app
let landingJob = sessionStorage.getItem("landing:job");
async function realRun() {
  try {
    if (!landingJob) {
      const r = await fetch("/api/intake", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sample: "granite_peak_GPR-5561.eml" }) });
      if (!r.ok) return;
      landingJob = (await r.json()).id; sessionStorage.setItem("landing:job", landingJob);
    }
    $("inside").href = `app.html?job=${landingJob}`;
    for (let i = 0; i < 40; i++) {
      const j = await (await fetch(`/api/intake/${landingJob}`)).json();
      if (j.done) {
        const room = (j.tries || []).at(-1)?.receipt?.room;
        if (room && !played) LINES[3][1] = `room ${room.toUpperCase()} · Vultr · gVisor`;
        return;
      }
      await new Promise((r) => setTimeout(r, 800));
    }
  } catch (e) {}
}
realRun();
setTimeout(() => $("live").classList.add("on"), 1500);

// live line from the running server: the last room and the counters (hidden until real numbers arrive)
fetch("/api/stats").then((r) => r.json()).then((s) => {
  setTimeout(() => $("live").classList.add("on"), 50);
  if (!s || !s.files) return;
  $("n-rooms").textContent = s.rooms.toLocaleString("en-US");
  $("n-stopped").textContent = s.stopped.toLocaleString("en-US");
  document.querySelectorAll(".proof .lv").forEach((d) => (d.hidden = false));
  const mins = Math.max(0, Math.round((Date.now() / 1000 - s.last_at) / 60));
  $("live").textContent = `Live on Vultr · last room ${s.last_room} destroyed ${mins < 1 ? "just now" : mins + " min ago"} · ${s.rooms} rooms since the server started · ${s.escapes} got out · the companies are fictional, the walls are real`;
  if (s.last_room && !landingJob) LINES[3][1] = `room ${s.last_room} · Vultr · gVisor`;
}).catch(() => {});
