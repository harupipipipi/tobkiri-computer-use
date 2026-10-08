// Local-only render fixture. Serves only extension/test assets, never configs or user files.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve,extname,sep} from 'node:path';
const root=fileURLToPath(new URL('..',import.meta.url));
const types={'.html':'text/html; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.png':'image/png'};
const server=http.createServer(async(req,res)=>{
  try{
    let path=decodeURIComponent(new URL(req.url,'http://127.0.0.1').pathname);
    if(path==='/')path='/tests/cursor-preview.html';
    if(path==='/popup'){
      const html=await readFile(resolve(root,'extension/popup.html'),'utf8');
      res.setHeader('Content-Type',types['.html']);res.end(html.replace('<head>','<head><base href="/extension/"><script src="/tests/popup-fixture.js"></script>'));return;
    }
    const file=resolve(root,'.'+path),extension=extname(file);
    if(!types[extension]||!['extension','tests'].some(dir=>file.startsWith(resolve(root,dir)+sep)))throw new Error('Not served');
    res.setHeader('Content-Type',types[extension]);res.setHeader('Cache-Control','no-store');res.end(await readFile(file));
  }catch{res.statusCode=404;res.end('Not found');}
});
server.listen(Number(process.env.TOBKIRI_PREVIEW_PORT)||4173,'127.0.0.1',()=>console.log('Render fixture: http://127.0.0.1:'+server.address().port));
