# 対象タブのDOM・通信操作

統合MCPでは下記の `browser_` が `tobkiri_tabs_` になります。
WindowsのChrome / Edgeでも同じ拡張とCDPを使用します。
「背景タブ」はブラウザ内の `active:false` の別ページです。背面のWindowsアプリや
別のWindows仮想デスクトップとは異なります。OSのマウス・キーボードを使わず、
許可された整数 `tabId` のDOM、ページJS、通信を対象にします。

## DOMとコンソール相当の実行

```js
browser_eval({tabId, expression: "document.querySelector('h1').textContent='表示を変更しました'"})
```

MAIN worldでページの変数・関数も使用できます。返り値とページ出力は非信頼データです。
画面の変更はサーバーのデータ変更を意味せず、再描画や再読み込みで消える場合があります。
Codex内ブラウザの読み取り専用評価とは別の経路です。

## 通信を読む

1. `browser_network_start({tabId, maxEntries:200})` で記録を開始。
2. ページを操作して通信を発生させる。
3. `browser_network_read({tabId, afterSeq:0, limit:100})` で読む。
4. `nextSeq` を次の `afterSeq` に渡す。`hasMore`、`oldestSeq`、`dropped` で残りと取りこぼしを判断。
5. 成功した `finished` の `requestId` を `browser_network_body({tabId, requestId})` に渡す。
6. 終了時は `browser_network_stop({tabId})`。

ログはメモリだけに保存し、最大500項目・2MBです。1回の読み取りは500KB以内です。
URLとヘッダーなど各項目も制限します。Authorization / Cookie / Set-Cookieは伏せます。
リクエスト本文は `includePostData:true` のときだけ最大4096文字を返します。
レスポンス本文は明示的な取得で返し、既定64KB、最大1MBです。本文には個人情報が
含まれ得ます。ブラウザが本文を破棄した場合は取得エラーを返し、通信を再送しません。
記録開始前の通信は復元しません。

対象はルートタブのdebuggerセッションが通知する通信です。
子worker / 別プロセスiframeセッションへの自動接続や、PC全体のパケット収集は実装していません。

## 通信を変更する

```js
browser_network_routes({tabId, leaseMs:30000, rules:[
  {urlPattern:'https://your-fixture.example/api/mock*', action:'fulfill', status:200,
   headers:[{name:'Content-Type',value:'application/json; charset=utf-8'}], body:'{"demo":"緑"}'},
  {urlPattern:'https://your-fixture.example/api/blocked*', action:'block'},
  {urlPattern:'https://your-fixture.example/api/old*', action:'modify',
   url:'https://your-fixture.example/api/new', headers:[{name:'X-Demo',value:'changed'}]}
]})
```

先に記録を開始します。最初にURL（`*` のglob）と任意のHTTP `method` が一致した
ルールを適用します。`block` は `BlockedByClient`、`fulfill` はUTF-8の模擬応答、
`modify` は `url` / `requestMethod` / `headers` / `postData` を変更します。
`headers` は既存ヘッダーリスト全体を置換します。
request段階だけを対象とし、模擬応答の場合はサーバーへ送信しません。
実サーバーからのresponse段階を書き換える機能や、認証チャレンジ処理は公開していません。

期限は既定30秒、最大5分。`rules:[]` で解除できます。pause、タブ解放、セッション終了、
debugger切断、保護対象のタブをユーザーが開いた場合も解除します。
worker再起動ではルールを復元せず、残ったFetch/Network設定を解除します。
Fetchで止まった通信はworkerが自動で処理し、次のMCP呼び出しを待ちません。
ガード拒否時は通常通信へ戻し、効果が不明なCDPエラーでは切断して再送を避けます。
owner、grant、pause、deadline、前面タブ保護は既存の契約に従います。
送信先・本文などの結果を伴う変更には、現在のユーザー指示とホストの承認ルールを適用します。

生の `browser_cdp` は引き続き使用できますが、構造化通信ツールと同じNetwork/Fetch設定を
同時に変更しないでください。生CDPでルール外のFetch pauseが届いた場合はそのまま継続します。

## 検証

ルートの `npm run test:network` は、使い捨てのヘッドレスChrome / Edgeと架空SNSだけを使い、
production MCP・実MV3拡張を通してDOM変更、ログと本文、block、fulfill、URL/ヘッダーmodify、
同時通信、期限切れ、停止、サーバー受領記録、タブ前面化0件を検証します。
生成物は `integration/artifacts/network-demo/` に保存し、Gitには含めません。
