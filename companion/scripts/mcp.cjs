// Codex stdio launcher: one desktop renderer, plus the real Tobkiri MCP server.
// Never write diagnostics to stdout (it belongs to MCP).
const { spawn } = require("node:child_process");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const server = process.argv[2];
if (!server) throw Error("Pass the installed tobkiri-computer-use executable");
const env = { ...process.env, TOBKIRI_COMPANION: "1", PYTHONUTF8: "1" };
delete env.ELECTRON_RUN_AS_NODE;
const renderer = spawn(require("electron"), [root, "--agent-mode"], {
  env,
  detached: true,
  stdio: "ignore",
  windowsHide: true,
});
renderer.on("error", (error) => console.error("Companion: " + error.message));
renderer.unref();
const child = spawn(server, process.argv.slice(3), {
  env,
  stdio: "inherit",
  windowsHide: true,
});
child.on("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => child.kill());
