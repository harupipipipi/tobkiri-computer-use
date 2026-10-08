# Tobkiri Computer Use for Windows

Cua Driver を基盤に、Windows アプリを Python / MCP から正確なウィンドウ単位で操作します。
標準の Computer と同じ観測・クリック・入力・スクロール・ドラッグを備えつつ、対応する
UIA / PostMessage 経路では対象を前面化せず、ユーザーのフォーカスと物理マウスを維持します。

検証済み構成は Windows 11、Python 3.13、Cua Driver 0.28.2 です。Python 3.11 以上を要求します。

## セットアップ

PowerShell で `windows/` に移動して実行します。

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\tobkiri-computer-use-setup.exe --driver "C:\absolute\path\to\cua-driver.exe"
.\.venv\Scripts\python.exe -m pytest -q
```

セットアップは `%LOCALAPPDATA%\Tobkiri Computer Use\runtime.json` に絶対パス、名前付きパイプ、
`standard` 権限モードを保存します。既存のログイン済み Chrome / Edge プロファイルを使う場合だけ、
人間がセットアップ時に `--existing-profile` を追加してください。通常のツール呼び出しからこの許可を
追加することはできません。

MCP の例:

```json
{
  "mcpServers": {
    "tobkiri-computer-use": {
      "command": "C:\\absolute\\path\\windows\\.venv\\Scripts\\tobkiri-computer-use.exe",
      "args": ["--surface", "all", "--approval", "windows-dialog"]
    }
  }
}
```

`windows-dialog` は物理マウス／キーボードまたは前面フォーカスが必要な一操作だけを、対象と内容を
表示して許可します。既定の `deny` はその経路を拒否します。バックグラウンド操作に追加確認はありません。

## Python

```python
from tobkiri_computer_use import Computer, WindowsDialogConsent

with Computer(approval_callback=WindowsDialogConsent()) as computer:
    rows = computer.windows()
    window = computer.window(pid=1234, window_id=5678)
    state = window.observe()
    name = state.find("Name", role="Edit")
    state = window.set_value(name, "Ada").observation
    result = window.click(state.find("Apply", role="Button"))
    print(result.delivery)
    result.observation.save("after.png", labels=True)
```

要素と座標は一つの観測に結びつきます。別ウィンドウ、別観測、リサイズ後の古い座標は入力前に
拒否されます。ウィンドウ移動だけならローカル画像座標を保ち、ネイティブフレームを入力直前に更新します。
曖昧なラベル、無効な要素、同一アプリの重なった別窓、効果不明な入力の自動再送も拒否します。

## Windows の配送方針

- UIA の `invoke` / `set_value` / `scroll` と Cua のウィンドウ宛て合成イベントを最優先します。
- バックグラウンドで配送できない場合は、構造化エラーを返し、自動で前面入力へ昇格しません。
- Cua Driver 0.28.2 がバックグラウンド drag を `global_input` として扱う問題は、送信前に拒否します。
- 明示的な `delivery_mode="foreground"` と一操作承認がある場合だけ、Windows 0.28.2 の
  scroll / drag 欠落を `SendInput` で補います。対象 HWND / PID を再検証し、終了時に元の前面窓と
  物理カーソル位置を復元します。
- 最小化された窓は Cua 0.28.2 が画像を返せません。最小化を解除する自動回復は行いません。

## 実機受け入れテスト

専用の捨て WinForms fixture だけを操作します。通常の pytest はデスクトップへ入力しません。

```powershell
.\.venv\Scripts\python.exe .\scripts\build_fixture_windows.py --output .\artifacts\TobkiriWindowsFixture.exe
.\.venv\Scripts\python.exe .\scripts\live_acceptance_windows.py `
  --driver "C:\absolute\path\to\cua-driver.exe" `
  --output .\artifacts\windows-acceptance.json `
  --allow-foreground
```

`--allow-foreground` はこの fixture の scroll / drag フォールバックだけを模擬承認します。
実アプリ向けの永続許可ではありません。

このホストでは、被覆された背景窓の取得、UIA click、pixel click、`set_value`、`type_text`、
semantic scroll、前面 scroll / drag、フォーカス／カーソル復元、stale 観測拒否が成功しました。
全239件のpytestも通過しています。Cua 0.28.2がDPI拡大時に付加するWGCの黒余白は、破棄領域が
実際に黒であることを確認した場合だけ除去し、UIA・画像入力座標はそれぞれの座標系へ変換します。

2026-10-08の再検証では全250件のpytestが成功しました。前面配送を許可しない実機試験も
10項目成功（前面フォールバック2項目はskip）し、背景click/type/UIA scrollと
前面窓・物理マウスの保持を再確認しました。pixel scrollとbackground dragは拒否結果です。
実機スクリプトはJSONレポートと同じフォルダに操作前後のPNGも保存します。

## 仮想デスクトップと仮想ディスプレイ

`scripts/virtual_desktop_acceptance_windows.py` は、既に存在する別の仮想デスクトップへ fixture だけを
公開 `IVirtualDesktopManager` API で移動します。ユーザーのデスクトップは切り替えません。

```powershell
.\.venv\Scripts\python.exe .\scripts\virtual_desktop_acceptance_windows.py `
  --driver "C:\absolute\path\to\cua-driver.exe" `
  --output .\artifacts\virtual-desktop-acceptance.json
```

今回の Windows 11 / Cua 0.28.2 では、別デスクトップの窓を列挙して画像取得できましたが、
背景 pixel click は対象へ届きませんでした。したがって別デスクトップを入力隔離機構としては使いません。
仮想モニターは Windows の Indirect Display Driver が必要です。テスト機には IDD がなく、署名済み
ドライバーの導入はシステム変更を伴うため、このパッケージは勝手にインストールしません。

詳しい比較と実測結果は [Windows parity report](docs/WINDOWS_PARITY.md) を参照してください。
