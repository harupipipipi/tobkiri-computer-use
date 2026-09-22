# Tobkiri Computer Use

Cua Driverを基盤にした、Python / MCP向けのComputer Use。ウィンドウに結びついた座標、
要素の検索、ズーム、クリック履歴とプレビュー、複数の仮想カーソルを提供します。

## 起動

この文書のコマンドはリポジトリの`mac/`内で実行してください。
文書内の`artifacts/`にある実機画像・生ログ・ビルド済みアプリはローカルの保存先で、
GitHubのソース配布には含まれません。

Python 3.11以上と、利用権限を設定済みの`cua-driver`が必要です。
実機で校正したバックエンドは **macOS / Cua Driver 0.28.2** です。
修正版本体の固定アプリへの設置は[固定名の運用](docs/STABLE_NATIVE_INSTALL.md)を参照。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/tobkiri-computer-use
```

標準入出力のMCPサーバーとして起動します。HTTPポートは開きません。
Cua標準ツールを動的に取得し、その名前・スキーマ・戻り値を保持します。
前面/desktop入力には追加の承認ガードがあります。一括trajectory replayも利用できますが、
内部の操作が前面/物理入力を含み得るため実ユーザー承認を通します。
Lunaなどには`--surface compact`が利用でき、最初に渡す定義を12ツールに限定します。
標準機能は`tools`で定義を確認して`call`で呼び出せます。

```json
{
  "mcpServers": {
    "tobkiri-computer-use": {
      "command": "/absolute/path/tobkiri-computer-use/mac/.venv/bin/tobkiri-computer-use",
      "args": ["--surface", "all", "--approval", "macos-dialog"]
    }
  }
}
```

既存のログイン済みブラウザを通常の背景操作に使う場合、ユーザーが方針を選んで一度設定します。

```sh
.venv/bin/tobkiri-computer-use-setup --existing-profile
```

`~/.config/tobkiri-computer-use/runtime.json`に保存し、Pythonの`Computer()`とMCPが同じ
専用socketを使います。macOSのLaunchServicesでCuaDriver.appを起動し、`standard`のまま
`existing-profile`だけを許可します。共有Cuaデーモンは再起動しません。専用デーモンが
停止していれば、次の接続時に保存済みの設定で起動します。起動済みのPython/MCP接続は
再読み込みが必要です。明示的な`--socket`や`Computer(command=...)`はホスト指定を優先します。
セットアップで選ぶsocketには実行ファイルのパスと内容のハッシュを含めます。
新しいドライバーを指定したのに、起動済みの旧ドライバーへつながることを防ぎます。
既存の保存済み設定は、セットアップを再実行するまで変更しません。

## Codexを終了せず更新する

0.1.6以降のMCPランチャーは、接続を維持するプロセスと操作するプロセスを分けます。
インストールとテストを終えた更新を、次のコマンドで反映できます。

```sh
.venv/bin/tobkiri-computer-use-reload
```

接続ごとの実行中の操作が終わり、次のリクエストが来た時点で処理プロセスを入れ替えます。
編集中のファイルは自動で読み込まず、公開後にファイルが変わっていた場合は更新を拒否します。
更新直後に古い座標で操作しようとすると、入力を送らず`runtime_reloaded`を返します。
新しい観測で続行してください。共有Cuaデーモン・権限・ほかのPython接続は変更しません。

MCPでは`tobkiri_runtime(action="status")`で読込済みバージョンを確認し、
`action="reload"`でその接続だけ再読み込みできます。ツール一覧が古いクライアントでも
`tobkiri_tools(name="tobkiri_runtime")`と`tobkiri_call(name="tobkiri_runtime", arguments={...})`
で新機能を発見・使用できます。普通のPythonは新しいプロセスから更新版になります。

**0.1.5以前からの初回移行だけは、設定のMCPサーバーを再接続する必要があります。**
Codexアプリ全体の終了は不要です。旧プロセスに後から更新機能を注入することはしません。
詳細と検証結果は[再読み込み](docs/RELOAD.md)。

## Python

```python
from tobkiri_computer_use import Computer

