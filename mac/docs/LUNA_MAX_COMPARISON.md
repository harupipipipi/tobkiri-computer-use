# Luna Max: 同じ指示による比較

## 最新結果（2026-09-22）

現在の通常MCPは0.1.14、接続先はCandidate12と同じコードの固定アプリ
`/Applications/CuaDriverLocal.app`。Codexを再起動せず更新した。
0.1.13採用時の設定・socket・ネイティブPIDは `artifacts/native-adoption-0.1.13.json`。
0.1.14はPythonのLocator、状態待機、観測画像の座標グリッドを追加した版。
ネイティブ本体は変更せず、今回の追加検証はPythonテスト266件。使用した専用fixture
11個はユーザーの依頼で終了し、再起動していない。現在の更新記録は
`artifacts/release-0.1.14.json`、終了記録は `artifacts/fixture-cleanup.json`。
以下の描画・カーソルの実機結果は各節に記載した以前の版の試験である。
固定アプリ採用後も、Lunaが通常MCPから専用WKWebViewへ左クリックを1回送り、
down/up各1回を確認した。実処理PID10378・worker子argvとの対応を記録済み。
この確認の画像はMCP履歴内、独立focus probeは未取得。
記録は `artifacts/luna-max/stable-default-adoption/report.json`。

0.1.13の固定アプリによる長時間試験では、操作を加えない380.84秒の区間を終えても
同一窓に束縛した2sessionともactiveだった。保存済みtransportログを別途監査し、
この区間はlist_windows/get_session/get_agent_cursor_stateだけ、余計な入力・移動とerrorは0。
各カーソルの自動state readは6回、最大間隔は約60.11秒。Cuaの20秒idle fadeは保持しており、
静止中のcursor_visible=falseをセッション終了とは扱わない。記録は
`artifacts/luna-max/cursor-idle-stable/idle-transport-audit.json`。
同区間の後、窓を同サイズのまま+40,+30移動し、元の位置への復元を確認した。
復元後のnative報告位置は2本とも初期のscreen pointと一致した（浮動小数点誤差以内）。
移動中の値はPythonのanchor記録、復元後はnative stateの実測であり、証拠を区別している。
デスクトップ画像は他の試験窓とmacOSの確認画面に遮られ、実overlay pixelsは未確認。
記録は同ディレクトリの `report.json` と `translation-restore-audit.json`。

直前の版では通常のMCP接続先をCandidate12へ切り替えた。Codex再起動なしで0.1.12を反映し、
通常MCPからもWKの左クリック1回がdown/up各1回になった。設定と実接続の照合は
`artifacts/native-adoption-0.1.12.json`、GUI結果は `default-native-adoption/report.json`。

新しいLuna Maxを用いた初見試験では、Tobkiri 0.1.12 + Candidate10で5色の家と
`Luna house` のタイトルまで完成した。同じ `quality-prompt.md` を使い、以前の絵や
レビュー指摘、座標、描画手順を与えていない。53入力（タイトル1・色5・ドラッグ47）で、
専用窓6235のログはdown/up各47・drag937、drop/failは0だった。実行時間は14分45秒。
静止画では主要部品、屋根・壁・ドアの接続、キャンバス内への配置を別のLunaが確認した。
壁と緑線の直接接触は画像境界から確定できず `unknown`。塗り、光線、窓や線の数は
要求にないため優劣の根拠にはしていない。これだけで標準Computerより上とは結論しない。

新しい試験の画像・操作・イベントは `artifacts/luna-max/tobkiri_final_quality/`、
標準側との保存画像比較は `quality_judge/fresh_final_comparison.{json,md}`。
全描画イベントでapp_active/window_keyはfalseだが、描画試験の独立した連続フォーカス計測は
ないため、無干渉の一般的な証明とは区別する。以下には以前の結果も改変せず残す。

