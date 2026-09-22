# 固定名のネイティブアプリ

比較用のCandidateアプリは、既存プロセスを上書きせず別ビルドを検証するためのもの。
通常運用では `/Applications/CuaDriverLocal.app` を使う。Cua 0.28.2はこの名前を
ローカル版の正規アプリとして認識し、起動責任と直接キャプチャの許可確認にも利用する。
bundle IDと署名要件が同じでも、候補名のアプリはこのパス判定に一致しない。

`scripts/install_patched_driver.py` は検証済み候補から固定アプリへの初回設置を行う。
既存の固定アプリは上書きせず、デーモン停止、CLI置換、LaunchAgent変更、TCC変更を行わない。
正規の上流installerは再ビルドやデーモン停止も含むため、比較中の環境では代用しない。

```sh
.venv/bin/python scripts/install_patched_driver.py \
  --source-app artifacts/patched-driver/CuaDriverCandidate12.app \
  --signing-identity YOUR_EXISTING_CERTIFICATE_SHA1
```

初回設置のスクリプトであり、既存固定アプリの更新機能は含まない。

設置では候補のハッシュと署名を確認し、同じ開発用証明書で固定名のbundleを署名する。
指定要件（designated requirement）の同一性を確認してから、未存在の固定先に公開する。
名前を含むInfo.plistを変えて再署名するため、実行ファイル全体のSHAは候補と変わり得る。
元候補と設置後のSHAを別々に記録し、候補のSHAを設置後の値として使い回さない。

読み取り専用の許可診断と専用fixture確認が通った後、通常接続を選ぶ。

```sh
.venv/bin/tobkiri-computer-use-setup --existing-profile \
  --driver /Applications/CuaDriverLocal.app/Contents/MacOS/cua-driver-local
.venv/bin/tobkiri-computer-use-reload
```

MCPは次の呼び出し境界で更新し、既存の座標・観測は破棄する。Codex全体の再起動は不要。
明示commandを使ったPython接続は自動変更されないので、新しい `Computer()` で観測し直す。
実接続はMCP workerの子プロセスのargv、専用socketのmetadata、実行ファイルを照合する。
`generation` は接続ごとの更新回数であり、別のタスクと値が違っていても異常ではない。

## 追従中のカーソルの状態確認

0.1.13は追従中の各カーソルの状態を60秒ごとに読み、標準Cuaの5分のsession idle期限で
静止中の2本目が消える問題を防ぐ。入力・移動の追加や終了済みsessionの復活は行わない。
対象が閉じた、消えた、サイズ変更した場合は停止し、非表示の同一窓にはreadだけを続ける。

現在の `standard + existing-profile` はauthorization contextのidle/absolute TTLを持たない。
将来delegated/bounded contextやcapability manifestを使う構成では、通常の認可済みreadも
それらのidle leaseを更新するため、同じ設計の採用前に再検討する。absolute期限や失効、
終了済みsessionは延長・復活しない。根拠はCuaの `tool.rs`、`session.rs`、
`session_authorization.rs`、`session_manifest.rs`。

セッションの5分idle期限と、カーソル表示の20秒idle fadeは別の状態。
`get_session.cursor_visible=false` はrender stateの値だが、静止中の正常なfadeでもfalseに
なる。状態readではfadeをresetしない。Pythonの `following / hidden=false` は窓への束縛と
明示disableの有無であり、継続的なピクセル可視を意味しない。移動後の再出現は別途確認する。
根拠は `session_tools.rs`、`session.rs`、`platform-macos/src/cursor/overlay.rs`、
`cursor-overlay/src/motion.rs`、`cursor-overlay/src/render_state.rs`。

## macOSの2つの画面取得確認

通常の `CGPreflightScreenCaptureAccess` と、ScreenCaptureKitでウィンドウを直接取得する
確認は同じではない。AX/Screen Recordingの診断がtrueでも、macOSの直接取得の確認画面が
出ることがある。Cua自身も、状態照会だけではその画面を出さないよう直接取得probeを省く。
固定のアプリ名・パス・署名を使っても、OSによる再確認がなくなるとは保証しない。

このスクリーンショット実装は音声取得を有効にしていない。確認画面が画面と音声を併記するのは
macOSの統合した文言で、Tobkiriに音楽再生や録音機能を追加したことを意味しない。
確認画面の遮蔽でカーソルが見えない場合、内部の位置が合っていても実描画は未確認と記録する。

ソース根拠はCua 0.28.2の `cua-driver/src/bundle.rs`、
`platform-macos/src/tools/check_permissions.rs`、`platform-macos/src/capture.rs`、
`libs/cua-driver/scripts/_install-local-rust.sh`。実機の記録は
`artifacts/luna-max/window-translation-twelve/` に保存している。
