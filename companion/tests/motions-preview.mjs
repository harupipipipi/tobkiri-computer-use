// Render the real animation engine in a private headless page. No desktop input.
import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
const folder = "test-results/recordings";
await fs.mkdir(folder, { recursive: true });
const server = spawn(process.execPath, ["scripts/preview.mjs"], {
  windowsHide: true,
  stdio: "pipe",
});
await new Promise((resolve, reject) => {
  server.stdout.once("data", resolve);
  server.once("error", reject);
});
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 1080, height: 760 },
  });
  await page.route("**/src/studio.js", (route) =>
    route.fulfill({ body: "", contentType: "text/javascript" }),
  );
  await page.goto("http://127.0.0.1:4173");
  const result = await page.evaluate(async () => {
    const { Character } = await import("/src/engine.js");
    const { defaults, motions } = await import("/src/config.js");
    // Dedicated preview stage; the normal Studio module is not running here.
    document.body.replaceChildren();
    const canvas = document.createElement("canvas");
    canvas.width = 1080;
    canvas.height = 760;
    document.body.append(canvas);
    const ctx = canvas.getContext("2d");
    const chosen = [
      "hip_pop",
      "vault",
      "soft_drop",
      "roll",
      "backflip",
      "handstand",
    ];
    const characters = chosen.map((action) => {
      const c = new Character(
        { ...defaults, size: 112, trail: false, displayMode: "pet" },
        210,
        230,
      );
      c.play(action, 30);
      return c;
    });
    let last = performance.now(),
      running = true;
    const intervals = [];
    function frame(now) {
      const dt = (now - last) / 1000;
      last = now;
      intervals.push(dt * 1000);
      ctx.fillStyle = "#f5f4fa";
      ctx.fillRect(0, 0, 1080, 760);
      ctx.fillStyle = "#302c43";
      ctx.font = "600 26px sans-serif";
      ctx.fillText("Mochi · new moves", 30, 43);
      ctx.fillStyle = "#817896";
      ctx.font = "14px sans-serif";
      ctx.fillText("18 NEW ANIMATIONS  /  PET ONLY", 735, 40);
      characters.forEach((c, i) => {
        ctx.save();
        ctx.translate((i % 3) * 350 + 20, Math.floor(i / 3) * 340 + 70);
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.roundRect(0, 0, 340, 320, 16);
        ctx.fill();
        ctx.strokeStyle = "#eeeaf6";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(32, 292);
        ctx.lineTo(308, 292);
        ctx.stroke();
        c.update(dt);
        c.draw(ctx);
        ctx.fillStyle = "#302c43";
        ctx.font = "600 15px sans-serif";
        ctx.fillText(motions.find((m) => m[0] === chosen[i])[1], 18, 29);
        ctx.fillStyle = "#a299b2";
        ctx.font = "12px sans-serif";
        ctx.fillText(String(i + 1).padStart(2, "0"), 301, 29);
        ctx.restore();
      });
      if (running) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    const stream = canvas.captureStream(60),
      chunks = [];
    const recorder = new MediaRecorder(stream, {
      mimeType: "video/webm;codecs=vp8",
      videoBitsPerSecond: 6000000,
    });
    recorder.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    recorder.start();
    await new Promise((r) => setTimeout(r, 8000));
    await new Promise((r) => {
      recorder.onstop = r;
      recorder.stop();
    });
    running = false;
    stream.getTracks().forEach((t) => t.stop());
    const video = await new Promise((resolve) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result.split(",")[1]);
      r.readAsDataURL(new Blob(chunks, { type: "video/webm" }));
    });
    return {
      video,
      poster: canvas.toDataURL("image/png").split(",")[1],
      intervals,
    };
  });
  await fs.writeFile(
    `${folder}/new-moves.webm`,
    Buffer.from(result.video, "base64"),
  );
  await fs.writeFile(
    `${folder}/new-moves.png`,
    Buffer.from(result.poster, "base64"),
  );
  await fs.writeFile(
    `${folder}/new-moves.json`,
    JSON.stringify({
      scope: "Headless engine preview; no real-app input",
      intervals: result.intervals,
    }),
  );
  const ffmpeg = spawn(
    "ffmpeg",
    [
      "-hide_banner",
      "-loglevel",
      "error",
      "-y",
      "-i",
      `${folder}/new-moves.webm`,
      "-c:v",
      "libx264",
      "-crf",
      "18",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      `${folder}/new-moves.mp4`,
    ],
    { windowsHide: true, stdio: "inherit" },
  );
  await new Promise((resolve, reject) => {
    ffmpeg.once("error", reject);
    ffmpeg.once("exit", (code) =>
      code === 0 ? resolve() : reject(Error(`ffmpeg ${code}`)),
    );
  });
  console.log("Recorded animation preview: " + folder + "/new-moves.mp4");
} finally {
  await browser.close();
  server.kill();
}