with Computer() as computer:
    print(computer.windows())  # ここからpid/window_idを選ぶ
    window = computer.window(pid=123, window_id=456)
    state = window.observe()
    button = state.find("Apply", role="AXButton")
    print(button.to_dict())    # 名前・状態・座標
    result = window.click(button)
    print(result.observation.changes)
    result.observation.save("result.png", labels=True)
```

座標は返却画像のピクセル単位です。画面原点、Retina倍率、縮小率を自前で計算する必要は
ありません。`state.point()`や`zoom.point()`は、その観測に結びついた座標オブジェクトを
返します。窓の位置だけが変わった場合、同じ画像座標・要素・ズーム座標を使えます。
入力直前に内部の画面原点とCuaの要素トークンを更新し、モデルに座標の再計算を求めません。
別ウィンドウ・古い観測・サイズ/画像倍率/要素配置が変わった座標は送信前に拒否します。
操作後の自動観測も、指定した画像サイズ・AX取得件数を維持します。AX取得の既定値は
Cua標準と同じ2000件です。`elements_complete=false`の場合は未取得の要素があり得るため、
表示中のボタンが見つからなければ`max_elements`を増やして再観測します。

### Pythonの処理を組み立てる

0.1.14では、使い回せる要素セレクターと、画面の変化を待つ処理を追加しました。
`Locator`は操作のたびに要素を探し直すため、前の操作で古くなった要素IDを使い回しません。

```python
name = window.locator("Name", role="AXTextField")
name.set_value("Ada")
state = window.wait_for(
    lambda s: s.find("Name", role="AXTextField").value == "Ada",
    timeout=5,
)
result = window.locator("Apply", role="AXButton").click(timeout=5)
```

待機は観測だけを繰り返します。入力は一度だけ送り、曖昧な一致やドライバーのエラーは
そのまま返します。`stop_event`による中止にも対応します。
`state.grid([left, top, right, bottom], rows=8, columns=16)`では、画像から選んだ領域を
等分して各セルの中心を取得できます。プレビューや静的な画面の`timeline`に利用できます。
座標の有効期限と単位は通常の`state.point()`と同じです。
詳しい例は[Python自動化](src/tobkiri_computer_use/skill/references/python-automation.md)。

詳しい手順は同梱[skill](src/tobkiri_computer_use/skill/SKILL.md)。MCPからも
`skill://tobkiri-computer-use/SKILL.md`で読めます。

## zoom・赤いクリック履歴・クリック前プレビュー

`state.zoom()` / `tobkiri_zoom`で画像を拡大できます。操作後の返却画像には、直近32件の
クリック試行を赤い点と番号で表示します。`state.save("raw.png", marks=False)`なら
履歴を描かない画像も保存できます。赤い点自体は操作成功の証拠ではありません。

0.1.7では、クリック予定位置を青い照準と座標で示すプレビューを追加しました。
全体画像と周辺の拡大画像を返し、クリック・カーソル移動・アプリへの問い合わせは送りません。

```python
state = window.observe()
preview = state.preview(state.point(480, 320))  # または state.preview(state.find("Apply"))
preview.save("click-preview.png")
preview.save("click-detail.png", detail=True)
print(preview.to_dict())  # 元画像の座標、拡大範囲、input_sent=False

zoom = state.zoom([400, 240, 600, 420], scale=3)
zoom.save("zoom.png")
planned = zoom.preview(240, 240)  # zoom画像の座標 → 元画像(480,320)
planned.save("from-zoom.png")
# 実行する場合だけ、別途 window.click(planned.point)
```

MCPは`tobkiri_preview`に`pid`, `window_id`, `observation_id`と`point: [x,y]`を渡します。
`point`の代わりに`element_id`も使えます。zoom内の座標には`zoom_id`を追加します。
返す画像の順序は全体・拡大。現在の接続に新ツールが表示されない場合も、
`tobkiri_tools(name="tobkiri_preview")`で定義を取得し、`tobkiri_call`から呼べます。

