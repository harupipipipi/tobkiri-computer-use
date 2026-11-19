import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { test } from "node:test";
import cursorPack from "../cursor-pack.cjs";
import { defaults, validatePack } from "../src/config.js";

const { loadStudioPack, publishPack, writePack } = cursorPack;
const load = async (file) => JSON.parse(await readFile(file, "utf8"));

async function paths(t) {
  const artifacts = new URL("../test-results/", import.meta.url);
  await mkdir(artifacts, { recursive: true });
  const dir = await mkdtemp(new URL("cursor-pack-", artifacts));
  t.after(() => rm(dir, { recursive: true, force: true }));
  return {
    settings: join(dir, "studio", "character.json"),
    shared: join(dir, ".tobkiri-tabs", "cursor-pack.json"),
  };
}

test("Studio imports a Tabs pack once and publishes subsequent edits", async (t) => {
  const { settings, shared } = await paths(t);
  const previous = {
    version: 1,
    name: "Tabs character",
    color: "#3366aa",
    cursor: "ring",
    displayMode: "pet",
    mode: "pointer",
  };
  await writePack(shared, previous);

  const migrated = await loadStudioPack(
    settings,
    shared,
    defaults,
    validatePack,
  );
  assert.deepEqual(migrated, { ...validatePack(previous), mode: "computer" });
  assert.deepEqual(await load(settings), migrated);
  await publishPack(shared, migrated, { preserveExisting: true });

  const edited = { ...migrated, cursorColor: "#aa3366", displayMode: "both" };
  await writePack(settings, edited);
  await publishPack(shared, edited);
  assert.deepEqual(await load(shared), edited);
  assert.deepEqual(await load(`${shared}.before-studio`), previous);

  await writePack(shared, previous);
  assert.deepEqual(
    await loadStudioPack(settings, shared, defaults, validatePack),
    edited,
  );
});

test("Studio publishes first-run defaults and preserves an independent pack on replacement", async (t) => {
  const { settings, shared } = await paths(t);
  const initial = await loadStudioPack(
    settings,
    shared,
    defaults,
    validatePack,
  );
  assert.equal(initial.displayMode, "both");
  assert.deepEqual(await load(settings), initial);
  await publishPack(shared, initial, { preserveExisting: true });
  await publishPack(shared, initial, { preserveExisting: true });
  await assert.rejects(readFile(`${shared}.before-studio`), { code: "ENOENT" });

  const edited = { ...initial, color: "#112233" };
  await writePack(settings, edited);
  assert.deepEqual(
    await loadStudioPack(settings, shared, defaults, validatePack),
    edited,
  );
  await publishPack(shared, edited, { preserveExisting: true });
  await publishPack(
    shared,
    { ...edited, color: "#223344" },
    { preserveExisting: true },
  );
  assert.deepEqual(await load(`${shared}.before-studio`), initial);
});

test("an invalid legacy pack survives a failed import", async (t) => {
  const { settings, shared } = await paths(t);
  await mkdir(dirname(shared), { recursive: true });
  await writeFile(shared, "{broken");
  await assert.rejects(
    loadStudioPack(settings, shared, defaults, validatePack),
    SyntaxError,
  );
  assert.equal(await readFile(shared, "utf8"), "{broken");
  await assert.rejects(readFile(settings), { code: "ENOENT" });
});
