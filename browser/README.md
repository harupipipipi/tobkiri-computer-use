# Tobkiri Tabs

AI専用のタブを色付きグループにまとめ、別のタブを人間が使っている間も、対象タブをバックグラウンドで操作するための **Chrome拡張 + ローカルstdio MCPサーバー**です。MITライセンス、実行時のnpm依存はありません。

> **v0.3.0 / 検証範囲は変更・ホストごとに記録しています。** サーバー・権限制御の自動テストに加え、今回のカーソル描画はmacOSのChromeとCodexのブラウザでDOM検証ページを使って確認しました。この統合版はWindowsの隔離したヘッドレスChromiumでインストール済み拡張を通した試験も実施しています。過去のWindows Vivaldiでの実拡張チェックを含む、実施内容と未検証の範囲は [検証記録](docs/VALIDATION.md) を参照してください。

## なにができる？

| 機能 | 実装 |
|---|---|
| タスクごとの色付きタブグループ | 名前・色の指定、名前変更、折りたたみ |
| バックグラウンドタブの作成・遷移・終了 | `active:false` で作成。前面化APIは公開しない |
| 既存タブの引き渡し | 拡張ポップアップから人間が対象MCPクライアントに許可 |
| ページ読み取り | 本文、操作要素のref、入力欄の状態、open Shadow DOM |
| ポインター移動・クリック・文字入力・キー・ドラッグ | `chrome.debugger` → CDP。OSマウス・OSキーボード・共有クリップボード不使用 |
| スクロール | 一番近いスクロール可能なDOM要素を直接スクロール |
| スクリーンショット | 対象タブの `Page.captureScreenshot`。通常/全ページ、PNG/JPEG、MCP image応答 |
| フォーム | checkbox/radio、native select、条件待ち |
| DOM・コンソール相当のJS | `browser_eval` で対象ページのMAIN worldを実行 |
| 通信記録・本文取得 | 対象タブのCDP Networkイベントを件数・容量制限付きで保存 |
| 通信ブロック・書き換え・模擬応答 | CDP FetchのURL条件ルール。期限付きで自動処理 |
| 人間優先 | 前面タブへの変更操作を標準で拒否。読み取りは可能 |
| 複数MCPクライアント | MCPプロセスごとに別セッション。別セッションの許可タブは取得・操作不可 |

グループは見た目の整理です。**グループに入れただけのタブは、自動ではAIに許可されません。** 許可台帳とグループの所属は別に管理します。

## 導入

### 1. Node.js 22以上でセットアップ

ZIPを展開し、展開した `tobkiri-tabs` フォルダで実行します。

```sh
node --version
npm run setup
```

`npm install`、ビルド、Docker、Native MessagingホストのOS登録は不要です。ブラウザを `--remote-debugging-port` 付きで起動し直す必要もありません。

セットアップは `~/.tobkiri-tabs/config.json` に256-bitのランダムトークンを保存し、ループバック専用ブリッジを起動します。端末には、拡張のフォルダ、**秘密のペアリングコード**、実際の絶対パス入りMCP設定が表示されます。

**ペアリングコードはAIチャットやリポジトリに貼らず、拡張ポップアップだけに入力してください。** MCP設定JSONにはトークンを含めません。

### 2. 拡張を読み込む

Chromeの `chrome://extensions` を開き、デベロッパーモードを有効にして「パッケージ化されていない拡張機能を読み込む」から、このプロジェクトの **`extension` フォルダ**を選択します。プロジェクトのルートではありません。

拡張アイコンを開いてペアリングコードを入力します。「AI専用タブの新規作成を許可する」を選び、「接続して、AI用の作業場所を用意」を押します。許可しなくても、人間が個別に渡した既存タブの操作はできます。

Chrome 120以上を対象にしています。Windowsの通常版Chrome / Edgeは専用ヘッドレスプロフィールで実拡張を検証しています。Braveや画面表示した通常プロフィールは未検証です。Firefox / Safari向けではありません。組織のポリシーが拡張やdebuggerを禁止している場合、その制限を回避せず管理者に確認してください。

### 3. MCPホストに登録する