プレビューは保存済み画像での位置確認です。アプリの反応は予測せず、画面更新・
ウィンドウ移動を新しく取得しません。後のクリックでは通常の窓・観測・座標検証が働きます。
窓の位置だけの変更なら画像座標を維持し、リサイズや別窓・古い観測の座標は拒否します。

## 通常の入力と、許可が必要な最終手段

通常は`background`です。ユーザーのフォーカスを解除・復帰する処理は追加していません。
通常の仮想カーソル・背景入力・画面読み取りには追加確認を求めません。
ログイン、送信・共有・削除・購入などの重要操作には、ホストのComputerルールと
ユーザーの指示に従って確認します。実マウス/実キーボードや前面フォーカスを借りる場合には
追加で実ユーザー承認が必要です。窓を対象にした仮想カーソルは画面全体の座標を使う場合も
物理入力ではありません。一方、Cuaの`move_cursor(scope="desktop")`やdesktop targetは
実ポインタを動かすため承認が必要です。

Cua 0.28.2の`browser_consent_required`は、標準モードのプロファイル接続認可であり、
macOSの画面収録/アクセシビリティとは別です。上のsetupでユーザーが認可した後は
対応するブラウザ・endpointでは`browser.prepare()` → `browser.bind()`で接続できます。
既存endpointへの接続は通知不要です。CDP接続が利用できなくても、現在表示しているページの
Cua標準ウィンドウ操作（AX→画像座標）は使えます。
endpointの新規設定でブラウザ設定UIや前面入力が必要な場合は承認を通します。
重要操作の意味はagent/host側で判断し、Pythonの座標クリックが自動分類するとは保証しません。
ネイティブ文字欄の全体置換は`window.set_value(field, "...")`、挿入は
`window.type_text(field, "...")`、キーは`window.press_key("a", target=field)`を使います。
`observe()`の`input.background_keyboard`で配送経路の状態を確認できます。
複数窓でキーの配送先を証明できない場合は拒否します。Web入力は対象タブに結びついた
`browser_type`等を優先し、AX値だけを成功の証拠にしないでください。

専用の1窓AppKitアプリで、全体置換・文字挿入・キー入力・Applyを実機確認しました。
238サンプルで前面PIDとフォーカス要素のrole/位置/大きさに変化はありませんでした。
Codex Computerでも同じ操作で前面PIDが変わらないことを確認しました。任意アプリでの
動作保証ではありません。記録は`artifacts/background-focus.json`等にあります。

背景で操作できない場合、Cuaの`delivery_mode="foreground"`を最終手段として使えます。
PyAutoGUIのように共有入力と前面窓を使う経路で、**1操作ごとの実ユーザー承認が必須**です。
デフォルトは拒否。自動切り替え・永続的な許可・`approved: true`引数はありません。

```sh
# ホスト/ユーザーが起動時に選ぶ。モデルのツール引数では変更できない。
.venv/bin/tobkiri-computer-use --surface compact --approval macos-dialog
# 対話端末で運用する場合は --approval terminal
```

MCPでは`delivery_mode: "foreground"`と`fallback_reason`を`tobkiri_act`に指定すると、
ホストが対象・操作・入力内容を提示し、許可/拒否を待ちます。許可されるまで入力しません。
Pythonでは同じ承認アダプタを使えます。

```python
from tobkiri_computer_use import Computer, MacOSDialogConsent

with Computer(approval_callback=MacOSDialogConsent()) as computer:
    window = computer.window(pid=PID, window_id=WINDOW_ID)
    state = window.observe()
    result = window.type_text(
        state.find("Name"), "test",
        delivery_mode="foreground",
        fallback_reason="背景入力後の観測で文字が入らず、前面入力が必要",
    )  # 人間がダイアログでこの1回を許可した場合だけ配送
```

