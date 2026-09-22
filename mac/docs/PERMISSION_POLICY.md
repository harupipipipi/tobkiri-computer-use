# 0.1.3の権限方針と実機確認

2026-09-20。Cua Driver 0.28.2 / macOS。

## 原因

共有Cuaは`standard (built_in_default)`で、既存プロファイルの起動時grantがなく、
authorization hostも接続されていなかった。OSのAccessibility/Screen Recordingは
両方grantedだった。`browser_consent_required`はOSエラーではない。

`standard`は通常操作には確認不要だが、既存のログイン済みChromiumへの接続には
明示的なgrantを要求する。ユーザーが求めた方針を、Tobkiri専用runtimeの
`--permission-mode standard --grant existing-profile`へ反映した。
既存共有runtimeを停止せず、LaunchServicesで同じCuaDriver.appの別socketを起動する。
`unrestricted`やOS権限チェックの無効化は使用しない。

## 確認する範囲

| 操作 | 方針 |
| --- | --- |
| 画面の読み取り、通常の背景クリック/キー、仮想カーソル | 追加確認不要 |
| ユーザーが設定済みの既存プロファイルへの接続 | 追加確認不要 |
| ログイン、送信、削除、購入、重要な設定など | Computerの行為別ルールとユーザー指示に従う |
| 物理マウス/キーボード、前面フォーカス取得 | hostの実ユーザー承認が必要 |
| endpoint新規設定にブラウザの設定UIが必要 | 実行前に承認する |

意味に応じた確認はagent/hostの責務。ライブラリが座標だけから「購入」を自動判定する
ものではない。物理/前面入力の境界はコード側でも強制する。

## 確認結果

125テストとskill検証が成功。実際のPython `Computer()`およびCodex登録済みコマンドで
新規起動したMCP 0.1.3からVivaldiの11タブへ接続した。prepareの全side_effectsはfalseで、
確認前後のfrontmost appは同一。既存共有daemonも生存していた。
証跡: `artifacts/runtime-policy-acceptance.json`。

既存MCP接続を直接呼ぶと0.1.2のままだった。ファイルや設定を更新しても読み込み済みの
Pythonモジュールは更新されない。既存接続は再接続が必要。新規Python接続は即反映される。

Cua 0.28.2の`status`のPID表示はsocket別ではなく共通PIDファイルを読むため、複数daemonの
識別には`check_permissions(prompt=false).source.pid`と接続socketを使う。

参考: [Cua permission modes](https://cua.ai/docs/reference/cua-driver/permission-modes)、
[Cua process model](https://cua.ai/docs/reference/cua-driver/process-model)、
[OpenAI Computerドキュメント](https://developers.openai.com/ja-JP/docs/computer-use)。