| 最新の同一指示による比較 | 標準Computer | Tobkiri 0.1.12 + Candidate10 |
| --- | --- | --- |
| 実行モデル | Luna Max | Luna Max |
| タイトル・5色・家と太陽 | 保存画像で確認 | 保存画像で確認 |
| 屋根・壁・ドアの接続 | 保存画像で確認 | 保存画像で確認 |
| 地面の直接接触 | 画像境界では確定不可 | 画像境界では確定不可 |
| 描画イベントの監査 | 初期fixtureのログ不備で比較不可 | down/up各47、drop/fail 0 |
| 一般的な精度の優劣 | この一例では未判定 | この一例では未判定 |

標準Computerの完成画像:

![標準Computer、Luna Maxの同一指示試験](../artifacts/luna-max/quality_judge/standard_quality.png)

Tobkiriの新しい初見試験の完成画像:

![Tobkiri、Luna Maxの同一指示試験](../artifacts/luna-max/tobkiri_final_quality/final.png)

### 以前の同条件試験と修正経過

速度を加点しない共通の `quality-prompt.md` で、標準ComputerとTobkiri 0.1.9 +
5patch候補の描画が両方完了した。両担当はLuna Max。別のLuna Maxが同じ読み取りAPI、
1400×1057、クリック印なしで両方の完成画面を取得した。

| 項目 | 標準Computer | Tobkiri 0.1.9 + 5patch |
| --- | --- | --- |
| タイトル・5色・構成要素 | 確認 | 確認 |
| 家の外形 | 青い壁、赤い屋根、Darkのドアと窓 | 同じ構成を輪郭線で描画 |
| 家と地面 | 底辺に近い緑の帯 | 底辺と緑の線の間に約50画像pxの隙間 |
| 太陽 | 水平線で埋めた円形 | 八角形の輪郭。塗りや光線は課題の必須条件ではない |
| キャンバス内への収まり | 確認 | 確認 |
| 実入力記録 | ハーネス不備で取得できず | 24ドラッグ、down/up各24。配送と画像の両方を確認 |

Tobkiriの24本の始点・終点をアプリが受け取ったイベントから観測画像へ戻すと、
指定点との差は最大0.393画像pxだった。これは固定した1つの窓での入力配送の測定であり、
カーソルの描画、移動中の窓、別Space、他アプリの精度まで証明しない。家と地面の隙間は
指定座標にも存在し、実行後の完成確認に改善余地がある。

証拠は `artifacts/luna-max/quality_judge/` の比較・両画像、
`artifacts/luna-max/tobkiri_quality/endpoint-accuracy.json` と元の操作記録。
フォーカス保持は独立測定しておらず、明示的な前面化命令がないだけで保持成功とはしない。
初回結果は保存し、0.1.10のskillによる追加の仕上げ試験は別ディレクトリに分離した。
単一課題・各1回の結果から完全上位互換やモデルの一般的成功率は結論しない。

0.1.10ではPythonの持続セッション手順、画像の接続・隙間を含めた完成確認、検索失敗と
入力結果不明の区別を改善した。`elements_complete=false` をツリー上限到達と誤説明していた
箇所も修正。217件のPythonテストが通過し、接続中MCPで再起動なしの0.1.10反映を確認した。

追加の無助言refinementではLunaが変更不要と判定し、追加入力は0件、前後画像も同一だった。
この結果はskillの改訂だけで完成度が改善した証拠にはならない。初回と追加試験は
`artifacts/luna-max/tobkiri_quality_refinement/` に分離して保存した。レビューで欠陥を伝える
修正試験はさらに別の `tobkiri_quality_review_fix/` とし、同条件の初期比較には合算しない。

0.1.11はネイティブ観測の `input.exact_window` と `input.routes` をPython/MCPの要約にも
保存し、経路の理由や未確認状態を読み取れるようにした。219件のPythonテストとskill検証が
通過し、接続中MCPの0.1.11反映も確認した。ネイティブ候補の切替とは別の更新である。

### 入力試験ハーネスの訂正

