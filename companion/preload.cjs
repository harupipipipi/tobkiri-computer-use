const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("companion", {
  getState: () => ipcRenderer.invoke("state"),
  save: (pack) => ipcRenderer.invoke("save", pack),
  show: (enabled) => ipcRenderer.invoke("overlay", enabled),
  ready: (event) => ipcRenderer.send("character-ready", event),
  onEvent: (fn) => {
    const cb = (_, e) => fn(e);
    ipcRenderer.on("event", cb);
    return () => ipcRenderer.removeListener("event", cb);
  },
  onConfig: (fn) => {
    const cb = (_, e) => fn(e);
    ipcRenderer.on("config", cb);
    return () => ipcRenderer.removeListener("config", cb);
  },
});
