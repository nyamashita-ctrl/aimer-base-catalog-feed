# aimer-base-catalog-feed

Meta（Facebook/Instagram）の商品カタログ用フィード。
BASEショップ https://aimer12.base.shop/ の公開ページから商品情報を読み取り、`feed.csv` を毎日更新する。

- フィードURL: `https://raw.githubusercontent.com/nyamashita-ctrl/aimer-base-catalog-feed/main/feed.csv`
- 更新: GitHub Actions が毎日 03:00 JST に実行（`workflow_dispatch` で手動実行も可）
- 商品 `id` は BASE の商品ID。BASE のピクセルが送る `content_ids` と同じ値なので、カタログ広告で閲覧履歴と商品が突き合う
- `custom_label_0 = members_only` は BASE の「会員限定商品」。商品セットで除外する用
- 認証情報は不要（公開ページのみ、1.2秒間隔で取得）

Meta 側の受け取り: コマースマネージャ → カタログ「カタログ_商品」(1057130093907445) → データソース → 定期取得（毎日 04:00 JST）。