旧RawPointer fixture PID82345では、プロセスのスタックが `mouseUp → log → FileHandle/open`
で停止していた。ログにdown/upが無いだけでは入力が届かなかったとは言えない。
`native-six-preflight/harness-audit.json` と `native-six-diagnostics/raw-pointer-process-sample.txt`
に根拠を保存した。openが停止した根本理由は未確定で、OS権限が原因とは断定しない。

別のPointerProbe fixture PID85103は、独立したサンプルでは通常のAppKitイベント待機だった。
こちらのcallback 0件を同じlogger停止に帰属させる根拠はなく、原因未確定に訂正した。
詳細は `pointer-six-matrix/report.json` と `process-sample.txt`。両fixtureのログI/Oを
イベント処理から分離し、上限付きFIFO、永続FD、Library/Cachesへの保存、UI診断を持つ
新しいSafeFixtureを作成した。旧プロセスと元の試験証拠は保持して再試験する。

PointerProbeには別の確定した不具合もあった。全マウスイベントから `scrollingDeltaX/Y` や
`phase` を読んでいたため、AppKitが `NSInternalInconsistencyException` を発生させた。
画面へ投稿しないin-memoryのleftMouseDownでも各getterのSIGABRTを再現した。
型別getterを使うTypedFixtureを別bundleとして作成し、mouseとscrollWheelのカウンター・
ログ項目を非GUIテストで確認した。証拠は `artifacts/pointer-event-getter-reproducer.json`。
旧PointerProbe/SafeFixtureのcallback 0件も、配送欠落の証拠には使わない。

8patchの新しい描画fixtureでは、クリックがdown/up各1、ドラッグがdown/up各1・drag20となり、
描画とUndoによる2→1ストロークへの変化を新しい画像でも確認した。
`artifacts/luna-max/raw-safe-eight/report.json` に保存。独立probeは前後のforegroundと
物理ポインターが同じことを確認しているが、全操作中の連続したフォーカス保持は未検証。

0.1.12はアプリのAX応答停止に対してピクセル操作を勧めないようにし、AXエラーの元操作名と
コードを要約にも残す。220件のPythonテストとskill検証、接続中MCPの反映を確認した。
Candidate10は応答しないAX問い合わせと正常な空リストを区別する0010を追加したビルド。
旧RawPointer窓への1回の読み取り時点ではアプリが応答し、エラー無しで正しい窓が得られたため、
この実機試行ではエラー分岐そのものの再現にはならない。

レビュー後の修正試験では、地面と壁の隙間を言葉で指摘した後、Lunaが20入力で修正した。
別のLunaによる保存画像の確認では、地面・壁・ドアの接触と全構成要素・タイトルを確認し、
可視の退行は見つからなかった。緑線の下に隠れた暗色線の形状までは断定しない。
親は座標や描画手順を渡していないが、欠点の指摘を与えた試験なので、初見の成績とは分ける。
証拠は `tobkiri_quality_review_fix/` と `quality_judge/review_fix_verdict.json`。

typed pointer fixtureによる6patch対Candidate10の16入力では、AppKitの右クリックが
down/up/menu各2回から各1回になり、中央クリックは0回からdown/up各1回となった。
左クリックのdown/up各1回も維持された。1行スクロールの移動量はAppKitで20→10、
WKWebViewで80→40となった（各入力の差分であり、累積位置ではない）。
WKの左クリックは両候補ともAX経路でDOM callbackを生じず、右クリック後の中央クリックには
別領域AppKitのmouse-upが1件記録された。16ケースの生結果と画像・イベント・連続probeは
`pointer-typed-matrix/` に保存した。

Candidate12の追加試験は、メニューが開いていないことを観測してから同じ専用窓へ
中央クリック・左クリックを各1回送った。中央はWKのdown/up/auxclick各1回、左は
down/up各1回を記録し、別領域AppKitのイベントは発生しなかった。左クリックは従来の
AX経路からsynthetic_eventsへ変わった。両試験と重なる20ms間隔の独立probeでは
frontmost PID38677と物理ポインターが不変だった。証拠は `pointer-twelve-independent/`。
前のmenu可視ケースの原因を確定したわけではなく、任意のアプリ・メニュー状態へは一般化しない。

