import { defaults, presets, motions, validatePack } from "./config.js";
import { Character, drawCharacter, poseFor, fitCanvas } from "./engine.js";
const $ = (s) => document.querySelector(s),
  $$ = (s) => [...document.querySelectorAll(s)];
const native = window.companion;
$$("[data-motion-count]").forEach((el) => (el.textContent = motions.length));
let pack = structuredClone(defaults),
  desktopState = null;
try {
  if (native) {
    desktopState = await native.getState();
    pack = desktopState.config;
  } else {
    const saved = localStorage.getItem("tobkiri-character");
    if (saved) pack = validatePack(JSON.parse(saved));
    else
      pack.reducedMotion = matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
  }
} catch {
  toast("保存した設定を読み込めなかったため、標準設定で起動しました。");
}
let saveTimer,
  saveChain = Promise.resolve(),
  revision = 0;
function toast(text) {
  $("#toast").textContent = text;
  $("#toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("#toast").hidden = true), 4500);
}
function save() {
  const rev = ++revision;
  $("#save-state").textContent = "保存中…";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const value = structuredClone(pack);
    saveChain = saveChain.then(async () => {
      try {
        if (native) await native.save(value);
        else localStorage.setItem("tobkiri-character", JSON.stringify(value));
        if (rev === revision) $("#save-state").textContent = "✓ 保存しました";
      } catch (error) {
        $("#save-state").textContent = "保存できませんでした";
        toast(
          "保存できませんでした。書き出しで設定を保存できます。 " +
            error.message,
        );
      }
    });
  }, 250);
}
function apply(next) {
  pack = validatePack({ ...pack, ...next });
  character.pack = pack;
  sync();
  save();
}
const canvas = $("#playground"),
  character = new Character(pack, 250, 250);
let demo = true,
  paused = false,
  selected = "idle",
  last = performance.now(),
  demoTime = 0,
  lastStep = -1,
  frames = 0,
  fpsTime = 0;