`npm run setup` が出力した設定を使います。これは `mcpServers` 形式のホスト用の例です。

```json
{
  "mcpServers": {
    "tobkiri-tabs": {
      "command": "/absolute/path/to/node",
      "args": [
        "/absolute/path/to/tobkiri-tabs/src/cli.mjs",
        "mcp",
        "--config",
        "/absolute/path/to/.tobkiri-tabs/config.json"
      ]
    }
  }
}
```

Tobkiri等でトランスポートを選ぶ場合は **stdio**、起動コマンドと引数をそれぞれの欄に入れます。接続先を設定するHTTP MCPではありません。`http://127.0.0.1:17653` は内部ブリッジ用で、MCPの `/mcp` エンドポイントではありません。

MCPプロセス起動時、ブリッジが停止していれば自動起動します。複数のMCPプロセスは同じブリッジを共有できます。1つのブリッジに同時接続できるブラウザプロフィールは1つです。

ホストへ設定後、次のように依頼します。

> Tobkiri Tabsで「調査用」のワークスペースを作り、専用タブで example.com を開いて。本文を読み取り、スクリーンショットを撮って。私の前面タブは切り替えないで。

### 4. 既存のログイン済みタブを使う

対象ページを開き、拡張ポップアップの「このタブを渡す」でMCPクライアントを選択して渡します。その後、人間は別タブへ移動します。

前面タブの保護を有効にしたままで構いません。AI側は `browser_tabs` で許可されたタブIDを取得できます。**引き渡しはそのタブの以後のHTTP(S)遷移先にも及びます。** Cookieの書き出しは行いませんが、操作は同じブラウザプロフィールのログイン状態で行われます。

「人間に返す」はタブを閉じずに許可を取り消します。MCPセッション終了時も、タブを残して許可を解放します。再起動したMCPが以前のタブを無断で取り戻すことはありません。必要なタブは再度手動で渡してください。

## MCPツール

ツールのJSON Schemaと詳しい説明は `extension/shared.mjs` にあります。
通信操作の手順・範囲・期限は [DOM・通信操作](docs/NETWORK.md) を参照してください。

| 用途 | ツール |
|---|---|
| 状態・許可対象の一覧 | `browser_status`, `browser_workspaces`, `browser_tabs` |
| ワークスペース | `browser_workspace_create`, `browser_workspace_update`, `browser_workspace_release` |
| タブ | `browser_tab_open`, `browser_tab_navigate`, `browser_tab_close`, `browser_tab_release`, `browser_tab_regrant` |
| 読み取り・画像 | `browser_snapshot`, `browser_screenshot`, `browser_pdf` |
| 操作 | `browser_move`, `browser_click`, `browser_type`, `browser_press`, `browser_scroll`, `browser_drag` |
| フォーム・待機 | `browser_select`, `browser_check`, `browser_wait` |
| JS・生CDP | `browser_eval`, `browser_cdp` |
| 通信 | `browser_network_start`, `browser_network_read`, `browser_network_body`, `browser_network_routes`, `browser_network_stop` |

例：

```text
browser_workspace_create({"name":"PR1322 調査","color":"cyan","url":"https://example.com"})
  → workspaceId と tabId が返る

browser_snapshot({"tabId":返された数値})
  → 本文・ref付きの操作要素

browser_click({"tabId":返された数値,"ref":"最新snapshotのref"})
browser_type({"tabId":返された数値,"selector":"#search","text":"調べる内容"})
browser_press({"tabId":返された数値,"key":"Enter"})
browser_screenshot({"tabId":返された数値})
```

`ref`は次のsnapshotやページ遷移で無効になります。クリック対象はref、単一要素に一致するCSS selector、または座標のどれか1つです。曖昧なselectorや他の要素に覆われたクリック対象は失敗させ、適当な場所をクリックしません。

座標は **CSS viewport pixels** です。Retinaなどでは画像ピクセルと異なるので、スクリーンショットの `cssPerImagePixel` を掛けて変換してください。全ページ画像から操作座標を求める場合は、さらに `viewport.scrollX/scrollY` を引く必要があります。クリックには通常のviewportスクリーンショットを使う方が簡単です。