拒否、未設定、期限切れ、承認待ち中の対象変更では送信しません。許可後は同じ倍率で
再観測し、窓と要素を照合します。座標操作では画像の変化も拒否します。
前面操作と承認待ちは他の入力ジョブと排他です。低レベルの`bring_to_front`、
desktopスコープの物理マウス/キー、`delivery_mode=foreground`も承認を通ります。
desktopの画面読み取りや、window targetでの仮想カーソル描画には、この承認は不要です。
低レベル呼び出しにはヘルパーの再観測ガードは適用されないため、通常はヘルパーを使ってください。

元の前面アプリへの復帰はCuaのbest effortです。特に同じアプリの別窓や編集中のキャレットまで
完全に戻せるとは保証しません。操作中の手入力を避け、失敗時は観測してから判断してください。
標準の承認UIは単独利用向けです。モデルに同じプロセスの任意Python/OS権限を渡した状態を
隔離する仕組みではありません。Defaultsでは`approval_callback`を信頼するホストbrokerへ
接続し、モデルからコールバックやtransportを変更できない境界が必要です。

前面/物理入力の実機試験はユーザー許可前には実行しません。単体テストの模擬承認は、
その許可や実機での成功を意味しません。
今回の実機試験は承認確認で停止し、キーは送信していません。許可後の前面入力の成功は
未確認です。再試験用の`scripts/foreground_acceptance.py`にも実際の人間確認が入ります。

## 改善内容

| 項目 | 実装 |
| --- | --- |
| 標準機能 | Cuaの全ツールを実行時に取得してそのまま公開。ブラウザ、キー、ドラッグ等も保持 |
| モデル向けの操作 | 対象固定、名前/role検索、曖昧一致の拒否、古い要素の拒否、操作後の差分と画像 |
| 背景ブラウザ | 現在のページにはCua標準AX/画像操作。非表示タブには任意の`Computer.browser`経路で対象を固定 |
| Python | `Computer`、`Window`、`Observation`、`Element`、`Point`、`Zoom`、`ClickPreview` |
| 座標取得 | macOS AXフレームから画像上の中心座標を機械的に取得。非表示の要素には座標を捏造しない |
| ズーム | 元画像を切り出し、各クロップが専用変換を保持。窓/カーソル間で上書きしない |
| 赤い点 | 最大32件の番号付きクリック跡を画像に描画。アプリのDOMや文書は変更しない |
| クリック前プレビュー | `state.preview()` / `zoom.preview()` / `tobkiri_preview`で全体と拡大画像に予定座標を表示。入力は送信しない |
| 複数マウス | UUID付き独立セッション、複数窓の並列ジョブ、同じ窓の排他、明示的な終了 |
| 高速入力 | ヘルパーは1ms glide・dwellなし。`Window.timeline()` / `tobkiri_timeline`で時刻指定の背景クリック、同じ窓の複数カーソル、最後の観測 |
| カーソルずれ | ウィンドウ内の位置を保持して窓の移動に追従。0.28.2のscreen-point契約・表示倍率・負の画面原点を変換 |
| 別窓への誤操作 | 同一アプリの別窓と重なる座標入力・ドラッグ経路を拒否。ウィンドウ単位の配送を保証できないキー入力を拒否 |
| 最終手段 | 毎回の実ユーザー承認後だけ前面/desktop入力。対象変更・拒否・期限切れで停止、他ジョブの入力と排他 |
| 通信 | request IDごとのFutureで応答を配送。応答順序逆転、切断、タイムアウトに対応 |

## 比較と限界

### ブラウザではウィンドウとタブを分ける

現在表示中のページは、他のアプリと同じく`window.observe()`からAX要素を優先し、
要素が取得できない場合に画像座標を使います。CDP接続は前提条件ではありません。
操作後に再観測し、配送受付とページの変化を区別します。

