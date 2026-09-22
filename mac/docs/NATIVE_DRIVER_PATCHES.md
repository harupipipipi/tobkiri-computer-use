# Cua本体の修正版

対象ソースは Cua Driver 0.28.2、commit
`fc188250b4ca8549b8e61f937fdb1fb560770e86`。Pythonパッケージの更新とは別の
ネイティブビルドであり、MCPのバージョン表示だけでは本体の切替を確認できない。

現在の0.1.14はPython SDKのみの追加で、このネイティブ本体は変更していない。
現在のプロセス・socket・ハッシュは `artifacts/release-0.1.14.json`。以下のPIDとgenerationは
それぞれの採用・試験当時の記録であり、再起動後も同じ値であることは要求しない。

2026-09-22、Candidate12と同じコードを固定名 `/Applications/CuaDriverLocal.app` に
設置し、通常接続先に採用した。Python/MCPは0.1.13、当タスクの接続はgeneration 7（最後の再読込はSkillのfade説明追加）。
設置後のbinary SHA-256は `448bdb30275a6f1581924366f965b9a3ae48477e34b5ded0e84ed259000a9148`。
専用managed socket `driver-aac10f3230cddee9.sock` のmetadataが返す本体PIDは10378。
固定名への設置・署名確認は `artifacts/stable-native-install.json`、通常接続の設定と
更新結果は `artifacts/native-adoption-0.1.13.json`。手順とmacOSの確認の区別は
[固定アプリの説明](STABLE_NATIVE_INSTALL.md)を参照。Codex・共有Cuaの再起動はしていない。
固定アプリへの通常MCP接続から、専用WKWebViewの左クリック1回がdown/up各1回に
なることをLunaが再確認した。MCP worker10554の子10555のargvも固定binary/socketに一致。
`artifacts/luna-max/stable-default-adoption/report.json` に記録する。
画像はそのMCP履歴内にあり、この採用確認では独立focus probeを取得していない。

これ以前に通常の保存済み接続先をCandidate12へ切り替え、接続中のMCPを
0.1.12・generation 5へ再読込した。Codexと共有Cuaの再起動は行っていない。
設定、バイナリSHA、更新結果は `artifacts/native-adoption-0.1.12.json` に記録する。
通常MCPの別接続でも、対象WKWebViewの左クリックがdown/up各1回となった。
managed socketのmetadataが返す本体PIDは6422（起動親6421）。明示候補socketの本体PIDは
5189（起動親5188）。CLIの起動PIDと実処理PIDを区別する。
通常MCP試験の画像はツール履歴内で、独立した連続フォーカスprobeは取得していない。
その確認は同じバイナリの専用接続試験 `pointer-twelve-independent/` に限る。
以下の候補履歴にある「未採用」は、それぞれの試験当時の状態を示す。

5patch候補に含めた修正は次の5つ。

1. `0001-macos-exact-window-background-drag.patch` — 正確なpid/window_idを検証し、
   既存のPID宛てドラッグへ進む。物理入力への自動切替は追加しない。
2. `0002-macos-drag-always-releases-after-mousedown.patch` — ボタンを押す前に解放イベントを
   作り、途中のイベント生成エラーでも解放を送って元のエラーを返す。
3. `0002-macos-exact-ax-window-union.patch` — 観測と入力前チェックが同じAXウィンドウ候補を
   調べる。IDの推測はせず、矛盾する可視状態は未知のまま扱う。
4. `0004-macos-bounded-cursor-arrival.patch` — カーソル移動の通知失敗と到着待ちを区別し、
   無期限待ちをなくす。入力前のアニメーション失敗時は入力を送らない。
5. `0005-macos-drag-single-pid-route.patch` — ドラッグの各イベントを1つのPID配送経路だけに
   送る。SkyLightのシンボルが利用できない場合だけ公開APIを選び、配送後の別経路への再送はしない。

`0003-macos-ax-action-timeout.patch` は仮説を検証するための実験用で、通常の候補には含めない。
別Spaceで正確なAXウィンドウを解決できない問題は、この5patch群で解消したとは主張しない。

