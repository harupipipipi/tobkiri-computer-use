# Portable cursor themes

Mac・Windowsで同じテーマIDとCuaの描画経路を使います。Python/MCPは導入済みのIDを
選び、テーマの素材生成・コンパイル・導入はローカルのCLIで行います。

| ID | 見た目 | 導入 |
| --- | --- | --- |
| `cua.default` | Cua本来のカーソル。名前付きセッションの色もCuaに従います。 | Cua内蔵 |
| `tobkiri.arrow` | Windows風の白い矢印・濃い輪郭 | 下記のCLIで導入 |
| `tobkiri.stickman` | 手を振る棒人間・白い輪郭。動作別の青いアイコン付き | 下記のCLIで導入 |
| 任意の導入済みID | 独自のドット区切りID、例: `my.brand-cursor` | CuaのテーマCLIで導入 |

`Computer()`は既存のネイティブテーマ設定を維持します。Cuaの見た目を明示する場合は
`Computer(cursor_theme="cua.default")`を使います。テーマ対応には、
`set_agent_cursor_theme(session, theme_id, reduced_motion)`と、ローカルの
`cursor-theme`コンパイラを備えたCuaビルドが必要です。このチェックアウトのネイティブ
ソースは `fc188250b4ca8549b8e61f937fdb1fb560770e86` を基準にしています。
バージョン表記`0.28.2`だけでは、同じ機能を備えたビルドか判断できません。
旧ドライバーのshape/color/image引数への変換や、未導入テーマからの自動切り替えは行いません。

## Python / MCP

```python
from tobkiri_computer_use import Computer

with Computer(cursor_theme="cua.default") as computer:
    window = computer.window(pid=PID, window_id=WINDOW_ID)
    window.set_cursor_theme("tobkiri.stickman")
    print(window.cursor_state())
    window.set_cursor_theme("tobkiri.arrow", reduced_motion="on")
    window.set_cursor_theme("my.brand-cursor", reduced_motion="off")
    window.set_cursor_theme("cua.default")
```

`reduced_motion`は`auto`・`on`・`off`です。`on`はテーマの静止フレームを使います。
`set_cursor_speed("fast" / "normal")`は移動速度で、テーマとは独立しています。
複数の`mouse()`セッションで別々のテーマを選べます。新しいセッションの共通設定は
`Computer(cursor_theme=..., cursor_reduced_motion="on")`で指定できます。

MCPの`tobkiri_cursor`:

```json
{"pid":123,"window_id":456,"cursor":"left","action":"theme","theme_id":"tobkiri.stickman","reduced_motion":"auto"}
```

同じ`pid`・`window_id`・`cursor`で`action="state"`を呼ぶと、Cuaのテーマ情報、
アニメーション状態、表示状態、`fallback`診断が返ります。`action="status"`は従来どおり
ウィンドウ追従の状態で、セッションを新規作成しません。サーバー起動時には
`--cursor-theme tobkiri.stickman --cursor-reduced-motion on`でも設定できます。

切り替えはレンダラーへのキュー投入です。応答の成功や状態の読み取りだけでは実際の
表示ピクセルを証明しません。未導入テーマ・非対応ドライバーのエラーはそのまま返し、
入力の再送や権限設定の変更は行いません。テーマ変更は観測ID、ウィンドウとの結び付け、
画像/ズーム座標、クリック履歴、物理カーソルやフォーカスに影響しません。

## 組み込み素材の生成と導入

パッケージを更新すると`tobkiri-cursor-theme`コマンドが追加されます。ソースチェックアウト
では下記の`python -m`経路も使えます。両OSで同じソースを生成します。

macOS (`mac/`で実行):

```sh
.venv/bin/python -m tobkiri_computer_use.cursor_theme_cli tobkiri.stickman --install
.venv/bin/python -m tobkiri_computer_use.cursor_theme_cli tobkiri.arrow --install
```

Windows PowerShell (`windows/`で実行):

```powershell
.venv\Scripts\python.exe -m tobkiri_computer_use.cursor_theme_cli tobkiri.stickman --install
.venv\Scripts\python.exe -m tobkiri_computer_use.cursor_theme_cli tobkiri.arrow --install
```

インストール後の共通コマンド:

```sh
tobkiri-cursor-theme tobkiri.stickman --install
```

既定では`cua-driver cursor-theme build`でコンパイルします。`--driver PATH`はCua実行ファイル、
`--compiler PATH`は単独の`cua-cursor-theme`実行ファイルを選びます。
`--install`なしなら生成とコンパイルまで、`--source-only`なら素材生成だけでドライバーを
起動しません。生成先は既定で`artifacts/cursor-themes/`、`--output DIRECTORY`で変更できます。
生成済みの`.lottie`・`.cua-theme`・プレビューはGitに含めません。

ネイティブソースから単独コンパイラをビルドする場合は、CuaのRustワークスペースで
`cargo +stable build --locked -p cursor-theme-cli`を実行します。実行ファイル名は
`cua-cursor-theme` (Windowsでは`.exe`)です。Tobkiriはこのビルドやドライバー更新を
自動実行しません。

## 独自テーマの追加

独自の`.lottie`を、Cuaの`cua.cursor-theme/2`・`cua-driver-actions-v2`形式で作成します。
128×128・30fpsのキャンバスと、`idle`, `observe`, `click`, `drag`, `scroll`, `text`,
`key`, `navigate`, `app`, `transfer`, `record`, `system`の12動作を用意します。
`cursor_themes.source_entries("tobkiri.stickman")`から編集用のJSON構造を取得でき、
`--source-only`でdotLottieのZIPにまとめたテンプレートも生成できます。
独自素材の`cua/theme.json`には、独自のID・名前・作者・ライセンスを指定してください。
ドライバーは外部画像・スクリプト・任意のLottie機能を実行せず、対応するベクター命令を
境界付きの`.cua-theme`にコンパイルします。

```sh
cua-driver cursor-theme validate my-cursor.lottie
cua-driver cursor-theme build my-cursor.lottie --output my-cursor.cua-theme
cua-driver cursor-theme preview my-cursor.cua-theme --output artifacts/my-cursor-preview
cua-driver cursor-theme install my-cursor.cua-theme
cua-driver cursor-theme list --json
```

同じ`.cua-theme`を両OSに導入し、`window.set_cursor_theme("my.brand-cursor")`で選べます。
新しいIDのためにPython/MCPのスキーマを変更する必要はありません。MCPに素材のパスや
アニメーションのJSONを渡すことはできません。

Cua既定の導入先はMacが`~/Library/Application Support/Cua Driver/cursor-themes/`、
Windowsが`%LOCALAPPDATA%\Cua Driver\cursor-themes\`です。
`CUA_DRIVER_CURSOR_THEME_DIR`を使う場合は絶対パスで指定し、CLIとドライバーが同じ
ディレクトリを参照するようホスト側で設定してください。

## 検証

通常のテストはFakeTransportを使い、デスクトップを操作しません。テーマのセッション分離、
ネイティブ応答/拒否の保持、観測/座標の維持、素材の再現性、12動作、両OSの素材一致、
失敗したコンパイルから導入しないことを検証します。
この変更では両テーマをCuaの実コンパイラで検証し、12動作の静止プレビューを描画しました。
Mac上でWindowsパッケージの単体テストも実行しています。Windows実機のオーバーレイ表示と
ライブ入力の試験は未実施です。実機試験は各OSの専用fixtureとopt-in受け入れスクリプトで行います。
