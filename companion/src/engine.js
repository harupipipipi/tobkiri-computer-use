import { defaults, motionIds } from "./config.js";
import { extraPose, idleMotion } from "./motions.js";
const TAU = Math.PI * 2;
export const lerp = (a, b, t) => a + (b - a) * t;
export const smooth = (current, target, dt, rate = 12) =>
  lerp(current, target, 1 - Math.exp(-Math.max(0, Math.min(dt, 0.05)) * rate));
// Explicit ten-joint pose: head, neck, hip, left hand, right hand, left knee, right knee, left foot, right foot, gaze.
export function poseFor(action, time, pack = defaults) {
  const t = time * pack.speed,
    s = Math.sin(t * TAU),
    c = Math.cos(t * TAU);
  let p = [
    [0, -99],
    [0, -77],
    [0, -43],
    [-24, -48],
    [24, -48],
    [-12, -22],
    [12, -22],
    [-17, 0],
    [17, 0],
    [2, 0],
  ];
  const custom = pack.clips?.[action];
  if (custom) {
    const frame = (((t % 1) + 1) % 1) * custom.length,
      i = Math.floor(frame),
      u = (1 - Math.cos((frame - i) * Math.PI)) / 2;
    return custom[i].map((v, j) =>
      v.map((n, k) => lerp(n, custom[(i + 1) % custom.length][j][k], u)),
    );
  }
  const shift = (x, y) => {
    p = p.map((v, i) => (i === 9 ? v : [v[0] + x, v[1] + y]));
  };
  const extra = extraPose(action, t);
  if (extra) return extra;
  switch (action) {
    case "walk":
    case "run":
    case "dash": {
      const a = Math.sin(t * TAU * (action === "walk" ? 1.3 : 2.4)),
        fast = action !== "walk";
      p[3] = [-14 - a * 24, -54];
      p[4] = [14 + a * 24, -54];
      p[5] = [-a * 22, -25];
      p[6] = [a * 22, -25];
      p[7] = [-a * 34, -Math.max(0, a) * 21];
      p[8] = [a * 34, -Math.max(0, -a) * 21];
      p[0][0] = fast ? 16 : 5;
      p[1][0] = fast ? 10 : 3;
      if (action === "dash") {
        p[0][0] = 32;
        p[1][0] = 22;
        p[3] = [-29, -69];
        p[4] = [-19, -56];
      }
      shift(0, -Math.abs(a) * (fast ? 8 : 3));
      break;
    }
    case "jump": {
      const hop = Math.max(0, Math.sin(t * Math.PI * 1.4));
      p[3] = [-29, -104];
      p[4] = [29, -104];
      p[7] = [-25, -hop * 18];
      p[8] = [25, -hop * 18];
      shift(0, -hop * 48);
      break;
    }
    case "land":
      p[0][1] += 24;
      p[1][1] += 24;
      p[2][1] += 20;
      p[3] = [-34, -17];
      p[4] = [34, -17];
      p[5] = [-24, -15];
      p[6] = [24, -15];
      shift(0, Math.sin(t * 6) * 2);
      break;
    case "click":
    case "double_click":
    case "right_click": {
      const tap = Math.max(
        0,
        Math.sin(t * TAU * (action === "double_click" ? 3 : 1.4)),
      );
      p[4] = [39 + tap * 6, -53 + tap * 12];
      p[0][0] = 8;
      p[1][0] = 6;
      p[3] = [-17, -45];
      p[9] = [4, 2];
      if (action === "right_click") p[3] = [-12, -85];
      break;
    }
    case "type":
    case "key":
      p[3] = [12, -48 + Math.sin(t * 31) * 5];
      p[4] = [37, -48 + Math.cos(t * 31) * 5];
      p[0] = [10, -94];
      p[1][0] = 6;
      p[9] = [3, 3];
      if (action === "key") p[4][1] -= Math.max(0, s) * 15;
      break;
    case "scroll_up":
    case "scroll_down": {
      const y = (action === "scroll_up" ? -s : s) * 25;
      p[3] = [27, -60 + y];
      p[4] = [39, -60 - y];
      p[0][0] = 8;
      p[9] = [4, action === "scroll_up" ? -3 : 3];
      break;
    }
    case "drag":
      p[0] = [-15, -91];
      p[1] = [-10, -70];
      p[3] = [27, -59];
      p[4] = [39, -56];
      p[7] = [-32, 0];
      p[8] = [21, 0];
      shift(s * 3, 0);
      break;
    case "grab":
      p[3] = [25, -81];
      p[4] = [37, -76];
      p[0][0] = 9;
      p[9] = [3, -2];
      break;
    case "think":
      p[4] = [13, -87];
      p[3] = [-14, -44];
      p[0][0] = 6;
      p[9] = [2, -3];
      shift(0, s * 1.5);
      break;
    case "wait":
      p[3] = [-8, -40];
      p[4] = [8, -40];
      p[8][1] = -Math.max(0, Math.sin(t * 12)) * 5;
      p[9] = [s * 3, 0];
      break;
    case "wave":
      p[4] = [31 + s * 11, -105];
      p[3] = [-22, -51];
      p[0][0] = s * 3;
      break;
    case "celebrate":
      p[3] = [-35, -109 + s * 6];
      p[4] = [35, -109 - s * 6];
      p[7] = [-24, 0];
      p[8] = [24, 0];
      shift(0, -Math.abs(s) * 17);
      break;
    case "confused":
      p[3] = [-32, -76];
      p[4] = [32, -76];
      p[0][0] = s * 6;
      p[9] = [-s * 3, -2];
      break;
    case "sleep":
      p[0] = [15, -59];
      p[1] = [0, -42];
      p[2] = [0, -18];
      p[3] = [15, -36];
      p[4] = [23, -34];
      p[5] = [-20, -8];
      p[6] = [24, -8];
      p[7] = [-27, 0];
      p[8] = [31, 0];
      shift(0, Math.sin(t * 2) * 2);
      break;
    case "stretch":
      p[3] = [-15, -133 + s * 3];
      p[4] = [15, -133 + s * 3];
      p[0][1] -= 3;
      p[7] = [-12, 0];
      p[8] = [12, 0];
      break;
    case "bow":
      p[0] = [31, -65 + s * 3];
      p[1] = [22, -52];
      p[3] = [34, -22];
      p[4] = [39, -22];
      p[9] = [2, 4];
      break;
    case "climb":
      p[3] = [-26, -108 + s * 16];
      p[4] = [26, -108 - s * 16];
      p[5] = [-22, -36 - s * 12];
      p[6] = [22, -36 + s * 12];
      p[7] = [-23, -15 - s * 12];
      p[8] = [23, -15 + s * 12];
      shift(0, s * 4);
      break;
    case "float":
      p[3] = [-34, -63 + s * 7];
      p[4] = [34, -63 - s * 7];
      p[7] = [-24, -8];
      p[8] = [24, -4];
      shift(s * 4, -18 + c * 8);
      break;
    case "dance":
      p[0][0] = s * 12;
      p[1][0] = s * 8;
      p[3] = [-33, -78 + c * 24];
      p[4] = [33, -78 - c * 24];
      p[7] = [-25, -Math.max(0, s) * 12];
      p[8] = [25, -Math.max(0, -s) * 12];
      shift(0, -Math.abs(s) * 4);
      break;
    case "peek":
      p[0] = [25, -97];
      p[1][0] = 14;
      p[4] = [26, -86];
      p[3] = [-10, -46];
      p[9] = [5, 0];
      break;
    case "sit":
      p[0][1] += 29;
      p[1][1] += 29;
      p[2][1] += 24;
      p[3] = [-21, -16];
      p[4] = [21, -16];
      p[5] = [-23, -7];
      p[6] = [23, -7];
      p[7] = [-33, 0];
      p[8] = [33, 0];
      break;
    case "balance":
      p[3] = [-44, -76 + s * 6];
      p[4] = [44, -76 - s * 6];
      p[8] = [36, -21];
      p[6] = [16, -31];
      shift(s * 4, 0);
      break;
    case "spin": {
      const spin = Math.cos(t * 6);
      p = p.map((v, i) => (i === 9 ? v : [v[0] * spin, v[1]]));
      p[3][1] = -77;
      p[4][1] = -77;
      break;
    }
    default:
      p[0][1] += Math.sin(t * 2.4) * 2;
      p[1][1] += Math.sin(t * 2.4);
      p[3][0] += Math.sin(t * 2) * 2;
      p[4][0] -= Math.sin(t * 2) * 2;
  }
  return p;
}
const images = new Map();
function bitmap(data) {
  if (!data) return null;
  if (!images.has(data)) {
    if (images.size > 64) images.clear();
    const im = new Image();
    im.src = data;
    images.set(data, im);
  }
  const im = images.get(data);
  return im.complete && im.naturalWidth ? im : null;
}
function line(ctx, points, color, width) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.stroke();
}
function dot(ctx, x, y, r, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, TAU);
  ctx.fill();
}
function limb(ctx, start, end, bend, color, width) {
  const middle = [(start[0] + end[0]) / 2 + bend, (start[1] + end[1]) / 2 - 4];
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(...start);
  ctx.quadraticCurveTo(...middle, ...end);
  ctx.stroke();
}
export function drawCharacter(
  ctx,
  pose,
  pack,
  action,
  time,
  { shadow = true, facing = 1 } = {},
) {
  const sprite = pack.sprites?.[action],
    im = sprite && bitmap(sprite.image);
  if (im) {
    const w = im.naturalWidth / sprite.frames,
      frame = Math.floor(time * sprite.fps * pack.speed) % sprite.frames,
      scale = Math.min(160 / w, 125 / im.naturalHeight);
    ctx.save();
    ctx.scale(facing < 0 ? -1 : 1, 1);
    ctx.drawImage(
      im,
      frame * w,
      0,
      w,
      im.naturalHeight,
      (-w * scale) / 2,
      -im.naturalHeight * scale,
      w * scale,
      im.naturalHeight * scale,
    );
    ctx.restore();
    return;
  }
  // Turn joints in place, retaining a round head and constant line thickness.
  // Scaling the whole canvas through zero made the character paper-thin.
  pose = pose.map(([x, y]) => [x * facing, y]);
  const [head, neck, hip, lh, rh, lk, rk, lf, rf, gaze] = pose;
  if (shadow) {
    ctx.fillStyle = "#302c4312";
    ctx.beginPath();
    ctx.ellipse(0, 5, 35, 5, 0, 0, TAU);
    ctx.fill();
  }
  line(ctx, [hip, lk, lf], pack.color, pack.weight);
  line(ctx, [hip, rk, rf], pack.color, pack.weight);
  line(ctx, [neck, hip], pack.color, pack.weight + 1);
  limb(ctx, neck, lh, -8 * facing, pack.color, pack.weight);
  limb(ctx, neck, rh, 8 * facing, pack.color, pack.weight);
  if (pack.accessory === "scarf") {
    line(
      ctx,
      [
        [neck[0] - 8, neck[1] - 1],
        [neck[0] + 9, neck[1] + 1],
      ],
      pack.accent,
      8,
    );
    ctx.fillStyle = pack.accent;
    ctx.beginPath();
    ctx.moveTo(neck[0] - 5 * facing, neck[1]);
    ctx.quadraticCurveTo(
      neck[0] - 20 * facing,
      neck[1] + 8,
      neck[0] - 31 * facing,
      neck[1] + Math.sin(time * 6) * 6,
    );
    ctx.lineTo(neck[0] - 24 * facing, neck[1] + 15 + Math.sin(time * 6) * 5);
    ctx.lineTo(neck[0] - 4 * facing, neck[1] + 7);
    ctx.fill();
  }
  dot(ctx, ...head, pack.head, pack.color);
  if (pack.accessory === "antenna") {
    line(
      ctx,
      [
        [head[0], head[1] - pack.head],
        [head[0] + Math.sin(time * 3) * 5, head[1] - pack.head - 12],
      ],
      pack.color,
      3,
    );
    dot(
      ctx,
      head[0] + Math.sin(time * 3) * 5,
      head[1] - pack.head - 13,
      4,
      pack.accent,
    );
  }
  if (pack.eyes) {
    const blink = action === "sleep" || Math.sin(time * 0.85) > 0.997;
    for (const x of [-5, 5]) {
      if (blink)
        line(
          ctx,
          [
            [head[0] + x - 2, head[1] + gaze[1]],
            [head[0] + x + 2, head[1] + gaze[1]],
          ],
          "#ffffff",
          2,
        );
      else dot(ctx, head[0] + x + gaze[0], head[1] + gaze[1], 2, "#fff");
    }
  }
  if (["type", "key"].includes(action)) {
    ctx.save();
    ctx.scale(facing, 1);
    ctx.fillStyle = "#eceaf5";
    ctx.strokeStyle = pack.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.roundRect(1, -39, 53, 13, 4);
    ctx.fill();
    ctx.stroke();
    for (let i = 0; i < 8; i++) dot(ctx, 7 + i * 5.5, -33, 1.1, pack.color);
    ctx.restore();
  }
  if (action === "think" || action === "confused" || action === "sleep") {
    ctx.fillStyle = pack.color;
    ctx.font = "bold 18px sans-serif";
    ctx.fillText(
      action === "think" ? "···" : action === "confused" ? "?" : "z",
      head[0] + 25 * facing,
      head[1] - 20 - Math.sin(time * 3) * 3,
    );
  }
  if (action === "celebrate") {
    for (let i = 0; i < 8; i++) {
      const a = (i * TAU) / 8 + time * 0.4;
      dot(
        ctx,
        Math.cos(a) * 52,
        -80 + Math.sin(a) * 43,
        2.5,
        i % 2 ? pack.color : pack.accent,
      );
    }
  }
  if (action === "scroll_up" || action === "scroll_down") {
    const d = action === "scroll_up" ? -1 : 1;
    line(
      ctx,
      [
        [53, -77],
        [53, -50],
      ],
      pack.accent,
      3,
    );
    line(
      ctx,
      [
        [47, -64 + d * 13],
        [53, -58 + d * 13],
        [59, -64 + d * 13],
      ],
      pack.accent,
      3,
    );
  }
}
export function drawCursor(ctx, x, y, pack, phase = 0) {
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = pack.cursorColor;
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 2;
  ctx.lineJoin = "round";
  const im = pack.cursor === "custom" && bitmap(pack.cursorImage);
  if (im) ctx.drawImage(im, -pack.hotspot[0], -pack.hotspot[1], 32, 32);
  else if (pack.cursor === "ring") {
    ctx.strokeStyle = pack.cursorColor;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(0, 0, 8, 0, TAU);
    ctx.stroke();
    dot(ctx, 0, 0, 2, pack.cursorColor);
  } else if (pack.cursor === "star") {
    ctx.beginPath();
    for (let i = 0; i < 10; i++) {
      const a = (i * Math.PI) / 5 - Math.PI / 2,
        r = i % 2 ? 5 : 11;
      ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r);
    }
    ctx.closePath();
    ctx.stroke();
    ctx.fill();
  } else {
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(0, 21);
    ctx.lineTo(6, 16);
    ctx.lineTo(10, 25);
    ctx.lineTo(15, 23);
    ctx.lineTo(11, 14);
    ctx.lineTo(20, 14);
    ctx.closePath();
    ctx.stroke();
    ctx.fill();
  }
  if (phase > 0) {
    ctx.strokeStyle = pack.color;
    ctx.globalAlpha = 1 - phase;
    ctx.beginPath();
    ctx.arc(0, 0, 6 + phase * 25, 0, TAU);
    ctx.stroke();
  }
  ctx.restore();
}
export class Character {
  constructor(pack = defaults, x = 0, y = 0) {
    this.pack = pack;
    this.x = x;
    this.y = y;
    this.tx = x;
    this.ty = y;
    this.action = "idle";
    this.actionStarted = 0;
    this.until = 0;
    this.time = 0;
    this.stillTime = 0;
    this.facing = 1;
    this.facingBlend = 1;
    this.pose = poseFor("idle", 0, pack);
    this.trail = [];
    this.lastSeen = performance.now();
    this.hidden = false;
    this.active = false;
    this.clickAt = -100;
  }
  play(action, duration = 2) {
    this.action = motionIds.includes(action) ? action : "idle";
    this.actionStarted = this.time;
    this.until = this.time + duration;
    if (action.includes("click")) this.clickAt = this.time;
  }
  receive(e) {
    this.lastSeen = performance.now();
    this.hidden = e.phase === "hide";
    if (this.hidden) {
      this.pending = null;
      return;
    }
    this.tx = e.point[0];
    this.ty = e.point[1];
    if (e.phase === "prepare") {
      this.pending = { event: e, posedAt: null };
      this.until = 0;
    }
    if (e.phase === "start") {
      this.pending = null;
      this.active = true;
      this.play(e.action, 30);
    }
    if (e.phase === "end") {
      this.active = false;
      this.play(
        e.outcome === "error" || e.outcome === "refused"
          ? "confused"
          : e.action,
        1.2,
      );
    }
  }
  update(dt) {
    dt = Math.min(0.05, Math.max(0, dt));
    this.time += dt;
    const dx = this.tx - this.x,
      dy = this.ty - this.y,
      dist = Math.hypot(dx, dy);
    if (Math.abs(dx) > 2) this.facing = dx > 0 ? 1 : -1;
    // Turn the body continuously. Flipping the ±42px body offset in one frame
    // used to teleport the character by 84px even for a tiny pointer reversal.
    this.facingBlend = this.pack.reducedMotion
      ? this.facing
      : smooth(this.facingBlend, this.facing, dt, 14);
    this.x = this.pack.reducedMotion
      ? this.tx
      : smooth(this.x, this.tx, dt, 9 * this.pack.speed);
    this.y = this.pack.reducedMotion
      ? this.ty
      : smooth(this.y, this.ty, dt, 9 * this.pack.speed);
    this.stillTime = dist > 5 ? 0 : this.stillTime + dt;
    if (this.time > this.until) {
      const next =
        dist > 120 ? "run" : dist > 5 ? "walk" : idleMotion(this.stillTime);
      if (next !== this.action) {
        this.action = next;
        this.actionStarted = this.time;
      }
    }
    const target = poseFor(
      this.pack.reducedMotion ? "idle" : this.action,
      this.pack.reducedMotion ? 0 : this.time - this.actionStarted,
      this.pack,
    );
    this.pose = this.pose.map((p, i) =>
      p.map((v, j) => smooth(v, target[i][j], dt, 18)),
    );
    if (this.pack.trail && dist > 8 && !this.pack.reducedMotion) {
      this.trail.push({ x: this.x, y: this.y, t: this.time });
    }
    this.trail = this.trail.filter((p) => this.time - p.t < 0.28).slice(-20);
  }
  draw(ctx, { cursor = true, shadow = true } = {}) {
    if (this.hidden) return;
    const scale = this.pack.size / 100;
    const showCursor = cursor && this.pack.displayMode === "both";
    for (const p of showCursor ? this.trail : []) {
      ctx.globalAlpha = Math.max(0, 0.22 - (this.time - p.t) * 0.75);
      dot(ctx, p.x, p.y, 3, this.pack.color);
    }
    ctx.globalAlpha = 1;
    ctx.save();
    ctx.translate(this.x - 42 * scale * this.facingBlend, this.y + 54 * scale);
    ctx.scale(scale, scale);
    drawCharacter(
      ctx,
      this.pose,
      this.pack,
      this.pack.reducedMotion ? "idle" : this.action,
      this.pack.reducedMotion ? 0 : this.time,
      {
        shadow,
        facing: this.facingBlend,
      },
    );
    ctx.restore();
    // The hotspot is exact; only the character follows with easing.
    if (showCursor)
      drawCursor(
        ctx,
        this.tx,
        this.ty,
        this.pack,
        !this.pack.reducedMotion && this.time - this.clickAt < 0.5
          ? (this.time - this.clickAt) * 2
          : 0,
      );
  }
}
export function fitCanvas(canvas) {
  const rect = canvas.getBoundingClientRect(),
    dpr = Math.min(devicePixelRatio || 1, 2);
  if (
    canvas.width !== Math.round(rect.width * dpr) ||
    canvas.height !== Math.round(rect.height * dpr)
  ) {
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width: rect.width, height: rect.height };
}
