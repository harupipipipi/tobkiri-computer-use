// Fictional, read-only popup status for visual QA. Never loaded by the packaged extension.
globalThis.chrome={runtime:{sendMessage:async({type})=>type==='status'?{result:{
  version:'0.3.0',connected:true,config:{enabled:true,paired:true,protectActive:true,allowCreate:true},
  clients:[{id:'fixture',name:'描画確認用クライアント'}],
  workspaces:[{id:'fixture',name:'カーソル描画の確認',color:'cyan',paused:false}],
  tabs:[{workspaceId:'fixture',title:'Tobkiri Tabs · Cursor validation',active:false}],audit:[],
}}:{error:'これは表示確認用のプレビューです。接続・許可は変更されません。'}}};