Candidate12の同サイズ移動では、移動前のズーム座標から対象窓へクリックし、点の追加と
down/up各1回を確認した。2カーソルのnative報告位置は窓と同じ+60,+50で追従した。
クリック中の独立probeではfrontmostと物理ポインターが不変。実カーソルの画像は
macOS確認画面や別窓に遮られたため未検証のまま。証拠は `window-translation-twelve/`。

以下は過去の試行と原因調査の記録。

## 初回比較（2026-09-21）

両担当は `gpt-5.6-luna / max`。同じ `benchmarks/luna-max/prompt.md` を読み、
同じコードから作成した空の専用アプリに「5色の家を描き、Luna houseというタイトルを付ける」
課題を実行した。親は画面を操作せず、描画座標や描き方を教えていない。

| 観測項目 | 標準Computer | Tobkiri 0.1.7 + Cua 0.28.2 |
| --- | --- | --- |
| タイトル | Luna houseを確認 | Luna houseを確認 |
| 色の選択 | 5色の描画を確認 | Ink Blueまで確認 |
| キャンバス | 壁・屋根・ドア・窓・地面・太陽、48ストローク | 最終観測0ストローク、未完成 |
| 実キャンバスイベント | down/drag/up 各48件 | 0件 |
| 時間 | 約2分18秒（開始は分単位の概算） | 約8分34秒（最終観測を含む） |
| 問題 | 保存APIなし、画像はツール出力 | 座標ドラッグとクリックが返らず中断 |

標準側の実イベントの最初から最後までは135.986秒。ただしモデルの思考・観測を含むため、
ツール単体の入力遅延としては扱わない。Tobkiri側の中断した呼び出しは結果不明として
扱い、再送せず、新しい観測で0ストロークを確認した。

両担当とも明示的な物理入力・前面化・Space切替を要求していない。一方、標準側の全144件の
入力イベントで `app_active=true / window_key=true` が記録されている。独立した前後の
フォーカス計測はしておらず、標準ツールが内部で前面化や復元をしたかは不明。
「ユーザーのフォーカスを一切奪わなかった」とは結論できない。

## 原因と修正の状態

Cua 0.28.2のソースには背景ドラッグを一律に拒否する処理がある。ただし今回のTobkiri試験では
その拒否応答すら返らなかった。追加調査で、入力前のカーソルアニメーションがキューへの
通知失敗を見落とし、到着を無期限に待つ経路を確認した。今回の停止時のスタックは取得して
いないため、同じ経路が直接の原因だったとまでは断定しない。

`patches/cua-driver-0.28.2/` の4つの修正を適用したネイティブ候補をビルドし、ローカル署名を
検証した。正確なウィンドウID検証を保つ背景ドラッグ、途中のイベント生成エラー時のボタン
解放、AXウィンドウ候補の統一、カーソル到着の無期限待ち解消を含む。ネイティブの関連する
単体テスト13件が通過した。詳細と再現手順は [NATIVE_DRIVER_PATCHES.md](NATIVE_DRIVER_PATCHES.md)。

Pythonのセットアップは、ドライバー実行ファイルのパスと内容を基に専用socketを選ぶよう
修正した。新ビルドの指定が起動済み旧ビルドへの接続になってしまうケースを回帰テストで確認。
既存の保存済みランタイム設定、共有デーモン、OS権限は変更していない。
Python 0.1.8の189件のテストが通過し、wheelを作成した。再起動せずに更新を配信し、
別のLuna Maxが接続中のMCPで `runtime_version=0.1.8`、`reload_error=null` を確認した。

