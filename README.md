# Tobkiri Computer Use

Cua Driverを基盤に、PythonとMCPからアプリを操作するComputer Useツールです。
実装は **`mac/`** と **`windows/`** に分かれています。Windows版は Cua Driver 0.28.2 の
バックグラウンド UIA / PostMessage 経路と、一操作承認付きの前面入力を実機検証しています。

- ウィンドウに結びついた座標。位置だけが変わっても画像内の座標を維持します。
- Pythonの要素検索、`Locator`、状態待機、座標グリッド、時刻指定の操作。
- 画像のズーム、赤いクリック履歴、入力を送らず確認できるクリック前プレビュー。
- 複数の名前付き仮想カーソル。物理マウスは1つの共有入力デバイスです。
- Cua標準ツールの公開と、MCPクライアントを終了せず更新する仕組み。
- [Cursor Studio](companion/README.md)：48種類のしぐさで操作についてくるキャラクター。
  棒人間の見た目、手描きカーソル、自作PNGアニメーションを編集できます。
  「petだけ」と「カーソル＋pet」を切り替えられます。

通常の仮想入力は追加確認なしで進め、物理マウス・キーボードや前面フォーカスを
借りる操作は承認を通します。ログインや重要な操作はホスト側の確認ルールに従います。

## セットアップ

Python 3.11以上が必要です。Pythonパッケージの導入だけではネイティブドライバーは
インストールされません。OSごとの手順は [macOS](mac/README.md) または
[Windows](windows/README.md) を参照してください。

```sh
git clone https://github.com/harupipipipi/tobkiri-computer-use.git
cd tobkiri-computer-use/mac
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest
```

通常のテストはデスクトップを操作しません。MCP設定、Pythonの使い方、実機試験は各 OS の
README、エージェント用の手順は各パッケージの `skill/SKILL.md` にあります。

## 構成

キャラクターの編集・デスクトップ表示は `companion/` で `npm ci` → `npm start`。
Pythonは `Computer(companion=True)`、MCPは `TOBKIRI_COMPANION=1` で接続します。
詳しくは [Cursor Studio の起動手順](companion/README.md) を参照してください。

```text
mac/
  src/tobkiri_computer_use/  Python API・MCP・Skill
  scripts/                  ビルド・インストール・実機試験
  tests/                    単体テストと専用GUI fixture
  patches/                  Cua Driverへの修正パッチ
  benchmarks/               同条件のモデル比較用テンプレート
  docs/                     設計・検証記録・制約
  third_party/              上流のライセンス表記
windows/
  src/tobkiri_computer_use/  Windows Python API・MCP・Skill
  scripts/                  WinForms fixture と実機受け入れ試験
  tests/                    単体テスト
  docs/                     Windows比較・隔離実験
```

## 検証状況

標準Computerを全面的に上回ることは、まだ確認できていません。
同じLuna Max・同じ指示による描画比較と、専用アプリでの座標・入力の試験を行っています。
任意のアプリ、別Space、実際のカーソル描画の追従までを保証する結果ではありません。
[比較結果と限界](mac/docs/LUNA_MAX_COMPARISON.md)に、確認できたことと未確認の点を記載しています。

Windows版は同一WinForms fixtureの現行デスクトップ試験で標準Computerと同じ結果を出し、
バックグラウンドUIA経路ではフォーカスと物理カーソルを維持しました。別のWindows仮想
デスクトップは画像取得までで、入力配送は保証しません。詳細は
[Windows比較・隔離実験](windows/docs/WINDOWS_PARITY.md)を参照してください。

実機の画像・生ログ・個人用設定・ビルド済みアプリはリポジトリに含めていません。
文書内の`artifacts/`はローカル試験時の保存先です。
Cua由来のコードの表記は各OSパッケージの `third_party/README.md` を参照してください。