const demoSteps = [
  ["wave", 0.48, 0.66],
  ["hip_pop", 0.48, 0.7],
  ["vault", 0.55, 0.7],
  ["walk", 0.48, 0.66],
  ["type", 0.44, 0.61],
  ["think", 0.44, 0.61],
  ["run", 0.8, 0.65],
  ["click", 0.8, 0.65],
  ["dance", 0.65, 0.7],
  ["scroll_down", 0.5, 0.6],
  ["drag", 0.32, 0.65],
  ["jump", 0.45, 0.64],
  ["backflip", 0.48, 0.7],
  ["handstand", 0.48, 0.7],
  ["soft_drop", 0.48, 0.7],
  ["roll", 0.55, 0.7],
  ["celebrate", 0.45, 0.64],
  ["sit", 0.45, 0.7],
];
function selectMotion(id, { keepDemo = false } = {}) {
  selected = id;
  character.play(id, 4);
  $("#action-label").textContent = motions.find((m) => m[0] === id)?.[1] ?? id;
  $$(".motion-card").forEach((b) =>
    b.classList.toggle("active", b.dataset.motion === id),
  );
  if (!keepDemo) setDemo(false);
}
function setDemo(value) {
  demo = value;
  $("#auto-demo").classList.toggle("active", demo);
  $("#interact").classList.toggle("active", !demo);
  $("#stage-hint").textContent = demo
    ? "しぐさを、おまかせ再生中"
    : "移動・クリック・スクロール・キー入力であそべます";
}
$("#auto-demo").onclick = () => {
  setDemo(true);
  lastStep = -1;
};
$("#interact").onclick = () => setDemo(false);
$("#pause").onclick = () => {
  paused = !paused;
  $("#pause").textContent = paused ? "▶" : "Ⅱ";
  $("#pause").setAttribute(
    "aria-label",
    paused ? "プレビューを再開" : "プレビューを一時停止",
  );
};
function point(event) {
  const r = canvas.getBoundingClientRect();
  return [event.clientX - r.left, event.clientY - r.top];
}
canvas.addEventListener("pointermove", (e) => {
  if (!demo) {
    [character.tx, character.ty] = point(e);
    if (e.buttons === 1) character.play("drag", 0.3);
  }
});
canvas.addEventListener("pointerdown", (e) => {
  setDemo(false);
  [character.tx, character.ty] = point(e);
  selectMotion(e.button === 2 ? "right_click" : "click");
  canvas.focus();
});
canvas.addEventListener("dblclick", () => selectMotion("double_click"));
canvas.addEventListener("contextmenu", (e) => e.preventDefault());
canvas.addEventListener(
  "wheel",
  (e) => {
    if (!demo) {
      e.preventDefault();
      selectMotion(e.deltaY < 0 ? "scroll_up" : "scroll_down");
    }
  },
  { passive: false },
);
canvas.tabIndex = 0;
canvas.addEventListener("keydown", (e) => {
  if (e.key.length === 1 || e.key === "Enter") {
    e.preventDefault();
    selectMotion(e.key.length === 1 ? "type" : "key");
  }
});
const categories = {
  work: [
    "click",
    "double_click",
    "right_click",
    "type",
    "key",
    "scroll_up",
    "scroll_down",
    "drag",
    "grab",
    "think",
    "wait",
  ],
  move: [
    "walk",
    "run",
    "dash",
    "jump",
    "land",
    "climb",
    "float",
    "balance",
    "spin",
    "hip_pop",
    "vault",
    "soft_drop",
    "roll",
    "cartwheel",
    "handstand",
    "backflip",
    "skid",
    "tiptoe",
    "sidestep",
    "bounce",
    "kick",
    "push",
    "pull_up",
    "swing",
  ],
};
for (const [i, m] of motions.entries()) {
  const b = document.createElement("button");
  b.className = "motion-card";
  b.dataset.motion = m[0];
  b.title = m[2];
  b.setAttribute("aria-label", m[1]);
  const c = document.createElement("canvas"),
    label = document.createElement("span"),
    index = document.createElement("span");
  label.textContent = m[1];
  index.textContent = String(i + 1).padStart(2, "0");
  index.className = "index";
  b.append(c, label, index);
  b.onclick = () => selectMotion(m[0]);
  $("#motion-grid").append(b);
}
$("#motion-filter").onchange = () => {
  const value = $("#motion-filter").value;
  $$(".motion-card").forEach(
    (b) =>
      (b.hidden =
        value === "all"
          ? false
          : value === "life"
            ? [...categories.work, ...categories.move].includes(
                b.dataset.motion,
              )
            : !categories[value].includes(b.dataset.motion)),
  );
};
for (const p of presets) {
  const b = document.createElement("button");
  b.className = "preset";
  b.title = p.name;
  b.setAttribute("aria-label", p.name);
  b.dataset.color = p.color;
  const c = document.createElement("canvas");
  b.append(c);
  b.onclick = () => apply(p);
  $("#presets").append(b);
}
for (const color of [
  "#7764e8",
  "#ee6d50",
  "#e6aa4f",
  "#359c8c",
  "#5795d8",
  "#db85b0",
  "#343440",
]) {
  const b = document.createElement("button");
  b.className = "swatch";
  b.style.background = color;
  b.dataset.color = color;
  b.setAttribute("aria-label", color);
  b.onclick = () => apply({ color });
  $("#swatches").append(b);
}
for (const key of [
  "name",
  "color",
  "accent",
  "size",
  "weight",
  "head",
  "speed",
  "eyes",
  "trail",
  "accessory",
  "mode",
  "reducedMotion",
  "cursor",
  "cursorColor",
  "displayMode",
]) {
  const el = $("#" + key);
  el.addEventListener("input", () => {
    const value =
      el.type === "checkbox"
        ? el.checked
        : el.type === "range"
          ? Number(el.value)
          : el.value;
    apply({ [key]: value });
  });
}
function tab(name) {
  $$("[data-tab]").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === name);
    b.setAttribute("aria-selected", b.dataset.tab === name ? "true" : "false");
  });
  $$(".tab-content").forEach((p) => (p.hidden = p.id !== "tab-" + name));
}
$$("[data-tab]").forEach((b) => (b.onclick = () => tab(b.dataset.tab)));
$$("[data-section]").forEach(
  (b) =>
    (b.onclick = () => {
      const section = b.dataset.section;
      $$("[data-section]").forEach((n) =>
        n.classList.toggle("active", n === b),
      );
      if (section === "motion") {
        $("#motion-panel").scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
        tab("motion");
      } else tab(section === "cursor" ? "cursor" : "look");
    }),
);
function sync() {
  for (const key of [
    "name",
    "color",
    "accent",
    "size",
    "weight",
    "head",
    "speed",
    "eyes",
    "trail",
    "accessory",
    "mode",
    "reducedMotion",
    "cursor",
    "cursorColor",
    "displayMode",
  ]) {
    const el = $("#" + key);
    if (el.type === "checkbox") el.checked = pack[key];
    else el.value = pack[key];
  }
  for (const key of ["color", "accent", "size", "weight", "head", "speed"])
    $("#" + key + "-value").textContent =
      String(pack[key]).toUpperCase() +
      (key === "size" ? "%" : key === "speed" ? "×" : "");
  $("#character-name").textContent = pack.name;
  $$(".preset,.swatch").forEach((b) =>
    b.classList.toggle("active", b.dataset.color === pack.color),
  );
  $("#hotspot-x").value = pack.hotspot[0];
  $("#hotspot-y").value = pack.hotspot[1];
  spriteState();
}
$("#export").onclick = () => {
  const blob = new Blob([JSON.stringify(pack, null, 2)], {
    type: "application/json",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download =
    (pack.name.replace(/[^a-zA-Z0-9_-]/g, "_") || "character") +
    ".tobkiri.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast("キャラクターを書き出しました。");
};
$("#import").onclick = () => $("#pack-file").click();
$("#pack-file").onchange = async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  try {
    if (file.size > 8000000) throw Error("ファイルは8MB以内にしてください。");
    pack = validatePack(JSON.parse(await file.text()));
    character.pack = pack;
    sync();
    await loadDrawing();
    save();
    toast("キャラクターを読み込みました。");
  } catch (error) {
    toast(error.message);
  }
};
$("#reset").onclick = async () => {
  pack = structuredClone(defaults);
  character.pack = pack;
  sync();
  await loadDrawing();
  save();
  toast("標準のMochiに戻しました。");
};
function updateDesktop(state) {
  desktopState = state;
  $("#desktop-toggle").textContent = state.enabled
    ? "✓ デスクトップ表示中"
    : "↗ デスクトップに出す";
  $("#connection").textContent =
    state.status === "listening" ? "Computer Use を待っています" : state.status;
  $("#integration-copy").textContent =
    `Python: Computer(companion=True) / MCP: TOBKIRI_COMPANION=1 · 非表示は Ctrl / ⌘ + Shift + F8`;
}
if (native) {
  updateDesktop(desktopState);
  native.onConfig(updateDesktop);
  native.onEvent((event) => {
    if (event.source !== "pointer")
      $("#connection").textContent =
        event.phase === "hide"
          ? "操作先を非表示"
          : "接続中 · " +
            (motions.find((m) => m[0] === event.action)?.[1] ?? "移動");
  });
} else $("#connection").textContent = "ブラウザプレビュー · この端末に保存";
$("#desktop-toggle").onclick = async () => {
  if (!native) {
    toast(
      "デスクトップ表示は companion フォルダーで npm start を実行してください。",
    );
    return;
  }
  try {
    updateDesktop(await native.show(!desktopState.enabled));
  } catch (error) {
    toast(error.message);
  }
};
const pixel = document.createElement("canvas");
pixel.width = pixel.height = 32;
const pix = pixel.getContext("2d"),
  drawing = $("#cursor-drawing"),
  pen = drawing.getContext("2d");
let drawingImage = "";
function drawGrid() {
  pen.clearRect(0, 0, 256, 256);
  pen.imageSmoothingEnabled = false;
  pen.drawImage(pixel, 0, 0, 256, 256);
  pen.strokeStyle = "#9b8fb619";
  pen.lineWidth = 1;
  for (let i = 0; i <= 32; i++) {
    pen.beginPath();
    pen.moveTo(i * 8, 0);
    pen.lineTo(i * 8, 256);
    pen.moveTo(0, i * 8);
    pen.lineTo(256, i * 8);
    pen.stroke();
  }
  pen.strokeStyle = "#ee6d50";
  pen.lineWidth = 2;
  pen.strokeRect(pack.hotspot[0] * 8 + 1, pack.hotspot[1] * 8 + 1, 6, 6);
}
async function loadDrawing() {
  pix.clearRect(0, 0, 32, 32);
  if (pack.cursorImage) {
    const im = new Image();
    im.src = pack.cursorImage;
    await im.decode();
    pix.drawImage(im, 0, 0, 32, 32);
  }
  drawingImage = pack.cursorImage;
  drawGrid();
}
function drawPixel(e) {
  const r = drawing.getBoundingClientRect(),
    x = Math.floor(((e.clientX - r.left) * 32) / r.width),
    y = Math.floor(((e.clientY - r.top) * 32) / r.height);
  if (x < 0 || x > 31 || y < 0 || y > 31) return;
  if (e.shiftKey) pix.clearRect(x, y, 1, 1);
  else {
    pix.fillStyle = pack.cursorColor;
    pix.fillRect(x, y, 1, 1);
  }
  drawGrid();
}
drawing.onpointerdown = (e) => {
  drawing.setPointerCapture(e.pointerId);
  drawPixel(e);
};
drawing.onpointermove = (e) => {
  if (e.buttons === 1) drawPixel(e);
};
function finishDrawing() {
  apply({ cursor: "custom", cursorImage: pixel.toDataURL("image/png") });
  drawingImage = pack.cursorImage;
}
drawing.onpointerup = finishDrawing;
drawing.onpointercancel = finishDrawing;
$("#cursor-clear").onclick = () => {
  pix.clearRect(0, 0, 32, 32);
  drawGrid();
  finishDrawing();
};
for (const [i, id] of ["hotspot-x", "hotspot-y"].entries())
  $("#" + id).onchange = () => {
    const next = [...pack.hotspot];
    next[i] = Math.max(
      0,
      Math.min(31, Math.round(Number($("#" + id).value) || 0)),
    );
    apply({ hotspot: next });
    drawGrid();
  };
async function readPNG(file) {
  if (!file || file.type !== "image/png" || file.size > 2000000)
    throw Error("2MB以下のPNGを選んでください。");
  const data = await new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
  const im = new Image();
  im.src = data;
  await im.decode();
  if (im.naturalWidth > 8192 || im.naturalHeight > 4096)
    throw Error("画像は8192 × 4096以内にしてください。");
  return { data, im };
}
$("#cursor-import").onclick = () => $("#cursor-file").click();
$("#cursor-file").onchange = async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  try {
    const { im } = await readPNG(file);
    pix.clearRect(0, 0, 32, 32);
    pix.drawImage(im, 0, 0, 32, 32);
    drawGrid();
    finishDrawing();
  } catch (error) {
    toast(error.message);
  }
};
for (const m of motions) {
  const option = document.createElement("option");
  option.value = m[0];
  option.textContent = m[1];
  $("#sprite-action").append(option);
}
function spriteState() {
  const a = $("#sprite-action").value,
    s = pack.sprites[a];
  $("#sprite-state").textContent = s
    ? `カスタムPNG · ${s.frames} フレーム / ${s.fps} FPS`
    : "標準のしぐさを使用中";
}
$("#sprite-action").onchange = () => {
  spriteState();
  selectMotion($("#sprite-action").value);
};
$("#sprite-import").onclick = () => $("#sprite-file").click();
$("#sprite-file").onchange = async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  try {
    const { data, im } = await readPNG(file),
      frames = Number($("#sprite-frames").value),
      fps = Number($("#sprite-fps").value),
      action = $("#sprite-action").value;
    if (im.naturalWidth % frames !== 0)
      throw Error("画像の横幅をフレーム数で割り切れるようにしてください。");
    apply({
      sprites: { ...pack.sprites, [action]: { image: data, frames, fps } },
    });
    selectMotion(action);
    toast("自作アニメーションを追加しました。");
  } catch (error) {
    toast(error.message);
  }
};
$("#sprite-reset").onclick = () => {
  const next = { ...pack.sprites };
  delete next[$("#sprite-action").value];
  apply({ sprites: next });
};
const motionCards = $$(".motion-card").map((card) => ({
  card,
  canvas: card.querySelector("canvas"),
}));
const presetCanvases = $$(".preset").map((card) =>
  card.querySelector("canvas"),
);
function frame(now) {
  const elapsed = Math.max(0, (now - last) / 1000);
  const dt = Math.min(elapsed, 0.05);
  last = now;
  const { ctx, width, height } = fitCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  if (!paused) {
    if (demo) {
      demoTime += dt;
      const i = Math.floor(demoTime / 3) % demoSteps.length,
        [action, x, y] = demoSteps[i];
      character.tx = width * x;
      character.ty = height * y;
      if (i !== lastStep) {
        selectMotion(action, { keepDemo: true });
        lastStep = i;
      }
    }
    character.update(dt);
  }
  character.draw(ctx);
  frames++;
  // Measure wall time, not the clamped physics step, so stalls remain visible.
  fpsTime += elapsed;
  if (fpsTime > 1) {
    $("#fps").textContent = `${Math.round(frames / fpsTime)} FPS`;
    frames = 0;
    fpsTime = 0;
  }
  {
    const library = $("#motion-grid").getBoundingClientRect();
    for (const { card, canvas: c } of motionCards) {
      if (card.hidden) continue;
      const rect = card.getBoundingClientRect();
      if (
        rect.bottom < Math.max(0, library.top) ||
        rect.top > Math.min(innerHeight, library.bottom)
      )
        continue;
      const { ctx: cx, width: w, height: h } = fitCanvas(c);
      cx.clearRect(0, 0, w, h);
      cx.save();
      cx.translate(w / 2, h - 7);
      cx.scale(0.32, 0.32);
      drawCharacter(
        cx,
        poseFor(
          card.dataset.motion,
          paused || pack.reducedMotion ? 0 : now / 1000,
          pack,
        ),
        pack,
        card.dataset.motion,
        paused || pack.reducedMotion ? 0 : now / 1000,
      );
      cx.restore();
    }
    presetCanvases.forEach((canvas, i) => {
      if (!canvas.offsetWidth) return;
      const { ctx: cx, width: w, height: h } = fitCanvas(canvas);
      cx.clearRect(0, 0, w, h);
      cx.save();
      cx.translate(w / 2, h - 2);
      cx.scale(0.3, 0.3);
      const p = { ...defaults, ...presets[i] };
      drawCharacter(cx, poseFor("idle", 0, p), p, "idle", 0);
      cx.restore();
    });
  }
  requestAnimationFrame(frame);
}
sync();
await loadDrawing();
requestAnimationFrame(frame);
