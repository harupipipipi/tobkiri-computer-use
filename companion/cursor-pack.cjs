const { constants } = require("node:fs");
const fs = require("node:fs/promises");
const path = require("node:path");
const { randomUUID } = require("node:crypto");

const MAX_PACK_BYTES = 8_000_000;

async function readPack(file, validatePack) {
  try {
    const info = await fs.stat(file);
    if (!info.isFile() || info.size > MAX_PACK_BYTES)
      throw Error("Cursor pack must be a file of at most 8 MB.");
    return validatePack(JSON.parse(await fs.readFile(file, "utf8")));
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

async function writePack(file, pack) {
  const data = Buffer.from(JSON.stringify(pack));
  if (data.length > MAX_PACK_BYTES) throw Error("Cursor pack exceeds 8 MB.");
  await fs.mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
  const temporary = `${file}.${randomUUID()}.tmp`;
  try {
    await fs.writeFile(temporary, data, { flag: "wx", mode: 0o600 });
    await fs.rename(temporary, file);
  } catch (error) {
    await fs.rm(temporary, { force: true }).catch(() => {});
    throw error;
  }
}

async function loadStudioPack(
  settingsFile,
  sharedFile,
  defaults,
  validatePack,
) {
  const saved = await readPack(settingsFile, validatePack);
  if (saved) return saved;
  if (!sharedFile) return structuredClone(defaults);

  const existing = await readPack(sharedFile, validatePack);
  // The browser pack supplies artwork. Studio owns its desktop follow mode.
  const pack = existing
    ? { ...existing, mode: defaults.mode }
    : { ...structuredClone(defaults), displayMode: "both" };
  await writePack(settingsFile, pack);
  return pack;
}

async function publishPack(file, pack, { preserveExisting = false } = {}) {
  if (preserveExisting) {
    // The shared destination may have contained an independently edited pack.
    const data = Buffer.from(JSON.stringify(pack));
    try {
      const info = await fs.stat(file);
      if (!info.isFile() || info.size > MAX_PACK_BYTES)
        throw Error("Cursor pack must be a file of at most 8 MB.");
      if (info.size === data.length && (await fs.readFile(file)).equals(data))
        return;
      await fs.copyFile(file, `${file}.before-studio`, constants.COPYFILE_EXCL);
    } catch (error) {
      if (error.code !== "ENOENT" && error.code !== "EEXIST") throw error;
    }
  }
  await writePack(file, pack);
}

module.exports = { loadStudioPack, publishPack, writePack };