ネイティブ候補は既存ランタイムと別のsocketでLuna Maxが起動した。MCP接続は成功したが、
最初のウィンドウ一覧取得が `permissions_pending`（exit 75）で拒否された。候補は元のCuaと
署名が異なり、この時点ではmacOSのアクセシビリティ・画面収録の初期許可が完了していなかった。
その後の許可と専用fixtureによる実機結果は末尾に記録する。この初回試験時点では
通常接続は元のCuaのままで、ネイティブの実機修正確認も未完了だった。

ズーム・赤い番号付きクリック履歴・座標と画像によるクリック前プレビューは0.1.7で実装済み。
この描画試験でそれら全機能の使いやすさを評価したわけではない。

別のLuna Maxによる追加試験では、AX要素の座標取得、3倍ズーム、元画像へ座標を戻す
クリック前プレビュー（`input_sent=false`）、実際の背景AXクリック後の赤い番号付き履歴を
確認できた。色ボタンの1回のクリックは1.723秒で戻り、canvasは0ストロークのまま。
配送結果は `effect=unverifiable` なので、赤い印をアプリへの入力成功の証拠とは扱わない。
詳細は `artifacts/luna-max/features/report.json`。

## 証拠

- `artifacts/luna-max/standard_baseline/report.json` と `events.jsonl`
- `artifacts/luna-max/tobkiri_baseline/report.json` と `latest.png`
- 同一プロンプトとbackend別設定: `benchmarks/luna-max/`
- 更新済みMCPの確認: `artifacts/luna-max/features/runtime-0.1.8.json`
- ネイティブ候補の起動とOS許可待ち: `artifacts/luna-max/native_preflight/report.json`
- ビルドと単体テスト: `artifacts/patched-driver/build-report.json`、`native-unit-tests.json`
- 別Spaceなどの先行試験: `docs/LUNA_ACCEPTANCE.md`

この結果では標準Computerが優位であり、Tobkiriを完全上位互換とは呼べない。
修正後の同条件再試験と、別Space・フォーカス保持・同一アプリの別窓への誤配送の検証を
通過するまで、その主張はしない。

## 独立したLuna Maxによる完成画面の確認

試験後に別のLuna Maxが、両方の正確なpid/window_idを一覧で確かめ、同じTobkiriの
読み取りAPI・`max_dimension=1400` で撮影した。両画像とも1400×1055。
この確認では入力を送っておらず、試験の所要時間や成功操作数にも加算しない。

標準Computerの完成画面:

![標準ComputerでLuna Maxが描いた家](../artifacts/luna-max/judge/standard_baseline.png)

Tobkiri 0.1.7の最終画面:

![Tobkiriでタイトル設定後、未描画のキャンバス](../artifacts/luna-max/judge/tobkiri_baseline.png)

判定の詳細は `artifacts/luna-max/judge/verdict.json`。

## 2026-09-22の再確認と評価方針

ユーザーから「速度より成果を優先」と指定されたため、次の比較用に共通の
`benchmarks/luna-max/quality-prompt.md` を用意した。課題は同じ5色の家で、完成度・正確さ・
ユーザー作業への影響を評価し、速度や呼び出し数では加点しない。元の同条件試験は書き換えず、
2つの空の専用アプリを別試験として使った。完成した比較は冒頭に記録する。

ユーザーのOS許可完了の報告後、Luna Maxが候補を再確認したところ同じpendingが返った。
ソース調査で起動時ゲートの10分タイムアウト後はpendingが固定されることが分かり、候補の
正確なsocket・実行ファイル・PIDを検証して、その候補だけを1回再起動した（PID 71700→13000）。
同一署名・同一設定で30秒待った後もpendingだった。既存・共有ランタイムは変更していない。

続いてLunaが候補アプリをLaunchServices経由で読み取り専用probeとして起動した結果は
`{"accessibility":true,"screen_recording":false}`。不足しているのは画面収録の許可と確認できた。
この診断は許可要求・GUI入力・既存候補デーモンの再起動を行わない。この時点でfixture操作は
0件であり、ユーザーに画面収録だけの設定を案内した。

