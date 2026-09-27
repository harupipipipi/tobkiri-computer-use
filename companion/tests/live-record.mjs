// Opt-in recording of a real, visible target plus the native character overlay.
// Bounds must come from a freshly observed dedicated target. No simulated input.
import { _electron as electron } from "@playwright/test";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
const bounds = JSON.parse(await fs.readFile(process.argv[2], "utf8"));
const duration = Number(process.argv[3] || 60);
const name = process.argv[4] || "live-control";
if (!/^[a-z0-9-]+$/.test(name)) throw Error("Invalid recording name");
if (
  !["x", "y", "width", "height"].every((k) => Number.isFinite(bounds[k])) ||
  bounds.width < 2 ||
  bounds.height < 2 ||
  !Number.isFinite(duration) ||
  duration <= 0 ||
  duration > 180
)
  throw Error(
    "A verified target rectangle and bounded recording duration are required",
  );
const folder = path.resolve("test-results/recordings");
await fs.mkdir(folder, { recursive: true });
const env = {
  ...process.env,
  TOBKIRI_COMPANION_PORT: process.argv[5] || "47831",
};
delete env.ELECTRON_RUN_AS_NODE;
const app = await electron.launch({
  args: [".", "--record-test", "--agent-mode", "--recordable"],
  env,
});
let capture;
try {
  await app.firstWindow();
  let studio;
  for (let i = 0; i < 100; i++) {
    studio = app.windows().find((w) => w.url().includes("index.html"));
    if (studio) break;
    await new Promise((r) => setTimeout(r, 100));
  }
  if (!studio)
    throw Error("Studio did not load: " + app.windows().map((w) => w.url()));
  await studio.waitForSelector("#motion-grid button", { state: "attached" });
  await studio.waitForFunction(async () => {
    const state = await window.companion.getState();
    if (state.status.includes("エラー")) throw Error(state.status);
    return state.status === "listening";
  });
  const pages = app.windows().filter((w) => w.url().includes("overlay.html"));
  for (const page of pages) {
    await page.waitForLoadState();
    await page.evaluate(() => {
      window.liveMeasure = { frames: [], events: [], last: null };
      const original = requestAnimationFrame.bind(window);
      window.requestAnimationFrame = (callback) =>
        original((now) => {
          const m = window.liveMeasure;
          if (m.last !== null) m.frames.push(now - m.last);
          m.last = now;
          callback(now);
        });
      window.companion.onEvent((e) => {
        if (e.phase !== "anchor")
          window.liveMeasure.events.push({ ...e, time: performance.now() });
      });
    });
  }
  const width = Math.floor(bounds.width / 2) * 2,
    height = Math.floor(bounds.height / 2) * 2;
  const output = path.join(folder, `${name}.mp4`);
  let log = "";
  capture = spawn(
    "ffmpeg",
    [
      "-hide_banner",
      "-y",
      "-f",
      "lavfi",
      "-i",
      `ddagrab=framerate=60:video_size=${width}x${height}:offset_x=${Math.round(bounds.x)}:offset_y=${Math.round(bounds.y)}:draw_mouse=0`,
      "-t",
      String(duration),
      "-vf",
      "hwdownload,format=bgra",
      "-c:v",
      "libx264",
      "-preset",
      "ultrafast",
      "-crf",
      "18",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      output,
    ],
    { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] },
  );
  capture.stderr.on("data", (b) => (log += b));
  console.log("LIVE RECORDING STARTED: " + output);
  await new Promise((resolve, reject) => {
    capture.on("error", reject);
    capture.on("exit", (code) => (code === 0 ? resolve() : reject(Error(log))));
  });
  const reports = [];
  for (const page of pages)
    reports.push(await page.evaluate(() => window.liveMeasure));
  await fs.writeFile(
    path.join(folder, `${name}.json`),
    JSON.stringify({ bounds, duration, reports }, null, 2),
  );
  await fs.writeFile(path.join(folder, `${name}.ffmpeg.log`), log);
  console.log(
    JSON.stringify(
      reports.map((r) => ({
        frames: r.frames.length,
        maxMs: Math.max(...r.frames),
        events: r.events.length,
      })),
    ),
  );
} finally {
  if (capture?.exitCode === null) capture.kill();
  await app.close();
}
