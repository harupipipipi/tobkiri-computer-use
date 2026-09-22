# PR #1322に追従するための接続境界

この作業は独立パッケージの実装です。[PR #1322](https://github.com/harupipipipi/tobkiri/pull/1322)の
ブランチ・Profile・Packの設定には書き込んでいません。

調査したローカルのComputerHost契約はコミット
`8f7d73830a500fb4a3aec6eae9270ba1da73dc9a`時点です。
PRのAPI照会時のHEADは`da3ade8dcac9e66575f29fd068ea83853fee4d73`で、
そのHEADの`functions/computer_use/manifest.json`をGitHub APIでも確認しました。
同manifestは`computer.control`、`user.approved.high_risk`、
`authority_owner=core_runtime.authority`、`client_approved_trusted=false`、
`host_execution=false`を宣言しています。統合時には、その時点のHEADで再照合してください。

## 利用できる入口

- モデル用MCP: `tobkiri_computer_use.server:main`。
- Python SDK: `Computer` / `Window` / `Observation`。
- ホスト内のツール処理: `ToolService(computer).list_tools()`と`call(name,args)`。
- skill: パッケージ内リソース`skill/SKILL.md`。MCPでは専用resource URIでも読めます。

`Computer(transport=...)`には、ホストが認可済みのCua RPC transportを渡せます。
必要なインターフェースは`server_info`、`call`、`request`、`list_tools`、`close`です。
このインターフェースはCuaのRPCであり、既存`ComputerHost`のnative primitive契約に
そのまま互換ではありません。必要なホストアダプタはDefaults側で実装する接続点です。

独立プロセス方式なら、ホストが起動したprivate Cua endpointへ
`tobkiri-computer-use --socket /host/owned/private.sock`で接続できます。
これはCuaの`mcp --socket ...`へ渡す固定の起動設定です。
モデルのツール引数で実行ファイル・socket・環境・許可モードを選ぶ仕組みは設けていません。

単独利用の0.1.3では、ユーザーがsetupで選んだ`standard` + `existing-profile`を専用
LaunchServicesデーモンに保存し、Python/MCPが共用します。OSのTCC、既存プロファイル
接続認可、行為の意味に基づく確認、物理入力の承認は別の層です。
Defaultsでは同じ方針を信頼するhostに持たせ、通常の背景操作や仮想カーソルを承認待ちに
しないでください。ログイン・重要操作はhost/agentの文脈で判断し、物理入力はbrokerで
承認します。このPython SDKだけにクリックの意味の自動分類を任せる設計ではありません。

## 1操作ごとの前面入力承認

`Computer(transport=admitted_transport, approval_callback=host_broker_callback)`が追加の接続点です。
callbackは変更不能な`ConsentRequest`（request id、action、exact details JSON、reason、digest）を
受け取り、人間の明示的な判断を得た場合だけ同じid/digestの`ConsentDecision`を返します。
モデルの引数やUI内の「許可済み」表示からdecisionを生成してはいけません。
callbackは入力ロック内で呼ばれるため、同じComputerへ再入せず、独立した承認チャネルを使います。

許可は1回で保持されず、120秒経過、id/digest不一致、拒否、承認経路障害は入力前に停止します。
ウィンドウヘルパーは許可後に対象を再観測し、内容/位置の変化も拒否します。
MCPのツール引数にgrant、permission、callback、実行ファイル指定はありません。
標準Cuaの名前とスキーマは維持しますが、前面/desktop入力にはこの追加承認を適用し、
opaqueなtrajectory replayもこの承認を通した後に利用できます。通常の背景操作に
余分な確認を入れないため、内容が既知の操作列は個別の背景呼び出しとして実行します。
raw呼び出しの対象再観測はホスト側の責任です。

同一OSユーザーの任意コードや別のComputer/driverプロセスを、このPythonライブラリだけで
制限することはできません。PackVM内のPythonからホストのcallback/transport/OS入力APIへ
直接到達させず、core_runtime.authorityで行為ごとに認可してください。
端末/ダイアログの標準アダプタは単独実行用で、Defaultsの正規承認を代替しません。

## 対応表

| 既存ComputerHost側の概念 | このパッケージ |
| --- | --- |
| surface_id / selectors | pid/window_idを含む、ホストが検証した対象束縛 |
| observation_revision | `Observation.id`。native snapshot_idは内部で保持 |
| coordinate_space | `window_screenshot_pixels`。拡大画像は固有の変換を持つ |
| observe | `Window.observe()` |
| execute_primitive | 対応するWindow操作、またはスキーマを保持したCua呼び出し |
| verify | `Window.verify(expect)`。unknownを成功にしない |
| delivery/effect/postcondition | `ActionResult.delivery`と`verification`を別々に渡す |

## 統合時に残る作業

1. 正規のPack/tool登録経路でこのパッケージを登録し、各動作を既存のauthority・承認・
   resource policyへ結び付ける。元の`host_execution=false`を便宜的に変更しない。
2. ホストが認可したleaseごとに独立したComputer/ToolServiceを保持する。
   Python実行をPackVM内で提供する場合も、GUIの権限はホストbroker経由にする。
3. 標準はallモードでCuaの元ツール＋補助ツールを公開し、skillを対象会話へ供給する。
   定義量を減らしたいモデルに限りcompactを選ぶ。元ツールはオンデマンドで引き続き呼べる。
4. セッション終了・取り消し時に`Computer.close()`を呼び、leaseとカーソルを解放する。
5. exact catalog・PackVM・host approval・実機終了の既存ゲートを、統合したartifactで確認する。

このディレクトリだけのテスト結果は、Profileの起動やPackVMへの統合の証明ではありません。
