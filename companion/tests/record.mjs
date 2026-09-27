// Opt-in recording of this app's visible playground only; no desktop-wide capture.
import { _electron as electron } from "@playwright/test";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
const name = process.argv[2] || "motion-check";
if (!/^[a-z0-9-]+$/.test(name))
  throw Error("Use an alphanumeric recording name");
const folder = path.resolve("test-results/recordings");
await fs.mkdir(folder, { recursive: true });
const env = { ...process.env, TOBKIRI_COMPANION_PORT: "47840" };
delete env.ELECTRON_RUN_AS_NODE;
const app = await electron.launch({ args: [".", "--record-test"], env });
let recorder;
try {
  const page = await app.firstWindow();
  await page.waitForSelector("#motion-grid button");
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.stack));
  const title = await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()
      .find((w) => w.isFocusable())
      .getTitle(),
  );
  await page.evaluate(() => {
    window.motionMeasure = { frames: [], costs: [], last: null };
    const original = requestAnimationFrame.bind(window);
    window.requestAnimationFrame = (callback) =>
      original((now) => {
        const m = window.motionMeasure;
        if (m.last !== null && now !== m.last) m.frames.push(now - m.last);
        m.last = now;
        const start = performance.now();
        callback(now);
        m.costs.push(performance.now() - start);
      });
  });
  console.log("Measuring visible app: " + title);
  await page.waitForTimeout(5000);
  const baseline = await page.evaluate(() => {
    const m = window.motionMeasure;
    const data = { frames: m.frames, costs: m.costs };
    m.frames = [];
    m.costs = [];
    m.last = null;
    return data;
  });
  await app.evaluate(async ({ BrowserWindow, desktopCapturer, session }) => {
    const win = BrowserWindow.getAllWindows().find((w) => w.isFocusable());
    const sources = await desktopCapturer.getSources({
      types: ["window"],
      thumbnailSize: { width: 0, height: 0 },
    });
    const source = sources.find((s) => s.id === win.getMediaSourceId());
    if (!source) throw Error("Own window capture source not found");
    session.defaultSession.setDisplayMediaRequestHandler(
      (request, callback) => {
        if (request.frame === win.webContents.mainFrame)
          callback({ video: source });
        else callback({});
      },
      { useSystemPicker: false },
    );
  });
  const capture = await page.evaluate(async () => {
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: 60, width: 1280, height: 900 },
      audio: false,
    });
    const chunks = [],
      recorder = new MediaRecorder(stream, {
        mimeType: "video/webm;codecs=vp9",
        videoBitsPerSecond: 10000000,
      });
    recorder.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    const settings = stream.getVideoTracks()[0].getSettings();
    window.windowRecording = { stream, recorder, chunks };
    recorder.start(1000);
    window.motionMeasure.frames = [];
    window.motionMeasure.costs = [];
    window.motionMeasure.last = null;
    return settings;
  });
  console.log("Window-only recording started: " + JSON.stringify(capture));
  await page.waitForTimeout(30000);
  const recorded = await page.evaluate(() => ({
    frames: motionMeasure.frames,
    costs: motionMeasure.costs,
  }));
  const encoded = await page.evaluate(async () => {
    const { recorder, stream, chunks } = window.windowRecording;
    await new Promise((resolve) => {
      recorder.onstop = resolve;
      recorder.stop();
    });
    stream.getTracks().forEach((t) => t.stop());
    return await new Promise((resolve) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result.split(",")[1]);
      r.readAsDataURL(new Blob(chunks, { type: "video/webm" }));
    });
  });
  const webm = path.join(folder, `${name}.webm`),
    output = path.join(folder, `${name}.mp4`);
  await fs.writeFile(webm, Buffer.from(encoded, "base64"));
  let log = "";
  recorder = spawn(
    "ffmpeg",
    [
      "-hide_banner",
      "-y",
      "-i",
      webm,
      "-c:v",
      "libx264",
      "-preset",
      "fast",
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
  recorder.stderr.on("data", (data) => (log += data));
  await new Promise((resolve, reject) => {
    recorder.on("error", reject);
    recorder.on("exit", (code) =>
      code === 0 ? resolve() : reject(Error(log.slice(-2000))),
    );
  });
  function stats(data) {
    const q = (items, p) =>
      [...items].sort((a, b) => a - b)[
        Math.min(items.length - 1, Math.floor(items.length * p))
      ];
    return {
      frames: data.frames.length,
      averageFPS:
        1000 / (data.frames.reduce((a, b) => a + b, 0) / data.frames.length),
      medianMs: q(data.frames, 0.5),
      p95Ms: q(data.frames, 0.95),
      p99Ms: q(data.frames, 0.99),
      maxMs: Math.max(...data.frames),
      over25ms: data.frames.filter((x) => x > 25).length,
      over50ms: data.frames.filter((x) => x > 50).length,
      drawP95Ms: q(data.costs, 0.95),
      drawMaxMs: Math.max(...data.costs),
    };
  }
  const result = {
    name,
    recording: output,
    title,
    scope:
      "Native Electron window-only desktopCapturer stream, requested 60 fps, VP9 then H.264",
    capture,
    withoutRecorder: stats(baseline),
    withRecorder: stats(recorded),
    errors,
  };
  await fs.writeFile(
    path.join(folder, name + ".json"),
    JSON.stringify({ ...result, raw: { baseline, recorded } }, null, 2),
  );
  await fs.writeFile(path.join(folder, name + ".ffmpeg.log"), log);
  console.log(JSON.stringify(result, null, 2));
} finally {
  if (recorder?.exitCode === null) recorder.kill();
  await app.close();
}
