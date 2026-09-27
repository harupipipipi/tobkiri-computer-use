import { _electron as electron } from "@playwright/test";
import dgram from "node:dgram";
import fs from "node:fs/promises";
import assert from "node:assert/strict";
await fs.mkdir("test-results", { recursive: true });
const env = { ...process.env, TOBKIRI_COMPANION_PORT: "47839" };
delete env.ELECTRON_RUN_AS_NODE;
const app = await electron.launch({ args: [".", "--smoke-test"], env }),
  sender = dgram.createSocket("udp4");
try {
  await app.firstWindow();
  let studio;
  for (let i = 0; i < 100; i++) {
    studio = app.windows().find((page) => page.url().includes("index.html"));
    if (studio) break;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  assert.ok(studio, "Studio window must load");
  await studio.waitForSelector("#motion-grid button", { state: "attached" });
  const errors = [];
  studio.on("pageerror", (error) => errors.push(error.message));
  assert.equal(
    await studio.evaluate(async () => {
      const { config } = await window.companion.getState();
      config.displayMode = "both";
      const result = await window.companion.save({
        ...config,
        name: "Save fixture",
      });
      await window.companion.save(config);
      return result.config.name;
    }),
    "Save fixture",
  );
  const windows = await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows().map((w) => ({
      bounds: w.getBounds(),
      focusable: w.isFocusable(),
      visible: w.isVisible(),
      top: w.isAlwaysOnTop(),
    })),
  );
  assert.ok(windows.length >= 2);
  assert.ok(windows.every((w) => !w.visible));
  assert.ok(windows.filter((w) => !w.focusable).every((w) => w.top));
  await studio.locator("#desktop-toggle").click();
  const overlay = app.windows().find((w) => w.url().includes("overlay.html"));
  assert.ok(overlay);
  await overlay.waitForLoadState("load");
  const query = new URL(overlay.url()).searchParams;
  const point = [Number(query.get("x")) + 350, Number(query.get("y")) + 300];
  const physical =
    process.platform === "win32"
      ? await app.evaluate(
          ({ screen }, point) =>
            screen.dipToScreenPoint({ x: point[0], y: point[1] }),
          point,
        )
      : null;
  const event = {
    version: 1,
    source: "test",
    session: "test-fixture",
    seq: 1,
    action: "type",
    phase: "start",
    space: physical ? "physical" : "dip",
    point: physical ? [physical.x, physical.y] : point,
  };
  const send = async (value) =>
    new Promise((resolve, reject) =>
      sender.send(
        Buffer.from(JSON.stringify(value)),
        47839,
        "127.0.0.1",
        (err) => (err ? reject(err) : resolve()),
      ),
    );
  const opaquePixels = () =>
    overlay.evaluate(() => {
      const c = document.querySelector("canvas");
      return c
        .getContext("2d")
        .getImageData(0, 0, c.width, c.height)
        .data.some((v, i) => i % 4 === 3 && v > 0);
    });
  await send(event);
  await overlay.waitForFunction(() => {
    const c = document.querySelector("canvas");
    return (
      c.width > 0 &&
      c
        .getContext("2d")
        .getImageData(0, 0, c.width, c.height)
        .data.some((v, i) => i % 4 === 3 && v > 0)
    );
  });
  await overlay.screenshot({
    path: "test-results/desktop-overlay.png",
    omitBackground: true,
  });
  assert.ok(await opaquePixels());
  assert.ok(
    await overlay.evaluate(() => {
      const c = document.querySelector("canvas"),
        dpr = Math.min(devicePixelRatio, 2);
      return c
        .getContext("2d")
        .getImageData(
          Math.round(350 * dpr),
          Math.round(300 * dpr),
          Math.round(8 * dpr),
          Math.round(8 * dpr),
        )
        .data.some((v, i) => i % 4 === 3 && v > 0);
    }),
    "Physical coordinates must land on the exact DIP hotspot",
  );
  await studio.locator("#displayMode").selectOption("pet");
  await overlay.waitForTimeout(400);
  assert.ok(
    await opaquePixels(),
    "The pet remains visible when its arrow is hidden",
  );
  assert.equal(
    await overlay.evaluate(() => {
      const c = document.querySelector("canvas"),
        dpr = Math.min(devicePixelRatio, 2);
      const data = c
        .getContext("2d")
        .getImageData(
          Math.round(350 * dpr),
          Math.round(300 * dpr),
          Math.round(22 * dpr),
          Math.round(28 * dpr),
        ).data;
      for (let i = 0; i < data.length; i += 4)
        if (
          data[i] === 48 &&
          data[i + 1] === 44 &&
          data[i + 2] === 67 &&
          data[i + 3] > 0
        )
          return true;
      return false;
    }),
    false,
    "No dark cursor pixels in pet-only mode",
  );
  await send({ ...event, seq: 2, phase: "hide", action: "hide" });
  await overlay.waitForTimeout(150);
  assert.equal(await opaquePixels(), false);
  await send(event);
  await overlay.waitForTimeout(100);
  assert.equal(
    await opaquePixels(),
    false,
    "Out-of-order UDP must not revive a hidden cursor",
  );
  await send({ ...event, seq: 3 });
  await overlay.waitForTimeout(100);
  assert.ok(await opaquePixels());
  await send({ ...event, seq: 4, phase: "end", outcome: "attempted" });
  const replies = [];
  const arrived = new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(Error("Renderer arrival timed out")),
      1500,
    );
    sender.on("message", (message) => {
      const reply = JSON.parse(message);
      replies.push(reply);
      if (reply.phase === "ready") {
        clearTimeout(timer);
        resolve(reply);
      }
    });
  });
  await send({ ...event, seq: 5, phase: "prepare" });
  assert.deepEqual(await arrived, { source: "test", seq: 5, phase: "ready" });
  assert.equal(replies[0].phase, "accepted");
  await send({ ...event, seq: 6, phase: "end", outcome: "attempted" });
  await overlay.waitForTimeout(3600);
  assert.equal(await opaquePixels(), false, "Crashed publisher must expire");
  assert.deepEqual(errors, []);
  console.log(
    "Desktop render passed: hidden isolated windows, nonfocusable overlay, UDP events, transparent rendering, hide, ordering and publisher expiry.",
  );
} finally {
  sender.close();
  await app.close();
}