非表示タブなど、タブを指定したい場合は任意で
`tobkiri_browser(action="bind", pid=..., window_id=...)`を使い、返された`browser_id`と
native state内の`target_id`/`tab_id`を保持します。その後の`state`、`click`、`type`、
`navigate`、`pointer`は対象タブを選択せずにCuaのブラウザAPIへ配送します。
ブラウザの`point`はCSSピクセルであり、ネイティブウィンドウ画像の座標とは別です。

```python
browser = computer.browser(pid=PID, window_id=WINDOW_ID)
binding = browser.bind()  # native MCP result: inspect structuredContent and refusals
result = browser.call("click", target_id=TARGET_ID, tab_id=TAB_ID,
                      ref=REF, input_route="dom_event")
state = browser.call("state", target_id=TARGET_ID, tab_id=TAB_ID)
```

既存プロファイルが`browser_consent_required`を返す場合、Cuaのホスト/起動時認可が必要です。
普通のMCP承認やモデルの`approved`引数では代替できません。`prepare`の既定値は
`isolated=false`で、保存済みホスト設定に従って既存プロファイルへの接続を試みます。
独立ブラウザの新規起動は明示的な`isolated=true, allow_launch=true`で要求します。
既存プロファイル指定自体は権限付与ではありません。

接続・セットアップの拒否はタブ/CDP経路だけに適用されます。0.1.4では、通常の
ネイティブ背景入力まで止めていた`browser_tab_required`の一律ガードを削除しました。
現在のページを新しく観測した上でAX/画像操作へ進めます。非表示タブを画像座標で
操作できるわけではなく、ユーザーのタブ切り替えやアドレス欄の上書きを復旧手順にしません。

非表示タブから画面上への位置対応は未実装です。ブラウザヘルパーはカーソルを
`not_projected`として返し、別タブの上に正しい位置で描いたと偽装しません。
ページ自身のAuto Playによる鍵盤変化は、エージェントの入力履歴とは別です。
このブラウザ追加部分は模擬タブによる回帰テストと実ドライバのスキーマで検証しています。
既存endpointへの接続は0.1.3で確認済みです。現在のVivaldiではendpointがなく、Cua 0.28.2の
既存プロファイル設定UIの自動操作は非対応でした。0.1.4のネイティブ背景クリックは
Cuaまで届き、直後の物理ポインタと前面アプリは不変でしたが、`effect=unverifiable`です。
直後の画像は不変で、後の画面変化の原因や音声再生の成功は確認できていません。

Codex Computerの実APIを使用し、専用AppKitアプリで「クリック→入力→適用」を比較しました。
採用したのは、対象を束縛したハンドル、短い要素表、操作をまとめた後の観測、差分表示です。
Codex内部の実装を複製したものではありません。

Cuaの機能自体は豊富ですが、元ハーネスはツール呼び出し・座標変換・結果検証を呼び出し側が
組み立てる必要がありました。本実装はその部分を担当します。小さいモデルへの効果は
設計上の狙いです。同じプロンプトを使うLuna Maxの描画比較を
`benchmarks/luna-max/` に用意し、実行結果を `artifacts/luna-max/` に保存しています。
単発の描画試験から一般的な成功率や標準Computerの完全上位互換は主張しません。

独立したカーソルは複数の物理マウスではありません。共有キーボードや前面入力は直列化され、
OS/ドライバもイベントを直列化することがあります。Mac以外の座標取得や実機操作、
任意のブラウザページ・iframeの正確な座標解決は未検証です。タブ単位の操作が必要な場合は
元のCuaのtyped browser toolsを使います。通常のウィンドウ経路も引き続き使えます。

別窓への誤操作ガードは`Window`と`tobkiri_*`の操作ヘルパーで適用します。
標準ツールと`tobkiri_call`はCua本来の低レベル契約を保持するため、同じガードを
追加適用しません。ただし前面/desktop入力の承認は共通で必須です。弱いモデルにはcompactモードと同梱skillを使い、拒否された入力を
rawツールで繰り返させない構成にしてください。状態一覧など読み取りだけのraw呼び出しは
ヘルパーの観測を破棄しません。入力やネイティブ観測の更新は、影響する窓だけを失効させます。

