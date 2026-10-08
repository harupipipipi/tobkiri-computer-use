const {
  app,
  BrowserWindow,
  ipcMain,
  screen,
  globalShortcut,
  Menu,
  Tray,
  nativeImage,
} = require("electron");
const path = require("node:path");
const fs = require("node:fs/promises");
const dgram = require("node:dgram");
const { parseEvent } = require("./protocol.cjs");
let studio,
  config,
  validatePack,
  socket,
  status = "starting",
  enabled = false,
  quitting = false;
let tray;
let sharedPackFile = process.env.TOBKIRI_CURSOR_PACK;
async function publishPack() {
  if (!sharedPackFile || !config) return;
  // Presentation only. Publishing failures never grant permission or send input.
  try {
    await fs.mkdir(path.dirname(sharedPackFile), { recursive: true });
    const temp = sharedPackFile + '.tmp';
    await fs.writeFile(temp, JSON.stringify(config), { mode: 0o600 });
    await fs.rename(temp, sharedPackFile);
  } catch (error) {
    console.error('Shared cursor pack: ' + error.code);
  }
}
const overlays = new Map(),
  sessions = new Map();
const arrivals = new Map();
const port = Number(process.env.TOBKIRI_COMPANION_PORT || 47831);
// Render-only acceptance uses isolated settings and never presents a native window.
const smokeTest = process.argv.includes("--smoke-test");
const recordTest = process.argv.includes("--record-test");
let agentMode = process.argv.includes("--agent-mode");
// Opt-in for the user's live recording. Normally overlays stay out of captures.
const recordable = process.argv.includes("--recordable");
if (smokeTest)
  app.setPath("userData", process.env.TOBKIRI_SMOKE_USER_DATA || path.join(__dirname, "test-results", "runtime"));
if (recordTest)
  app.setPath(
    "userData",
    path.join(__dirname, "test-results", "recording-runtime"),
  );