追加の6patch候補は、同じPID/CGWindowIDを検証したAXWindow参照を保持し、別Spaceで
AXWindows/AXChildrenから消えた際も、プロセス寿命・AXのPID/ID/role・WindowServerの所有と
Spaceを再検証して利用する。参照先をタイトルや位置で推測しない。
詳細は `patches/cua-driver-0.28.2/OFF_SPACE_AX_CACHE_README.md`。
`CuaDriverCandidate6.app` と別socketで試験し、稼働中の5patchアプリは上書きしない。
6patchのビルドと署名検証、関連するネイティブ単体テスト19件が通過した。
SHA-256は `3068fb020c4029bf262c4b9d9403b50dce1bb935eeff7f032a197956e5439f09`。
実機結果は `artifacts/luna-max/native-six-preflight/` に保存する。

8patch候補は、残る右・中央クリックとwheelの二重PID配送を除き、独立した `right_click`
にも汎用clickと同じフォーカス抑制を適用した。専用 `CuaDriverCandidate8.app` の
SHA-256は `c26ac3a8aa38fa58f35422afad07b2f6d01bbd0dd5568c281dade1f7a7425090`。
ビルド・署名検証と関連するネイティブ単体テスト21件が通過した。
`native-unit-tests-eight-patch.json` にバイナリと結果を対応させて記録している。
シンボル呼出し成功はアプリの受領確認ではなく、AppKit/WKWebView/Chromium間の互換性は
専用fixtureで別途検証する。二重配送を戻したり、未確認入力を別経路から再送したりはしない。

`0009-macos-exact-ax-cache-space-neutral.patch` は未採用の草案で、8patchには含めない。
パッチ番号のglobで実験用0003や草案0009をまとめて適用せず、ビルド記録の明示的な一覧を使う。
ネイティブ候補の試験と、現在の通常MCP接続先が切り替わったことは別に確認する。

Candidate10（計9本、0001/0002-drag/0002-union/0004/0005/0006/0007/0008/0010）は
トップレベルAX問い合わせの `-25204` を正常な空配列から区別し、観測と入力拒否の双方に
`ax_application_unresponsive` と元のoperation/codeを返す。正しい窓が他方のAX sourceから
得られた場合は使い、WindowServerの別PID・存在しない窓という診断も保持する。
応答停止にforegroundを推奨しない。詳細は `AX_READ_DIAGNOSTICS_README.md`。
SHA-256は `0842d0d1a27bf68937871d043454f8629db3041768a9ff77adb531a041854a0f`。
本体ビルドと署名、関連ネイティブテスト24件が通過した。Lunaの読み取り専用preflightで
AX/SR許可ともtrue、専用socketの実行ファイル・PIDも確認済み。
証拠は `native-unit-tests-ten-candidate.json` と `artifacts/luna-max/native-ten-preflight/`。

Candidate11（計10本）は0011を追加し、ピクセル点のAXヒット要素に対しては、現在の
対応アクションに `AXPress` があり、明示的な無効状態でもない場合だけAXPressを送る。
対象外ではAX入力を送らず、元からある正確なウィンドウ宛てピクセル経路を選ぶ。
SHA-256は `3eefd0bf78d3fa93f63d69c6e2c36b5a31d852c22de501242608c09bca7f2b4f`。
関連ネイティブテスト26件と、Lunaによる入力なしの許可・専用接続確認を通過した。
この段階ではWKWebViewの入力改善を実機で確認したとは扱わない。
証拠は `native-unit-tests-eleven-candidate.json` と `artifacts/luna-max/native-eleven-preflight/`。

Candidate12（計11本）は0012を追加した。サイズ不変の移動にsettableな `AXSize` まで
要求していた問題を直し、初回は実際に変わる属性だけを書き換える。両属性を変える場合の
Position→Size順、Tahoeで片方が戻った場合の補正、各書込み直前のsettableチェック、
正確な窓の所有確認、WindowServerでの最終確認を保持した。変更なしは入力を送らない。
SHA-256は `40ad28afa63228fd185141d3da23e519d51afbc6be2ff3df01e139fb22cb3380`。
関連ネイティブテスト36件と、LunaによるAX/SR許可・専用接続の確認を通過した。
詳細は `WINDOW_FRAME_REQUIRED_MUTATIONS_README.md`、証拠は
`native-unit-tests-twelve-candidate.json` と `artifacts/luna-max/native-twelve-preflight/`。
同じ専用WKWebView窓でのメニュー無し追加試験では、中央クリックのdown/up/auxclick、
左クリックのdown/upが各1回届いた。以前の候補でAX経路となりDOM入力がなかった左クリックも、
この候補ではsynthetic_eventsとなって受領を確認した。実入力と重なる独立probeで物理
ポインター・foregroundの不変を確認した。証拠は `artifacts/luna-max/pointer-twelve-independent/`。

