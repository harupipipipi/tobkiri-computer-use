# Tobkiri Computer Use

Cua Driverを基盤に、PythonとMCPからアプリを操作するComputer Useツールです。
実装は **`mac/`** にまとめています。現在の検証対象はmacOSとCua Driver 0.28.2です。

- ウィンドウに結びついた座標。位置だけが変わっても画像内の座標を維持します。
- Pythonの要素検索、`Locator`、状態待機、座標グリッド、時刻指定の操作。
- 画像のズーム、赤いクリック履歴、入力を送らず確認できるクリック前プレビュー。
- 複数の名前付き仮想カーソル。物理マウスは1つの共有入力デバイスです。
- Cua標準ツールの公開と、MCPクライアントを終了せず更新する仕組み。

通常の仮想入力は追加確認なしで進め、物理マウス・キーボードや前面フォーカスを
借りる操作は承認を通します。ログインや重要な操作はホスト側の確認ルールに従います。

## セットアップ

Python 3.11以上が必要です。Pythonパッケージの導入だけではネイティブドライバーは
インストールされません。Cua Driverの準備とOS権限の設定は
[macOSの手順](mac/README.md)と[修正版ドライバーのビルド](mac/docs/NATIVE_DRIVER_PATCHES.md)を参照してください。

```sh
git clone https://github.com/harupipipipi/tobkiri-computer-use.git
cd tobkiri-computer-use/mac
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest
```

通常のテストはデスクトップを操作しません。MCP設定、Pythonの使い方、実機試験は
[mac/README.md](mac/README.md)、エージェント用の手順は
[Skill](mac/src/tobkiri_computer_use/skill/SKILL.md)にあります。

## 構成

```text
mac/
  src/tobkiri_computer_use/  Python API・MCP・Skill
  scripts/                  ビルド・インストール・実機試験
  tests/                    単体テストと専用GUI fixture
  patches/                  Cua Driverへの修正パッチ
  benchmarks/               同条件のモデル比較用テンプレート
  docs/                     設計・検証記録・制約
  third_party/              上流のライセンス表記
```

## 検証状況

標準Computerを全面的に上回ることは、まだ確認できていません。
同じLuna Max・同じ指示による描画比較と、専用アプリでの座標・入力の試験を行っています。
任意のアプリ、別Space、実際のカーソル描画の追従までを保証する結果ではありません。
[比較結果と限界](mac/docs/LUNA_MAX_COMPARISON.md)に、確認できたことと未確認の点を記載しています。

実機の画像・生ログ・個人用設定・ビルド済みアプリはリポジトリに含めていません。
文書内の`artifacts/`はローカル試験時の保存先です。
Cua由来のコードの表記は[第三者ソフトウェアの情報](mac/third_party/README.md)を参照してください。
