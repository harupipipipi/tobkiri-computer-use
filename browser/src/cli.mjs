#!/usr/bin/env node
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {dirname,resolve} from 'node:path';
import {openSync,closeSync} from 'node:fs';
import {configPath,initConfig,readConfig,pairingCode,request} from './config.mjs';
import {startBridge} from './bridge.mjs';
import {runMcp} from './mcp.mjs';
import {cursorPackPath} from './cursor-pack.mjs';
import {VERSION} from '../extension/shared.mjs';
const file=fileURLToPath(import.meta.url), root=resolve(dirname(file),'..');
const [command='help',...args]=process.argv.slice(2);
function option(name,fallback) {const i=args.indexOf(name);if(i<0)return fallback;if(!args[i+1] || args[i+1].startsWith('--'))throw new Error(`Missing value for ${name}`);return args[i+1];}
const path=configPath(option('--config'));
async function ensureBridge(c) {
  try{const s=await request(c,'/status',undefined,undefined,700);if(s.product==='tobkiri-tabs')return;}catch{}
  const log=openSync(resolve(dirname(path),'bridge.log'),'a',0o600);
  const child=spawn(process.execPath,[file,'bridge','--config',path],{detached:true,stdio:['ignore',log,log],windowsHide:true});closeSync(log);child.unref();
  let spawnError;child.once('error',e=>{spawnError=e;});
  for(let i=0;i<30;i++){await new Promise(r=>setTimeout(r,150));if(spawnError)throw spawnError;try{const s=await request(c,'/status',undefined,undefined,500);if(s.product==='tobkiri-tabs')return;}catch{}}
  throw new Error(`Bridge did not start. Check ${dirname(path)}/bridge.log; port ${c.port} may already be in use.`);
}
try {
  if(command==='setup') {
    const c=await initConfig(path,Number(option('--port',17653)));await ensureBridge(c);
    console.log(`\nTobkiri Tabs ${VERSION}\n\n1. Load this unpacked extension:\n   ${root}/extension\n\n2. Paste this PRIVATE pairing code into the extension:\n\n${pairingCode(c)}\n\nDo not put the pairing code in an AI chat, repository, or screenshot.\n\n3. Add this stdio MCP configuration to your host:\n`);
    console.log(JSON.stringify({mcpServers:{'tobkiri-tabs':{command:process.execPath,args:[file,'mcp','--config',path]}}},null,2));
    console.log(`\nConfig: ${path}\nLocal bridge: 127.0.0.1:${c.port}\nStop: node "${file}" stop --config "${path}"\nNo npm install, build, native host registration, or remote-debugging port is needed.`);
  } else if(command==='bridge') {
    const c=await readConfig(path);const b=await startBridge(c);
    console.error(`Tobkiri Tabs bridge listening on 127.0.0.1:${c.port}`);
    process.once('SIGINT',()=>void b.stop());process.once('SIGTERM',()=>void b.stop());
  } else if(command==='mcp') {
    const c=await readConfig(path);await ensureBridge(c);
    await request(c,'/cursor/configure',{path:cursorPackPath(c)},undefined,3000);
    await runMcp(c,{name:option('--name','Tobkiri Tabs')});
  } else if(command==='doctor') {
    const c=await readConfig(path);console.log(JSON.stringify({node:process.version,config:path,...await request(c,'/status',undefined,undefined,2000)},null,2));
  } else if(command==='stop') {
    const c=await readConfig(path);await request(c,'/shutdown',{},undefined,2000);console.log('Bridge stopped. Browser tabs were NOT closed.');
  } else if(command==='config') {
    await readConfig(path);console.log(JSON.stringify({mcpServers:{'tobkiri-tabs':{command:process.execPath,args:[file,'mcp','--config',path]}}},null,2));
  } else {console.log('Tobkiri Tabs\n  setup [--port 17653] [--config PATH]\n  mcp [--name NAME] [--config PATH]\n  bridge | doctor | stop | config [--config PATH]\nNode 22+. No npm dependencies.');}
} catch(e){console.error(e.message);process.exitCode=1;}
