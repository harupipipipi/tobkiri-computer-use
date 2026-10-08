import {readFile,mkdir,writeFile,chmod} from 'node:fs/promises';
import {homedir} from 'node:os';
import {resolve,dirname} from 'node:path';
import {randomBytes,timingSafeEqual} from 'node:crypto';
export const configPath = explicit => resolve(explicit || process.env.TOBKIRI_TABS_CONFIG || `${homedir()}/.tobkiri-tabs/config.json`);
export async function readConfig(path) {
  let c; try { c=JSON.parse(await readFile(path,'utf8')); } catch { throw new Error(`Config unavailable. Run: node src/cli.mjs setup --config "${path}"`); }
  if (!Number.isInteger(c.port) || c.port<1024 || c.port>65535 || !/^[a-f0-9]{64}$/.test(c.token)) throw new Error('Invalid configuration.');
  c.configDir=dirname(path);
  return c;
}
export async function initConfig(path,port=17653) {
  try { return await readConfig(path); } catch {}
  if (!Number.isInteger(port) || port<1024 || port>65535) throw new Error('Port must be 1024–65535.');
  await mkdir(dirname(path),{recursive:true,mode:0o700});
  const c={version:1,port,token:randomBytes(32).toString('hex')};
  // Refuse to overwrite an existing malformed file or race another setup.
  await writeFile(path,JSON.stringify(c,null,2)+'\n',{flag:'wx',mode:0o600});
  if(process.platform!=='win32') await chmod(path,0o600);
  return c;
}
export const pairingCode = c => `tbt1.${c.port}.${c.token}`;
export function secureEqual(a,b) { const x=Buffer.from(String(a)),y=Buffer.from(String(b)); return x.length===y.length && timingSafeEqual(x,y); }
export async function request(c,path,body,signal,timeoutMs=35000) {
  const r=await fetch(`http://127.0.0.1:${c.port}${path}`,{method:body===undefined?'GET':'POST',headers:{Authorization:`Bearer ${c.token}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:signal ? AbortSignal.any([signal,AbortSignal.timeout(timeoutMs)]) : AbortSignal.timeout(timeoutMs)});
  const data=await r.json(); if(!r.ok || data.error) throw new Error(data.error || `HTTP ${r.status}`); return data;
}
