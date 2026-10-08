# 架空SNS「こもれび」

フォロー・いいねをTobkiriの統合MCP経由で操作するローカル試験です。
人物・投稿・アカウントはすべて架空で、サーバーは127.0.0.1にだけ待ち受けます。
外部SNSとの通信やログインはありません。

ルートで `npm run test:social` を実行します。導入済みChrome/Edgeと
`companion` のPlaywright開発依存が必要です。拡張の読み込みは使い捨ての
ヘッドレスプロファイルだけで行い、ユーザーのプロファイルや物理入力を使いません。
WindowsのGUI実機チェックとは別の、ローカルブラウザ試験です。

各ブラウザで次を確認します。

- 新しいsnapshotのrefを使い、葵へのフォロー・いいねをtrusted clickで実行。
- 凪へのフォロー・いいねを明示的なDOM clickで実行。
- 葵のフォロー・いいねを一度取り消し、再度適用。
- UIの表示、サーバーの保存状態、8件の変更記録が一致し、カウントが重複しない。
- 再読み込みでフォロー2人・いいね2件を復元。
- 共有カーソルの画像取得と、タブ前面化0回・人間用fixtureのフォーカス/文字保持。

入力エラー時はそこで停止し、同じ入力を自動再送しません。ブラウザの操作は
productionのMCP・MV3拡張を使い、ネイティブ側は入力しないrouting fixtureです。
`browserReportedTrusted` はページから届く診断情報で、認可の根拠には使いません。
実SNSや任意サイトで同じ操作が成功することは、この試験では保証しません。

レポート・操作前後の画像・状態JSONは `integration/artifacts/social-demo/` に
保存され、Gitに含めません。試験後に `npm run demo:social` を実行すると、
Edge試験後の保存状態を使うSNSのURLが表示されます。停止はCtrl+Cです。
Chromeの保存状態なら次のように起動します。

```powershell
node integration/demos/social/server.mjs --state integration/artifacts/social-demo/chrome/state.json
```

保存データが無い場合は、未操作の状態で起動します。フォロー・いいねだけが
操作対象で、投稿作成・返信・検索は見た目のサンプルです。