同サイズ移動の実機試験では、専用窓を+60,+50移動しても古いズームから選んだ点へ1回だけ
クリックでき、対象窓のdown/up各1と追加の点を確認した。2つの仮想カーソルのnative報告位置も
同じ差分で追従した。操作と重なる独立probeでfrontmostと物理ポインターは不変だった。
実際のカーソル描画は別窓とmacOS確認画面に遮られ、画像としては未確認。
復元後には2番目のカーソルセッション終了のエラーも記録されており、無期限の追従を証明しない。
証拠は `artifacts/luna-max/window-translation-twelve/report.json`。

その後のPython0.1.13は、追従する各sessionへ60秒ごとのstate readを追加した。
固定アプリでの380.84秒の無操作区間を終えても2sessionともactiveで、各6回の自動read以外に
入力・移動を足していないことをtransportログで確認した。readは表示のidle fadeを止めない。
`artifacts/luna-max/cursor-idle-stable/idle-transport-audit.json` が独立したログ監査。
その後の同サイズ移動・復元も成功し、復元後は2本のnative位置が元のscreen pointと一致した。
同ディレクトリの `translation-restore-audit.json` に記録する。対象窓はdesktop画像内で他窓と
macOSの確認画面に遮られており、この追加試験もoverlayの実ピクセル可視は証明していない。

## ビルド

リポジトリの`mac/`内で実行する。Rust/CargoとXcode Command Line Toolsが必要。
初回はビルドスクリプトが検証する固定commitの上流ソースを用意する。

```sh
mkdir -p artifacts
git clone --filter=blob:none https://github.com/trycua/cua.git artifacts/cua-source
git -C artifacts/cua-source checkout --detach fc188250b4ca8549b8e61f937fdb1fb560770e86
```

元のCuaソースとインストール済みアプリは書き換えず、
`artifacts/patched-driver/` 内に生成する。共有デーモンの再起動や権限変更は行わない。

```sh
.venv/bin/python scripts/build_patched_driver.py --compact-native --app-name CuaDriverCandidate12 \
  --patch patches/cua-driver-0.28.2/0001-macos-exact-window-background-drag.patch \
  --patch patches/cua-driver-0.28.2/0002-macos-drag-always-releases-after-mousedown.patch \
  --patch patches/cua-driver-0.28.2/0002-macos-exact-ax-window-union.patch \
  --patch patches/cua-driver-0.28.2/0004-macos-bounded-cursor-arrival.patch \
  --patch patches/cua-driver-0.28.2/0005-macos-drag-single-pid-route.patch \
  --patch patches/cua-driver-0.28.2/0006-macos-off-space-exact-ax-window-cache.patch \
  --patch patches/cua-driver-0.28.2/0007-macos-pointer-single-pid-route.patch \
  --patch patches/cua-driver-0.28.2/0008-macos-standalone-right-click-focus-guard.patch \
  --patch patches/cua-driver-0.28.2/0010-macos-ax-top-level-read-diagnostics.patch \
  --patch patches/cua-driver-0.28.2/0011-macos-pixel-hit-test-axpress-eligibility.patch \
  --patch patches/cua-driver-0.28.2/0012-macos-window-frame-required-mutations.patch
```

既存の生成済みビルドを再開する場合は `--resume` を付ける。記録済みpatchのSHA-256を
保ち、追加patchだけを適用する。ディスク残量に下限を設け、到達したら自分のビルドだけを
停止する。ビルドを止めた後に `scripts/compact_build_cache.py` を実行すると、今回のCargo
生成物だけを内容のSHA-256が一致することを確認して圧縮できる。

コンパイルと署名の結果・patchのハッシュは `artifacts/patched-driver/build-report.json`。
上の例の成果物は `artifacts/patched-driver/CuaDriverCandidate12.app`。
既存のCuaとは異なるローカル署名を使う。稼働中の同名候補は上書きできないため、
再ビルドする場合は別の `--app-name` を選ぶ。

