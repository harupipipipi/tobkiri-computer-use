# Lunaによる実機比較 — 2026-09-21

標準ComputerとTobkiriを、Luna（gpt-5.6-luna / high）の独立したテスト担当で比較した。
Tobkiriは0.1.6、Cua Driverは0.28.2。親は空の専用描画アプリを準備し、絵の内容や
描画座標は担当のLunaが決める。Devin・音楽デモのコードは使わない。

## 別SpaceのChrome

対象は既存のonline-piano.ioページ、pid564/window820。標準Computerで61鍵をAXから
観測でき、B4クリック後に音名表示A3→B4とChromeの「オーディオ再生中です」を確認。
実際の音声は録音していない。次のF3クリックは表示変化がなく成功未確認。
操作後も対象はSpace1、current Space40で、前面化・Space切替・タブ切替は要求していない。

同じpid/windowをTobkiriで読むとAX要素0、`ax_window_unresolved`。
backgroundのAX・pointer・keyboardはいずれも`off_space_or_ax_unresolved`で拒否された。
これは別SpaceがOS上すべて操作不能という証拠ではなく、両バックエンドの機能差である。
詳細は`artifacts/luna-offspace/report.md`。

## ネイティブキャンバス

空のTobkiriDrawingFixtureに対し、LunaのPython `Window.drag`はCuaから
`Background drag is unavailable on macOS; use delivery_mode:"foreground"`で拒否。
0.28.2の`platform-macos/src/tools/drag.rs`にも背景モードを拒否する分岐がある。
通常のPythonループや短いアニメーション設定でこの制約は解消しない。

標準Computerで同じアプリを新しく観測して短いドラッグを実行すると、実際に線が残り
Strokes1→2となった。fixtureのイベントログにも短いdown/drag/upが記録された。
それ以前の点はdown/upが121秒離れており、送信元をログから特定できないため、
Pythonクリックの成功や遅延の証拠としては扱わない。

同意を得た物理入力への切替や、対象窓チェックの解除は実施していない。
Python試験の詳細と描画スクリプトは`artifacts/luna-drawing/`。

続いてLunaは標準Computerの観測・色ボタン・ドラッグで色つきの顔を完成した。
スクリーンショット`artifacts/luna-drawing/standard-face-after.png`で輪郭、青い目、
赤い口、緑の線、金色の飾りを確認。32ストロークのうち最初の2個は既存の比較用の点・線。
イベントログは同じwindow1556に32 down / 31 drag / 32 up、5色を記録している。
これは標準Computerによる完成例であり、TobkiriのPython描画が成功した証拠ではない。
標準Computerに前面化やSpace変更は指示していないが、厳密なフォーカス保持は測定していない。

## Pythonの要素座標・ピクセル描画試験

空の24×16マスと色選択ボタンを持つ専用TobkiriPixelFixtureを追加。
マスは普通のNSButtonで、選択色の変更と塗り操作は実際のGUIアクションだけで行う。
絵をファイルから読み込む機能や、親が絵を設定する経路は用意していない。

フルスクリーンと別Spaceを含む試験で、NSPanel版は要素を394件取得できても後続の
背景入力で窓のAX照合に失敗した。通常NSWindow版でも、fresh observeで394件を取得後、
Lunaがその観測の最初のセルをElementとしてクリックすると、
`AXUIElementPerformAction(AXPress) returned -25204`になった。次の観測では要素0。
1マスの塗り成功も確認できておらず、Pythonによる完成した絵とは扱わない。

Lunaは最初に座標Pointのtimelineを全体に投入してしまった。この方式はAXPressでは
なく、最初のマスの変化を確認していなかった。親がその点を指摘し、1セルのAX試験に
切り替えた。その試験でも上記のdriver errorが出た。モデルの手順改善とバックエンドの
不具合を分けて評価する必要がある。

## 更新とskill

再起動後のCodex MCP接続が0.1.6であることを確認。
その接続を維持したexplicit reloadと、更新マーカー公開による次リクエスト前のreloadを
実機確認した。後者はsupervisor10796を維持し、generation3→4、worker28249→29893。
終了済みCuaセッションによるread拒否も、明示的reload後の新しいreadで復旧した。
入力を再送せず、共有Cuaデーモンも再起動していない。

skillには実測した背景ドラッグ・別Spaceの制限と、最初の1操作で実変化を確認する
描画手順を追記。170 unit testsおよびskill validatorが成功した。