## アイコンとカーソルの変更

添付画像を `extension/assets/brand.png` に保存し、拡張アイコン・ツールバー・設定画面・設定画面のfaviconで共用しています。別の画像に変えるときは、次のコマンドで元画像と16/32/48/128pxのアイコンをまとめて更新し、拡張を再読み込みしてください。画像全体を残し、縦横比を保ちます。

```sh
# 初回のみ。Pillowは画像生成用で、拡張やMCPの実行時には不要です。
python3 -m venv .venv-icons
.venv-icons/bin/python -m pip install Pillow
.venv-icons/bin/python scripts/build-icons.py /path/to/new-image.png
```

WindowsではPythonのパスを `.venv-icons\Scripts\python.exe` に置き換えてください。引数を省略すると、保存済みの元画像から再生成します。

AIの操作位置には、ローカルに同梱したLucide `mouse-pointer-2` を表示します。色・サイズ・表示時間は **`extension/cursor-theme.mjs`** で変更できます。クリック・ドラッグ中は輪を表示し、移動・入力・スクロールにも追従します。OSのマウス位置は変えません。表示は操作後2.4秒で消えます。

`browser_move` はref・selector・CSS座標からポインターを移動するツールです。実際のmouse moveイベントがページへ届いたことを検証し、届かなければ `INPUT_NOT_APPLIED` を返します。CSS hoverを再現できない合成イベントによる代用は行いません。

描画を確認するには `node tests/visual-server.mjs` を実行し、表示されたローカルURLを開いてください。「描画チェックを実行」でDOMチェック、「設定画面のプレビュー」で実際のHTML/CSSを確認できます。このプレビューの接続・タブ情報は架空で、設定や許可は変更しません。インストール済み拡張の通しテストは別途 `tests/browser_e2e.py` です。

## 重要な制限

**「自分で前面に切り替えない」設計であり、サイトによる一切の割り込みを防ぐものではありません。** `window.open`、新しいタブを開くリンク、認証・OSダイアログなどはサイトやブラウザ自身が前面UIを出すことがあります。その種の操作は人間の介入が必要になる場合があります。

DOM操作はメインドキュメントとopen Shadow DOMが対象です。cross-origin iframeのDOM/ref操作、closed Shadow DOM、ネイティブファイル選択、ダウンロード管理、ブラウザ設定画面、拡張ストア、`file:` URLは対応していません。

**`browser_eval` と `browser_cdp` は許可されたタブ内で完全な権限を持ちます。** `browser_eval` はページのmain worldで任意JavaScriptを実行し（DevToolsコンソール相当：ページの変数・関数・DOM・canvasにフルアクセス）、`browser_cdp` は生のCDPコマンドをそのタブのデバッガセッションへそのまま送ります。いずれもowner/grant/一時停止/active-tab保護のチェックは全て通りますが、タブ内では無制限です。戻り値・console出力は信頼できないデータとして扱ってください。

JavaScriptのalert/confirm/promptは自動でdismissし、ログに記録します。ファイル選択ダイアログはinterceptしますが、ファイルの投入は実装していません。WebAuthn、CAPTCHA、ブラウザ外UIの自動解決は提供しません。

スクロールは**DOMの直接スクロール**です。通常のページやスクロールコンテナを扱えますが、wheelイベントだけで動く特殊なキャンバスUIにはそのまま使えません。初期の実Chromiumテストで非表示タブのCDP mouseWheelが応答待ちになる挙動を確認したため、前面化でごまかさずこの方式にしています。

非表示で止まるアニメーション・`requestAnimationFrame`・タイマー・メディア・フォーカス依存アプリは、表示中と同じ動作になるとは限りません。完全なメモリ破棄やブラウザ終了後も動作し続けるものではありません。作成したAIタブは自動破棄を一時的に抑制し、解放時に戻します。

## セキュリティと停止

ループバック `127.0.0.1` のみにbindし、Bearerトークン、Host/Origin検証、メッセージ上限、タイムアウト、セッション別の許可台帳を使います。ブラウザWebページから操作を受けるcontent scriptや `externally_connectable` はありません。