const webPreferences = {
  preload: path.join(__dirname, "preload.cjs"),
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
  backgroundThrottling: false,
  offscreen: smokeTest,
};
const send = (win, channel, data) => {
  if (win && !win.isDestroyed() && !win.webContents.isLoading())
    win.webContents.send(channel, data);
};
function lock(win) {
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (e) => e.preventDefault());
}
function fanout(channel, event) {
  send(studio, channel, event);
  for (const win of overlays.values()) send(win, channel, event);
}
function state() {
  return { config, enabled, status, port, desktop: true };
}
function overlayWindows() {
  for (const win of overlays.values()) win.close();
  overlays.clear();
  for (const display of screen.getAllDisplays()) {
    const win = new BrowserWindow({
      ...display.bounds,
      show: false,
      transparent: true,
      frame: false,
      hasShadow: false,
      resizable: false,
      movable: false,
      focusable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      webPreferences,
    });
    lock(win);
    win.setIgnoreMouseEvents(true);
    win.setAlwaysOnTop(true, "screen-saver");
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    win.setContentProtection(!recordable);
    win.loadFile(path.join(__dirname, "overlay.html"), {
      query: { x: String(display.bounds.x), y: String(display.bounds.y) },
    });
    win.once("ready-to-show", () => {
      if (enabled && !smokeTest && !win.isDestroyed()) win.showInactive();
    });
    overlays.set(display.id, win);
  }
}
function setEnabled(value) {
  enabled = value === true;
  for (const win of overlays.values())
    enabled && !smokeTest ? win.showInactive() : win.hide();
  fanout("config", state());
  return state();
}
function receive(buffer, remote) {
  const event = parseEvent(buffer);
  if (!event) return;
  const key = event.source + ":" + event.session,
    previous = sessions.get(key);
  if (previous && previous.seq >= event.seq) return;
  if (!previous && sessions.size >= 64) return;
  const point = {
    x: Math.round(event.point[0]),
    y: Math.round(event.point[1]),
  };
  const dip =
    process.platform === "win32" && event.space === "physical"
      ? screen.screenToDipPoint(point)
      : point;
  event.point = [dip.x, dip.y];
  event.space = "dip";
  if (event.phase === "prepare" && enabled && remote?.address === "127.0.0.1") {
    const id = `${key}:${event.seq}`;
    arrivals.set(id, {
      remote,
      source: event.source,
      seq: event.seq,
      time: Date.now(),
    });
    socket.send(
      Buffer.from(
        JSON.stringify({
          source: event.source,
          seq: event.seq,
          phase: "accepted",
        }),
      ),
      remote.port,
      remote.address,
    );
  }
  sessions.set(key, { seq: event.seq, time: Date.now() });
  fanout("event", event);
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", (_event, argv) => {
    if (argv.includes("--agent-mode")) {
      agentMode = true;
      const packIndex = argv.indexOf('--cursor-pack');
      if (packIndex >= 0 && argv[packIndex + 1]) sharedPackFile = argv[packIndex + 1];
      if (config) config.mode = "computer";
      void publishPack();
      setEnabled(true);
    } else studio?.show();
  });
  app
    .whenReady()
    .then(async () => {
      ({ validatePack } = await import("./src/config.js"));
      const { defaults } = await import("./src/config.js");
      config = structuredClone(defaults);
      const configFile = path.join(app.getPath("userData"), "character.json");
      try {
        config = validatePack(
          JSON.parse(await fs.readFile(configFile, "utf8")),
        );
      } catch (error) {
        if (error.code === "ENOENT" && sharedPackFile) config.displayMode = "both";
        if (error.code !== "ENOENT")
          status =
            "保存した設定を読み込めませんでした。標準設定で起動しました。";
      }
      if (agentMode) config.mode = "computer";
      await publishPack();
      Menu.setApplicationMenu(null);
      const area = screen.getPrimaryDisplay().workAreaSize;
      studio = new BrowserWindow({
        width: Math.min(1400, area.width),
        height: Math.min(940, area.height),
        minWidth: Math.min(960, area.width),
        minHeight: Math.min(720, area.height),
        backgroundColor: "#f7f8fa",
        title: "Tobkiri — Cursor Studio",
        show: false,
        alwaysOnTop: recordTest,
        webPreferences,
      });
      lock(studio);
      if (recordTest) {
        studio.on("page-title-updated", (event) => event.preventDefault());
        studio.setTitle("Tobkiri Motion Check");
      }
      studio.loadFile(path.join(__dirname, "index.html"));
      studio.once("ready-to-show", () => {
        if (!smokeTest && !agentMode) studio.show();
      });
      studio.on("close", (event) => {
        if (agentMode && !quitting) {
          event.preventDefault();
          studio.hide();
        }
      });
      studio.on("closed", () => {
        studio = null;
        if (!quitting) app.quit();
      });
      ipcMain.handle("state", () => state());
      ipcMain.on("character-ready", (ipc, event) => {
        if (![...overlays.values()].some((w) => w.webContents === ipc.sender))
          return;
        if (
          !event ||
          typeof event.source !== "string" ||
          typeof event.session !== "string"
        )
          return;
        const id = `${event.source}:${event.session}:${event.seq}`,
          pending = arrivals.get(id);
        if (!pending) return;
        arrivals.delete(id);
        const { remote, source, seq } = pending;
        socket.send(
          Buffer.from(JSON.stringify({ source, seq, phase: "ready" })),
          remote.port,
          remote.address,
        );
      });
      ipcMain.handle("save", async (event, pack) => {
        if (event.sender !== studio?.webContents) throw Error("Studio only");
        const next = validatePack(pack);
        const temp = configFile + ".tmp";
        await fs.writeFile(temp, JSON.stringify(next));
        await fs.rename(temp, configFile);
        config = next;
        await publishPack();
        fanout("config", state());
        return state();
      });
      ipcMain.handle("overlay", (event, value) => {
        if (event.sender !== studio?.webContents) throw Error("Studio only");
        return setEnabled(value);
      });
      overlayWindows();
      if (!smokeTest && !recordTest) {
        const pixels = Buffer.alloc(32 * 32 * 4);
        for (let y = 0; y < 32; y++)
          for (let x = 0; x < 32; x++) {
            const i = (y * 32 + x) * 4;
            const inside = (x - 16) ** 2 + (y - 16) ** 2 < 230;
            pixels.set([232, 100, 119, inside ? 255 : 0], i);
            if (
              inside &&
              ((x >= 10 && x <= 13 && y >= 7 && y <= 24) ||
                (y >= 11 && y <= 14 && x >= 8 && x <= 23))
            )
              pixels.set([255, 255, 255, 255], i);
          }
        tray = new Tray(
          nativeImage.createFromBitmap(pixels, { width: 32, height: 32 }),
        );
        tray.setToolTip("Tobkiri — 操作するキャラクター");
        tray.setContextMenu(
          Menu.buildFromTemplate([
            { label: "キャラクターを編集", click: () => studio.show() },
            { label: "表示を切り替え", click: () => setEnabled(!enabled) },
            { type: "separator" },
            { label: "終了", click: () => app.quit() },
          ]),
        );
        tray.on("double-click", () => studio.show());
      }
      if (agentMode) setEnabled(true);
      for (const name of [
        "display-added",
        "display-removed",
        "display-metrics-changed",
      ])
        screen.on(name, overlayWindows);
      socket = dgram.createSocket("udp4");
      socket.on("message", receive);
      socket.on("error", (error) => {
        status = `接続エラー: ${error.code}`;
        fanout("config", state());
      });
      if (Number.isInteger(port) && port > 1024 && port < 65536)
        socket.bind(port, "127.0.0.1", () => {
          status = "listening";
          fanout("config", state());
        });
      else status = "ポートは1025〜65535で指定してください。";
      if (!smokeTest)
        globalShortcut.register("CommandOrControl+Shift+F8", () =>
          setEnabled(!enabled),
        );
      setInterval(() => {
        for (const [key, value] of arrivals)
          if (Date.now() - value.time > 1500) arrivals.delete(key);
        for (const [key, value] of sessions)
          if (Date.now() - value.time > 5000) sessions.delete(key);
        if (enabled && config.mode === "pointer") {
          const p = screen.getCursorScreenPoint();
          fanout("event", {
            version: 1,
            source: "pointer",
            session: "human",
            seq: Date.now(),
            action: "move",
            phase: "anchor",
            point: [p.x, p.y],
            space: "dip",
          });
        }
      }, 1000 / 60).unref();
    })
    .catch((error) => {
      console.error(error);
      app.quit();
    });
}
app.on("before-quit", () => {
  quitting = true;
  globalShortcut.unregisterAll();
  tray?.destroy();
  try {
    socket?.close();
  } catch {}
});
app.on("window-all-closed", () => app.quit());