初回に有効な開発用証明書を使う場合は、`--signing-identity 証明書のSHA-1` を追加する。
選択した署名元をbuild-reportに記録し、以降の `--resume` では同じ署名元を引き継ぐ。
初回に未指定なら従来どおりad-hoc署名だが、その署名はバイナリの変更で指定要件のcdhashが変わり、
このMacでは更新後にOS許可の診断結果がfalseへ変わった。開発用証明書への切替後は証明書と
bundle IDに基づく指定要件となる。証明書切替時の再許可やmacOS側の判断は別途必要になり得る。
証明書が使えない場合にad-hocへ黙って戻さず、署名失敗として終了する。秘密鍵の書き出しや
TCCデータベースの変更、許可ゲートの無効化は行わない。

比較中の候補を別bundleへ出すには、安全なbasenameだけを --app-name に渡す。

~~~sh
.venv/bin/python scripts/build_patched_driver.py --resume --app-name CuaDriverCandidate \
  --patch ...
~~~

この例の成果物は artifacts/patched-driver/CuaDriverCandidate.app であり、実機比較では
その実行ファイルと専用socketを明示して選ぶ。--app-name に .app、パス区切り、空白などは
渡せない。bundle IDは引き続き com.trycua.driver.local、--resume 時の署名元も従来どおり
build-reportの選択を引き継ぐ。build-reportには選択したapp出力も記録する。

既存の選択bundleを書き換える前には、スクリプトがそのbundle内の正確な実行ファイルを
lsof -t で読み取り確認する。PIDが見つかった場合、または確認が失敗・不確実な場合は署名も
上書きもせず終了する。共有daemonの停止や自動killは行わない。その場合は --app-name で別候補を
作る。各bundleのmacOS許可はOSの判断に従う。

2026-09-22、5patchのビルドと既存の開発用証明書による署名検証が完了した。
実行ファイルのSHA-256は
`dc67ec710458b4b6bd22f460e2a2942e63678fdb46716e4da401b1fd954e8ec7`。
関連するネイティブ単体テスト16件が通過し、結果を
`artifacts/patched-driver/native-unit-tests-five-patch.json` に保存している。
4patch時点のバイナリと記録は `artifacts/patched-driver/four-patch-backup/` に保持した。
全テスト・全OSの検証や上流リリースを示すものではない。

## 実機確認と採用

最初の確認は、既存ランタイムを変更せず、専用socketと明示的な
`Computer(command=[新しい実行ファイル, "mcp", "--socket", 専用socket])` で行う。
この候補を操作するのはLuna Maxで、専用fixtureだけを使う。標準Computerの同条件試験は
`benchmarks/luna-max/`、前後の結果は `artifacts/luna-max/` に残す。

新しい署名のアプリが既存のCuaのmacOS権限を引き継ぐとは限らない。OSが要求する
アクセシビリティ・画面収録の許可はユーザー本人が行う。これは通常の背景クリックの
たびに確認を求めるルールではなく、新しい実行ファイルの初期設定である。

Luna Maxによる最初の起動では、専用の `candidate-native.sock` へのMCP接続は成功したが、
ウィンドウ一覧取得を含むツール呼び出しが `permissions_pending`（exit 75）で止まった。
この最初の試行では入力を送っていない。OS許可の対象は上記アプリで、表示名は
「Tobkiri Computer Use Driver」、bundle名は `CuaDriverLocal.app`。
現状と再試験用スクリプトは `artifacts/luna-max/native_preflight/` に保存している。
その後の許可完了と4patch候補の実機結果は下記に記録している。
この最初の試行時点では既存ランタイムへ採用していなかった。

### 許可後も `permissions_pending` が続く場合

Cua 0.28.2の起動時ゲートは通常1秒ごとに新しい子プロセスで権限を確認するが、既定の
10分でタイムアウトすると、残ったデーモンのpending状態を解除しない。後からOSで許可しても
そのデーモンは再確認しない。`check_permissions` と `health_report` も同じゲートで止まるため、
この応答だけから、現在もOS許可が不足しているとは判断できない。

この場合はCodex全体ではなく、設定した候補のデーモンだけを同じ署名・同じ起動設定で
再起動し、通常の権限チェックを通す。対象socketへの `metadata` lifecycleリクエストが返す
`result.pid` と候補実行ファイルの一致を確認し、候補のCLI
`stop --socket 対象socket --expected-pid 確認したPID` で停止する。再起動は同じ候補アプリを
LaunchServices経由で行う。共有の既定デーモンやTCC設定を変更せず、ゲートを無効化しない。

