const { app, BrowserWindow } = require("electron");
const profile = process.argv[2];
if (!profile) throw Error("The fixture requires a disposable profile directory");
app.setPath("userData", profile);
app.setName("TobkiriFixture");
app.commandLine.appendSwitch("force-renderer-accessibility");
const windows = [];

app.whenReady().then(async () => {
  app.dock?.hide();
  for (const label of ["A", "B"]) {
    const title = `Tobkiri Overlap ${label}`;
    const window = new BrowserWindow({
      x: 80, y: 220, width: 480, height: 380, title, show: false,
      webPreferences: { sandbox: true, contextIsolation: true },
    });
    windows.push(window);
    const html = `<!doctype html><meta charset="utf-8"><title>${title}</title>
      <style>body { margin: 32px; font: 18px sans-serif }
      button,input { display:block; margin: 14px 0; padding: 8px }
      canvas { position:absolute; right:32px; top:128px }</style>
      <h1>${title}</h1><label>Name <input type="text" aria-label="Name" autofocus></label>
      <button id="increase">Increment</button><p id="count">Count: 0</p>
      <canvas width="80" height="48" aria-hidden="true"></canvas>
      <p id="canvas-count">Canvas hits: 0</p>
      <script>
        let count = 0, canvasHits = 0;
        document.querySelector('#increase').onclick = () =>
          document.querySelector('#count').textContent = 'Count: ' + ++count;
        const canvas = document.querySelector('canvas');
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#e22c83';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        canvas.onclick = () =>
          document.querySelector('#canvas-count').textContent = 'Canvas hits: ' + ++canvasHits;
      </script>`;
    await window.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(html));
    window.showInactive();
  }
}).catch(error => { console.error(error.message); app.exit(1); });
