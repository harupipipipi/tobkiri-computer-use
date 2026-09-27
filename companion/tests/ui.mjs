import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import assert from "node:assert/strict";
const server = spawn(process.execPath, ["scripts/preview.mjs"], {
  stdio: "pipe",
});
await new Promise((resolve, reject) => {
  server.stdout.once("data", resolve);
  server.once("error", reject);
  server.once("exit", (code) => reject(Error(`Server exited: ${code}`)));
});
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
      viewport: { width: 1440, height: 1080 },
    }),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.stack));
  await page.goto("http://127.0.0.1:4173");
  await page.waitForFunction(() =>
    document.querySelector("#fps").textContent.includes("FPS"),
  );
  assert.equal(await page.locator(".motion-card").count(), 48);
  assert.equal(await page.locator("#displayMode").inputValue(), "pet");
  await page.locator("#displayMode").selectOption("both");
  await page.waitForTimeout(600);
  await fs.mkdir("test-results", { recursive: true });
  await page.screenshot({ path: "test-results/studio.png", fullPage: true });
  await page.getByRole("button", { name: "タイピング", exact: true }).click();
  assert.equal(await page.locator("#action-label").textContent(), "タイピング");
  await page.locator("#name").fill("Test buddy");
  await page.locator("#size").fill("135");
  await page.waitForTimeout(400);
  await page.reload();
  await page.waitForTimeout(300);
  assert.equal(await page.locator("#name").inputValue(), "Test buddy");
  assert.equal(await page.locator("#size").inputValue(), "135");
  assert.equal(await page.locator("#displayMode").inputValue(), "both");
  await page.locator("#displayMode").selectOption("pet");
  await page
    .getByRole("button", { name: "ひゅっ、と降りる", exact: true })
    .click();
  assert.equal(
    await page.locator("#action-label").textContent(),
    "ひゅっ、と降りる",
  );
  await page.locator('[data-tab="cursor"]').click();
  const box = await page.locator("#cursor-drawing").boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.7, {
    steps: 8,
  });
  await page.mouse.up();
  assert.equal(await page.locator("#cursor").inputValue(), "custom");
  await page.locator("#hotspot-x").fill("12");
  await page.locator("#hotspot-x").press("Tab");
  const download = page.waitForEvent("download");
  await page.locator("#export").click();
  const file = await download;
  const exported = JSON.parse(await fs.readFile(await file.path(), "utf8"));
  assert.ok(exported.cursorImage.startsWith("data:image/png"));
  assert.equal(exported.hotspot[0], 12);
  assert.equal(exported.displayMode, "pet");
  await page.locator("#pack-file").setInputFiles({
    name: "broken.json",
    mimeType: "application/json",
    buffer: Buffer.from('{"version":999}'),
  });
  await page.waitForTimeout(100);
  assert.ok((await page.locator("#toast").textContent()).includes("version"));
  await page.locator('[data-tab="motion"]').click();
  await page.locator("#sprite-frames").fill("1");
  await page.locator("#sprite-file").setInputFiles({
    name: "sprite.png",
    mimeType: "image/png",
    buffer: Buffer.from(exported.cursorImage.split(",")[1], "base64"),
  });
  await page.waitForTimeout(200);
  assert.ok(
    (await page.locator("#sprite-state").textContent()).includes("カスタムPNG"),
  );
  await page.locator("#sprite-reset").click();
  assert.ok(
    (await page.locator("#sprite-state").textContent()).includes("標準"),
  );
  await page.locator("#reset").click();
  await page.setViewportSize({ width: 1000, height: 800 });
  await page.screenshot({
    path: "test-results/studio-compact.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  await page.screenshot({
    path: "test-results/studio-mobile.png",
    fullPage: true,
  });
  assert.deepEqual(errors, []);
  console.log(
    "UI passed: 48 motions, pet-only / cursor+pet modes, editing, persistence, cursor drawing, export, import, responsive layout, no page errors.",
  );
} finally {
  await browser.close();
  server.kill();
}