`status --socket` の表示PIDはこの版では共有のpidファイル由来なので、停止の根拠にしない。
`permissions status` も既定socketへ接続するため、この専用候補の診断には使わない。
入力中・結果不明の操作を解消する目的で再起動したり、その操作を再送したりしない。

ソース根拠: `platform-macos/src/permissions/gate.rs` のpoll/deadline、
`cua-driver/src/main.rs` のゲート完了処理、`cua-driver/src/serve.rs` の
`permission_gate_pending_response` と `metadata` / `shutdown_if_pid`。

ゲート中に不足項目だけを調べる場合、この版の内部読み取り専用probeを、候補アプリの
LaunchServices経由で実行できる。このmacOSの `open` は `--stdout` / `--stderr` を提供する。
出力先には新しい絶対パスを使う。

```sh
/usr/bin/open -n -W -g \
  --stdout /absolute/new/permission-probe.out \
  --stderr /absolute/new/permission-probe.err \
  /absolute/path/CuaDriverLocal.app \
  --args --cua-internal-permission-probe
```

`accessibility` と `screen_recording` のJSONを返す。Cua 0.28.2でのみソース確認した手順であり、
新しい版へ無条件に適用しない。これは `main` の先頭で終了し、daemon/socket・許可パネル・
カーソルの初期化を行わず、`AXIsProcessTrusted` と `CGPreflightScreenCaptureAccess` のみを
読む。`-W` で終了を待ってからファイルを読む。名前が似た
`--cua-internal-permission-probe-request` は許可要求を行う別モードなので診断には使わない。
実行ファイルをシェルから直接起動するとTerminal等の権限として判定され得るため、
アプリの許可を調べるには上記のLaunchServices経由を維持する。

2026-09-22、Luna Maxがこの読み取り専用診断を1回実行し、
`{"accessibility":true,"screen_recording":false}` を取得した。この時点で不足していたのは
候補アプリへの画面収録の許可。診断前後で候補PID 13000と起動引数は不変。
証拠は `artifacts/luna-max/native_preflight/permission_diagnosis.json`。

続くユーザーの許可後、4patch候補で両方trueを確認し、Luna Maxが同一pidのA/B窓を試験した。
AのAXボタンと座標指定ボタンのクリックはAだけを変更した。一方、専用キャンバスへの1回の
ドラッグで表示が `Strokes 2` となり、実際の線も確認できた。ソースにドラッグイベントを
SkyLightと公開PID APIの両方へ配送する処理があったため、5つ目のpatchで1経路に限定した。
4patchの実機結果は `artifacts/luna-max/native_preflight/final_result-20260922-granted.json`。

5patch候補のad-hoc再署名後、別のLuna Maxが読み取り専用probeで両方falseを確認した。
既存の開発用証明書へ切り替えた直後も、Luna Maxの読み取り専用probeは両方falseだった。
2026-09-22 01:58 JST、ユーザーの再許可後に同じ候補のprobeで両方trueを確認した。
診断は `artifacts/luna-max/tobkiri_quality/permission-probe-regrant-20260922T015852+0900-5646b60d0263442d8270787925829677.stdout`。
通常起動で両権限を確認し、5patchの1ドラッグが実際に1本だけ描かれた。
旧試験窓のUndoは別SpaceでAX解決が失敗し、未完了として保存した。その別問題を新規描画の
前提にせず、同条件の家描画を続けて完了した。24本でdown/up各24回を確認した。
画像比較は `docs/LUNA_MAX_COMPARISON.md`、旧窓の失敗は
`artifacts/native-preflight-five-patch-20260922T020718+0900-d5376cea/` に保持する。
この5patch試験時点では保存済みの既定ランタイムへ採用していなかった。
このpatchが変更するのはドラッグ配送だけで、一般のピクセルクリック・右クリック・ホイールの
別経路まで修正済みとは主張しない。SkyLightの戻り値もアプリ側の受領確認ではない。

検証済みの固定アプリを選択するホスト設定は次の通り。既存デーモンは停止せず、
バイナリに応じた専用socketを選ぶ。初回設置は `STABLE_NATIVE_INSTALL.md` を参照。

```sh
.venv/bin/tobkiri-computer-use-setup --existing-profile \
  --driver /Applications/CuaDriverLocal.app/Contents/MacOS/cua-driver-local
.venv/bin/tobkiri-computer-use-reload
```

Pythonパッケージの更新だけでドライバーは切り替わらない。設定された実行ファイルと
socket、接続先のmetadataを対応させて確認する。