0.1.4での互換性点検と修正は[CUA_PARITY_REVIEW.md](docs/CUA_PARITY_REVIEW.md)を参照。

クリック跡は試行位置で、成功の証明ではありません。`effect=unverifiable`を成功に変換せず、
最新状態と`verify_state`の結果を返します。カーソルの`position_matches`はドライバ位置の照合で、
描画されたピクセルを検証するものではありません。未知のドライバ版のカーソル移動は、
座標契約を校正して設定するまで拒否します。

観測時にカーソルを対象窓の中央へ結び付け、その後は最後の操作位置を保持します。
入力がない間も窓の位置を100ms間隔で確認し、対象窓だけを追跡します。最小化・非表示・
別Spaceでは隠し、サイズ変更や消失では古い座標での復帰を止めます。サイズ変更後は
再観測して`window.move(...)`または操作で新しい位置を指定してください。
`computer.cursor_status()`や`tobkiri_cursor(action="status", pid=..., window_id=...)`で
追跡状態を読めます。通常の入力結果とは別に、表示側のエラーを返します。

標準Cuaを呼ぶ場合も、同じ接続で`get_window_state`した窓と、その後の明示的な対象指定を
使って各セッションの標準カーソルを束縛します。独立カーソルには別セッションを使います。
rawの独自`cursor_id`はこの追従の対象外です。窓が移動したら内部で画像フレーム/要素トークンを更新します。
旧Cuaの`from_zoom`は移動後に再取得が必要です。Tobkiriのズームはそのまま使えます。
この追従はポーリングとCuaの描画によるもので、移動中は100msに通信・描画時間を加えた
遅れがあり、OSと完全に同時の描画や移動中の原子的な入力配送は保証しません。
他の接続・別ツールが所有するカーソルには適用されません。

0.1.13では追従中の各カーソルを60秒ごとに読み取り確認します。静止中の2本目がCuaの
5分のidle期限で消える問題に対応し、入力や移動を追加しません。終了済みセッションは
復活させずエラーを返し、閉じた窓・消えた窓・サイズ変更した窓の追跡は終了します。

## 検証

0.1.14はPythonテスト266件を通過しました。ネイティブ本体は0.1.13から変更せず、
修正版Cua Candidate12の関連ネイティブテスト36件と実機確認の記録を保持しています。
Luna Maxの同じ指示での描画、ポインター入力、窓移動の実機記録は
[比較結果](docs/LUNA_MAX_COMPARISON.md)と[ネイティブ修正・接続先](docs/NATIVE_DRIVER_PATCHES.md)を参照。
通常のMCPは0.1.14に更新し、Candidate12と同じ修正を含む固定アプリ
`/Applications/CuaDriverLocal.app` を接続先に設定しました。Codexの再起動は不要です。

0.1.5の高速設定とPythonタイミング制御は
[LATENCY.md](docs/LATENCY.md)、使い方は[操作列のskill](src/tobkiri_computer_use/skill/references/timed-input.md)を参照。
標準Cuaのツール定義は保持し、この版では56標準＋11補助＋更新用1ツールです。

```sh
.venv/bin/python -m pytest
.venv/bin/python scripts/build_fixture.py
# 生成されたartifacts/TobkiriFixture.appを起動した後:
.venv/bin/python scripts/live_acceptance.py
.venv/bin/python scripts/target_isolation_acceptance.py
.venv/bin/python scripts/latency_acceptance.py
.venv/bin/python scripts/build_fixture.py --name TobkiriTrackingFixture
.venv/bin/python scripts/window_tracking_acceptance.py
```

テスト用アプリの2窓だけを対象とします。実機結果は`artifacts/acceptance.json`、画像は
`artifacts/`に保存します。`docs/COMPARISON.md`と`docs/DEFAULTS_INTEGRATION.md`も参照。
