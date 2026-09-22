# Python の持続セッション: 観測から最小ドラッグまで（ドラフト）

これは Computer、Window、Observation、Point、ActionResult の公開 API だけを
使う対話用の手順です。1 回の作業では同じ Computer 接続と同じ Window を保持し、
毎回返された観測を次の判断に使います。

## REPL を開始する

インストール済みの環境で `python -i` を起動します。このcheckoutなら
`.venv/bin/python -i` です。ホストの実行ツールではTTY付きのセッションを保持し、
以後の入力は同じセッションへ送ります。毎回新しいシェルでPythonを起動しません。

    from tobkiri_computer_use import Computer, ComputerError

    computer = Computer()
    print(computer.windows())

一覧から依頼対象の正確なPIDとwindow_idを選び、次の行を同じREPLへ送ります。
ホストから特定の起動済みランタイムのcommandが指定されている場合は、最初の接続だけ
`Computer(command=指定されたcommand)` に置き換えます。

    window = computer.window(pid=PID, window_id=WINDOW_ID)
    state = window.observe()

    print(state.id)
    print(state.tree)
    state.save('/absolute/output/observe-01.png', marks=False)

保存先は自分の作業用ディレクトリの絶対パスを指定し、ホストの画像表示ツールでそのPNGを
確認します。REPLはcomputer、window、stateを保持します。操作ごとにComputer()を
作り直したり、同じウィンドウを再取得したりしません。作業を終える
ときだけ、REPL で computer.close() を呼びます。

## 画像から選んだ 2 点でドラッグする

state の画像を確認し、その画像内のピクセル座標を選びます。START_X、START_Y、
END_X、END_Y は説明用のプレースホルダーであり、実行時には直前の state の画像から
選んだ値だけを入れます。

    start = state.point(START_X, START_Y)
    end = state.point(END_X, END_Y)

    result = window.drag(start, end, duration_ms=500)
    print(result.delivery)

    state = result.observation
    print(state.id)
    print(state.changes)
    state.save('/absolute/output/observe-02.png', marks=False)

開始点と終了点は、必ず同じ Observation の point() から作ります。Window.drag() は
返却された ActionResult に次の Observation を含むため、その後のクリック、ドラッグ、
要素選択では更新後の state を使います。

    # 次の画面を見てから、その新しい画像に対応する座標を選ぶ。
    next_point = state.point(NEXT_X, NEXT_Y)
    result = window.click(next_point)
    state = result.observation

座標は観測画像のピクセル座標です。画面座標、Retina 倍率、またはウィンドウ原点を
自分で変換しません。ウィンドウのサイズ、画像倍率、または表示内容が変わった場合は、
state = window.observe() で新しい観測を取得してから新しい点を選びます。

## 結果を確認して続ける

result.delivery は配送結果で、state はその直後の観測です。配送の成功らしさと画面の
変化は別々に確認します。result.delivery が拒否を示す場合、または ComputerError が
発生した場合は、同じ入力を自動で再送しません。特に timeout は入力結果が不明です。
接続を維持したまま state = window.observe() で現在の画面を確認し、その観測に基づいて
次の手順を決めます。

この例の drag() は既定の window-targeted background 配送を使います。追加の確認処理や
foreground 指定はここでは加えません。必要な場合だけ、既存の Computer の承認ポリシーに
従って明示的に扱います。

## 最小ループ

同じ形式を繰り返します。

    # 1. 現在の state の画像と tree を確認する
    # 2. state.find(...) または state.point(...) でこの観測に結びついた対象を作る
    # 3. window の操作を 1 回だけ呼ぶ
    # 4. state = result.observation に更新する

古い state から作った点を新しい画面へ持ち越さず、不明な入力結果を再送しないことで、
持続接続を保ったまま各操作を個別に確認できます。