証拠は `artifacts/luna-max/native_preflight/` の `restart.json`、`permission_wait.json`、
`permission_diagnosis.json`。診断と復旧手順は [NATIVE_DRIVER_PATCHES.md](NATIVE_DRIVER_PATCHES.md)。
Python 0.1.9では成果を優先するskillと、同じネイティブ版番号でも修正ビルドの機能が異なる
場合の判断方法を更新した。Pythonとネイティブの更新・実機確認は別々に扱う。

## 許可後の実機結果と5patch候補

ユーザーの許可後、Luna Maxが4patch候補のAX・画面収録ともtrueを確認した。
同一pidのA/B窓では、Aの意味的クリックとボタン座標クリックがAだけを変更した。
ただし専用描画窓への1回のドラッグで、線が表示された一方、カウンターが `Strokes 2` になった。
結果不明な操作を再送せず、証拠を保存した。元のドラッグがイベントを2つのPID配送経路へ送る
実装だったため、5つ目のpatchで1経路に限定した。修正版のネイティブ単体テストは16件通過した。

5patchのad-hoc署名ではOS許可診断がfalse/falseへ変わったため、このMacに既存の開発用
証明書を使うビルド設定を追加した。以降のresumeでも同じ署名元を使い、証明書とbundle IDを
指定要件に保つ。署名検証は通過したが、Luna Maxによる新しい署名でのOS診断もAX・画面収録ともfalseだった。
この時点の証拠は
`artifacts/luna-max/tobkiri_quality/setup-report-development-signature.json`。
その後、ユーザーがCua Driver Localを再許可し、01:58 JSTの同一署名probeで両方trueとなった。
証拠は同ディレクトリの `permission-probe-regrant-20260922T015852+0900-5646b60d0263442d8270787925829677.stdout`。
通常起動での権限チェックと、1ドラッグ・Undoの事前試験を通過後、同条件の描画を実施する。
この時点のPython全テストは署名設定の7件を含む196件通過し、既定接続への採用は未実施だった。

ユーザー指定のタスク「Follow computer use test prompts」
（`01a0c4cc-887c-79e1-939e-1a41f44a89eb`）へ、Luna Maxを明示してTobkiri側の試験を引き継いだ。
親はGUI入力をせず、座標・完成画像・描画コードを渡していない。共通プロンプトのSHA-256は
`4b03ec535772eeb5327a06683d24e3e57ad22ab0838cf2805ed039774250ce1a`。

標準側のLuna Maxは5色の家を完成したと報告し、最終表示105ストローク、入力推定111件と記録した。
この試行ではハーネスがイベントログの空ファイルを作り忘れ、実イベント記録を取得できなかった。
モデルの概算時刻・入力数を実測値とは扱わず、フォーカスを奪わなかったとも断定しない。
詳細は `artifacts/luna-max/standard_quality/harness-audit.json`。

独立したLuna Maxが標準側の現在のpid/window_idを照合し、入力せずに完成画面を保存した。
タイトルと指定した5色の各構成要素、屋根・壁・地面の接続、キャンバス内への収まりを確認した。
内部の密な水平線は塗りとして一貫して見え、離れた余分な線や大きな未完成部は確認されなかった。
画像は `artifacts/luna-max/quality_judge/standard_quality.png`、判定は同ディレクトリの
`standard_quality_verdict.json`。撮影は通常のTobkiri読み取りAPI、`max_dimension=1400`、
`marks=false` で行い、修正版Tobkiriの完成画面も同じ条件で評価する。
この静止画からフォーカス保持や実入力数は証明できない。修正版Tobkiriの同条件描画もその後完了し、冒頭に記録した。

比較のGUI担当と評価担当は、保存済み設定と実際のturn_contextでLuna Maxと確認した。
Sol mediumだったのはコード調査担当 `native_backend_audit`。証拠は
`artifacts/luna-max/model-audit-20260922.json`。
