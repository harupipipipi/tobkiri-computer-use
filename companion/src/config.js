import { extraMotions } from "./motions.js";
export const motions = [
  ["idle", "ひと休み", "Idle"],
  ["walk", "あるく", "Walk"],
  ["run", "はしる", "Run"],
  ["dash", "ダッシュ", "Dash"],
  ["jump", "ジャンプ", "Jump"],
  ["land", "着地", "Land"],
  ["click", "クリック", "Click"],
  ["double_click", "ダブルクリック", "Double tap"],
  ["right_click", "右クリック", "Right click"],
  ["type", "タイピング", "Typing"],
  ["key", "キーを押す", "Key press"],
  ["scroll_up", "上にスクロール", "Scroll up"],
  ["scroll_down", "下にスクロール", "Scroll down"],
  ["drag", "ひっぱる", "Drag"],
  ["grab", "つかむ", "Grab"],
  ["think", "考え中", "Thinking"],
  ["wait", "待ってる", "Waiting"],
  ["wave", "手をふる", "Wave"],
  ["celebrate", "やった！", "Celebrate"],
  ["confused", "あれ？", "Confused"],
  ["sleep", "うとうと", "Sleep"],
  ["stretch", "のびをする", "Stretch"],
  ["bow", "おじぎ", "Bow"],
  ["climb", "よじのぼる", "Climb"],
  ["float", "ふわふわ", "Float"],
  ["dance", "ダンス", "Dance"],
  ["peek", "のぞきこむ", "Peek"],
  ["sit", "すわる", "Sit"],
  ["balance", "バランス", "Balance"],
  ["spin", "くるり", "Spin"],
  ...extraMotions,
];
export const motionIds = motions.map((m) => m[0]);
export const defaults = {
  version: 1,
  name: "Mochi",
  color: "#7764e8",
  accent: "#b9f373",
  size: 100,
  weight: 9,
  head: 17,
  speed: 1,
  trail: true,
  eyes: true,
  accessory: "scarf",
  cursor: "arrow",
  displayMode: "pet",
  cursorColor: "#302c43",
  cursorImage: "",
  hotspot: [0, 0],
  mode: "computer",
  reducedMotion: false,
  sprites: {},
  clips: {},
};
const numeric = {
  size: [45, 180],
  weight: [4, 16],
  head: [10, 25],
  speed: [0.3, 2],
};
const colors = ["color", "accent", "cursorColor"];
export function validatePack(input) {
  if (
    !input ||
    typeof input !== "object" ||
    Array.isArray(input) ||
    input.version !== 1
  )
    throw Error("version: 1 のキャラクターファイルを選んでください。");
  const out = structuredClone(defaults);
  out.name = String(input.name ?? defaults.name).slice(0, 32);
  for (const [key, [min, max]] of Object.entries(numeric)) {
    if (
      key in input &&
      (!Number.isFinite(input[key]) || input[key] < min || input[key] > max)
    )
      throw Error(`${key} は ${min}〜${max} です。`);
    if (key in input) out[key] = input[key];
  }
  for (const key of colors) {
    if (key in input && !/^#[\da-f]{6}$/i.test(input[key]))
      throw Error("色は #rrggbb 形式です。");
    if (key in input) out[key] = input[key];
  }
  for (const key of ["trail", "eyes", "reducedMotion"])
    if (key in input) out[key] = input[key] === true;
  for (const [key, values] of Object.entries({
    accessory: ["scarf", "antenna", "none"],
    cursor: ["arrow", "star", "ring", "custom"],
    displayMode: ["pet", "both"],
    mode: ["computer", "pointer"],
  })) {
    if (key in input && !values.includes(input[key]))
      throw Error(`${key} の値が不正です。`);
    if (key in input) out[key] = input[key];
  }
  const validImage = (s) =>
    typeof s === "string" &&
    s.length <= 2800000 &&
    /^data:image\/png;base64,[a-z\d+/=]+$/i.test(s);
  if (input.cursorImage) {
    if (!validImage(input.cursorImage))
      throw Error("カーソルにはPNGを使用してください。");
    out.cursorImage = input.cursorImage;
  }
  if (input.hotspot) {
    if (
      !Array.isArray(input.hotspot) ||
      input.hotspot.length !== 2 ||
      input.hotspot.some((n) => !Number.isFinite(n) || n < 0 || n > 31)
    )
      throw Error("ホットスポットは0〜31です。");
    out.hotspot = input.hotspot;
  }
  for (const [key, s] of Object.entries(input.sprites ?? {})) {
    if (
      !motionIds.includes(key) ||
      !s ||
      !validImage(s.image) ||
      !Number.isInteger(s.frames) ||
      s.frames < 1 ||
      s.frames > 64 ||
      !Number.isFinite(s.fps) ||
      s.fps < 1 ||
      s.fps > 60
    )
      throw Error(
        "スプライト設定が不正です。横一列のPNGと1〜64フレームを指定してください。",
      );
    out.sprites[key] = { image: s.image, frames: s.frames, fps: s.fps };
  }
  // Custom skeletal clips are data, never executable code. Coordinates are relative to the character's feet.
  for (const [key, clip] of Object.entries(input.clips ?? {})) {
    if (
      !motionIds.includes(key) ||
      !Array.isArray(clip) ||
      clip.length < 2 ||
      clip.length > 24
    )
      throw Error("クリップには2〜24個のポーズを指定してください。");
    out.clips[key] = clip.map((p) => {
      if (
        !Array.isArray(p) ||
        p.length !== 10 ||
        p.some(
          (v) =>
            !Array.isArray(v) ||
            v.length !== 2 ||
            v.some((n) => !Number.isFinite(n) || Math.abs(n) > 200),
        )
      )
        throw Error("ポーズは10関節の [x,y] 配列です。");
      return p.map((v) => [...v]);
    });
  }
  if (JSON.stringify(out).length > 8000000)
    throw Error("キャラクターファイルは8MB以内にしてください。");
  return out;
}
export const presets = [
  { name: "Mochi", color: "#7764e8", accent: "#b9f373", accessory: "scarf" },
  { name: "Ember", color: "#ee6d50", accent: "#ffd275", accessory: "none" },
  { name: "Mint", color: "#359c8c", accent: "#bdeadd", accessory: "antenna" },
  { name: "Ink", color: "#343440", accent: "#b8bcff", accessory: "scarf" },
];