ただし、`debugger` は強力な拡張権限です。許可台帳はこのコードによる論理的制約であり、悪意ある拡張コードを閉じ込めるOSサンドボックスではありません。**購入・投稿・送金・削除などの意味的な承認はMCPホスト側でも有効にしてください。** ページ本文を「AIへの命令」として扱わないでください。詳しくは [SECURITY.md](SECURITY.md)。

ポップアップの「一時停止」は待機中の操作を止め、debuggerをdetachします。既に発生したクリックや送信を取り消すことはできません。タイムアウトした操作も結果不明の場合があるため、無条件で再実行しないでください。

```sh
npm run doctor    # 接続状態を確認。トークンは表示しない
npm run stop      # ローカルブリッジを停止。ブラウザのタブは閉じない
npm test          # Nodeのサーバー・権限制御テスト
```

ブリッジはセットアップ/MCP起動時にローカルの独立プロセスとして起動し、ブラウザやMCPを閉じても残ることがあります。不要になったら `npm run stop` を実行します。OSのログイン項目やサービスには登録しません。

別ポートにしたい場合は、初回セットアップ時に `node src/cli.mjs setup --port 17654` を使います。既存の設定ファイルを黙って上書きする動作はしません。トークンを失効させる場合は、停止→拡張の接続解除→自分の `~/.tobkiri-tabs/config.json` を削除→再セットアップ・再ペアリングの順で行います。

## 開発・検証

このWindows統合版では、ルートの `npm run test:browser` が専用プロファイルの
ヘッドレスChromiumに実拡張を読み込む通し試験です。共有描画コードはsetup/試験/統合起動時に
生成します。元プロジェクトのPython試験は下記に残していますが、今回の検証経路は
[統合手順](../integration/README.md) を参照してください。

```sh
npm test

# 実Chromiumの操作コアのみ。Python + websockets が必要。
python tests/cdp_core.py --chromium /path/to/chromium

# 実インストール拡張を含むE2E。Python + Playwright が必要。
python tests/browser_e2e.py --chromium /path/to/chromium
```

LinuxのGUIなし環境では別途Xvfb等が必要です。テスト用依存は通常の拡張/MCP実行には不要です。`browser_e2e.py` は管理ポリシーが全拡張を禁止している環境では回避せず終了コード77と理由を返します。

実測レポートと画像はローカルの `test-results` / `../integration/artifacts` に保存し、Gitには同梱しません。画像はテスト用の架空ページです。`docs/ui-preview.png` がある場合はポップアップのテストデータによる描画プレビューであり、インストール成功の証拠ではありません。

## 構成

```text
MCPクライアント
  └─ stdio / JSON-RPC
      └─ src/mcp.mjs
          └─ 認証付きローカルHTTP
              └─ src/bridge.mjs (127.0.0.1のみ)
                  └─ 15秒上限のlong-poll + 即時レスポンス
                      └─ extension/background.mjs
                          ├─ chrome.tabs / chrome.tabGroups
                          └─ chrome.debugger → CDP → 許可された対象タブ
```

long-pollは15秒ごとにしか操作しないという意味ではありません。待機中にコマンドが届けば即座に応答します。15秒は空の待機応答の上限で、MV3の停止・再接続処理と合わせて扱っています。MCPは2025-11-25等のstdio基本機能のみを実装し、tools/initialize/ping/cancellationを扱います。MCP Streamable HTTP、resources、prompts、tasks、OAuthサーバーは提供しません。

既存OSSでは `hangwin/mcp-chrome` が近い設計です。本プロジェクトはそのコードのコピーではなく、タブ別許可と人間の前面操作を優先する小さい独立実装です。参照した仕様は [REFERENCES.md](docs/REFERENCES.md)。

## 取り込み範囲

この統合版はブラウザ操作部分だけを取り込んでいます。元リポジトリのデータ収集スクリプトと評価データは含めません。取り込み元と変更範囲は [UPSTREAM.md](UPSTREAM.md)、統合起動は [integration/README.md](../integration/README.md) を参照してください。
