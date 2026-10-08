# Computer Use と Browser Use を一緒に使う

Browser Use [PR #1](https://github.com/harupipipipi/tobkiri-browser-use/pull/1)
を基に、ネイティブアプリ・背景タブ・Cursor Studioを一つのstdio MCPにまとめています。

## セットアップ

1. [Windows](../windows/README.md) または [macOS](../mac/README.md) のPythonパッケージとCua Driverをセットアップします。
2. Node.js 22.12以上で、ルートから `npm ci --prefix companion` を実行します。
3. ルートで `npm run setup` を実行し、表示されたMCP設定をホストに登録します。
4. Chromeの `chrome://extensions` でデベロッパーモードを有効にし、表示された `browser/extension` フォルダを読み込みます。
5. MCPを起動して、拡張のポップアップに秘密のペアリングコードを貼り付けます。新しいAIタブを使う場合は、その作成を人間が許可します。

セットアップはコードを端末に表示します。チャットやGitには貼らないでください。
既存のユーザープロファイル、拡張の許可、ネイティブ入力の承認はそれぞれ元の仕組みを使います。
Chromeの通常タブへ自動で拡張を導入したり、許可を変更したりする機能はありません。

Windowsの直接起動例（ルートから）：

```powershell
node integration/cli.mjs --computer "$PWD\windows\.venv\Scripts\tobkiri-computer-use.exe"
```

`--browser-config PATH` は既存のBrowser Use設定を指定します。`--cursor-pack PATH`
は共有表示設定の保存先を変更します。`--no-companion` はElectronの自動起動を省きます。
`--` 以降の引数はネイティブMCPへそのまま渡します。
通常起動は `--surface all` とOSの一操作承認ダイアログを使用します。

## 操作とカーソル

| 対象 | ツール | 座標と表示 |
| --- | --- | --- |
| Windows/macOSアプリ | 元のCuaツール、`tobkiri_observe` / `tobkiri_act` | 観測に結びついた画像ピクセル。デスクトップのStudio表示 |
| Cuaのブラウザ経路 | 既存の `tobkiri_browser` | Cuaのtarget/tab/session ID。従来の契約を維持 |
| 拡張が許可された背景タブ | `tobkiri_tabs_*` | CSS viewportピクセル。ページ内のStudio表示 |

最初に `tobkiri_tabs_status`、続いて `tobkiri_tabs_workspace_create` でAIタブを作り、
返された `tabId` / `workspaceId` を使います。既存タブは拡張のポップアップで人間が渡します。
`tobkiri_tabs_eval` で許可されたタブのDOMを操作できます。
Cuaの `target_id` / `tab_id` と拡張の整数 `tabId` は交換できません。

Studioのキャラクター・色・手描きPNG・しぐさ・petだけ/カーソル＋petの設定は両方に適用されます。
統合起動の新規設定は「カーソル＋pet」で開始します。コード更新後はStudioを再起動してください。
変更はブラウザの次の操作で反映します。共有ファイルは既定でBrowser設定の隣の
`cursor-pack.json`。新しいStudioが既に起動中のStudioに接続した場合もこのファイルを更新します。
拡張内の描画コードは `companion/src` から生成し、`npm run check:cursor` で一致を確認します。
生成物はGitに含めず、`setup` / 統合起動 / 試験時に生成します。単独で拡張を読み込む場合は先に
ルートの `npm run sync:cursor` を実行してください。
背景タブの座標をデスクトップの前面タブへ描画しません。物理マウスはユーザーの共有入力デバイスです。

`click` / `type` / `press` / `check` は `inputRoute: "trusted"` が既定です。
DOM入力は `inputRoute: "dom"` を明示してください。結果は `trusted: false` を返します。
入力効果が不明なときにDOM入力へ自動で再送することはありません。先にページを再観測してください。
DOM clickは一回の左クリックに対応します。CSS hover、ネイティブUI、任意のドラッグを合成DOMイベントで代替しません。
ブラウザのタイムアウトや拒否は、ネイティブウィンドウのAX/画像操作を無効にしません。

## Windowsで確認できた範囲

2026-10-08にWindows上の隔離したヘッドレスChromium 153で、実際に読み込んだMV3拡張と
統合MCPの通し試験12項目が成功しました。CDP move/click/type、DOM入力、スクロール、
画像取得、同じStudioキャラの描画、設定更新、所有権・一時停止・前面タブ保護を確認しています。
背景タブの `active` はfalseで、試験中のタブ前面化イベントは0件です。
このChromiumではdebugger接続中の `document.hidden` はfalseでした。
タイマーが停止する状態の描画・後始末は別のDOM試験で確認します。

既存のWindows実機試験も専用WindowsComputerFixtureで成功しました。
被覆された背景窓のUIA/画像click、テキスト入力、UIA scrollはフォーカスと物理カーソルを維持します。
pixel scroll/background dragはCua 0.28.2が対応せず、明示的な前面配送と一操作承認が必要です。
最小化、別Windows仮想デスクトップ、任意のアプリへの配送は保証しません。

追加で通常版Chrome **154.0.8037.98** とEdge **154.0.4258.62** の専用ヘッドレス
プロファイルを使い、それぞれ17項目を確認しました。こちらは実Cuaの95ツール/Skillと
非表示の実Electron Studioを同じ試験に接続し、保存IPCから背景タブへの設定反映を検証しています。
ネイティブ側はスキーマ/Skillだけを読み、デスクトップ入力は拒否する設定です。
背景drag、ダブルクリック/右クリック、Unicodeのcontenteditable置換/削除、
Shadow DOMのref、古いrefの拒否、背景navigationも確認しました。両ブラウザともタブ前面化は0件です。

17項目には入力の拒否を検証する項目も含みます。両ブラウザの中クリックはtrustedの
mousedown/mouseupだけ届き、auxclickを確認できませんでした。部分配送は
`INPUT_OUTCOME_UNKNOWN` を返します。ブラウザ側の効果があり得るため、再送前に状態を確認してください。
キーもkeydownとkeyupの両方を、文字入力も実際のinputイベントを必要とします。

Chrome/Edge試験の拡張導入は、専用プロファイル限定のCDP `Extensions.loadUnpacked` を使います。
通常版Chromeは[Chrome 137以降、`--load-extension`を廃止](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/1-g8EFx2BBY/m/S0ET5wPjCAAJ)
しているため、実利用は上記の拡張管理画面から読み込みます。試験用の導入フラグはMCP起動設定には加えません。

画面に表示したChrome/Edge、実際のユーザープロファイル、外部サイト、macOSの統合実機試験は未実施です。
macOS用pytestをWindowsで実行した結果はOS固有処理等で失敗しており、macOS検証には使いません。

## 検証コマンド

架空SNSでのフォロー・いいねの実演は
[`demos/social/README.md`](demos/social/README.md) にあります。
`npm run test:social` でChrome/Edgeから実際に8回の操作を行い、
フォロー2人・いいね2件、解除と再適用、再読み込み後の保存状態を確認します。
`npm run demo:social` で保存済みの結果をブラウザから見られます。

```powershell
npm test
npm run test:browser
npm run test:browser:installed
npm run test:native
npm run test:studio
cd windows
.\.venv\Scripts\python.exe -m pytest -q
```

`npm test` はGUIへ入力しません。`test:browser` は捨てる専用プロファイルと架空ページだけを
ヘッドレスで使い、任意のユーザー窓を操作しません。Playwrightは `companion` の開発依存です。
Chromiumが未導入なら `npm exec --prefix companion -- playwright install chromium` で用意します。
`test:browser:installed` は導入済みChrome/Edge、ネイティブPython環境、Electronが必要です。
通常版ブラウザの使い捨てヘッドレスプロファイルだけで拡張を読み込み、基本のtrusted入力は
成功を必須にします。報告の `refusedInput` は配送成功と区別します。個別実行は
`node integration/tests/browser-live.mjs --browser chrome --native --studio --extended --require-trusted`
（Edgeは `--browser msedge`）です。
画像・生レポートは `integration/artifacts/` に保存し、Gitには含めません。
通常のGUI実機試験はOS別READMEの既存の専用fixture用スクリプトだけを使います。
`test:native` は実際のCuaへ接続してスキーマとSkillだけを読み、デスクトップ入力を行いません。
`test:studio` は別の設定ディレクトリと画面を出さないElectron描画で、実際の保存IPCから
共有ファイルへの反映を確認します。ユーザーのStudio設定は操作しません。
