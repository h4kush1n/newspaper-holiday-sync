# Newspaper Holiday Sync

静同新聞をはじめとする全国統一新聞休刊日の最新データをWebから自動取得し、個人のGoogleカレンダーへ完全自動同期するPython / GitHub Actionsパイプラインです。

パブリックカレンダーの更新遅延や手動登録の手間を排除し、毎月自動でGoogleカレンダーへ同期・メンテナンスを行います。

---

## 🛠 特徴 & アーキテクチャ

* **データソース:** `evolia` 公式固定ページ（`https://www.evolia.co.jp/promotion/orikomi/newspaper-holiday/`）からパース
* **頑健なノイズ除去処理:** 選挙等による日程変更の注記（「※」始まり、選挙・変更等のキーワードを含む行）をロジックレベルで除外処理し、確定休刊日のみを抽出
* **重複防止機構:** Google Calendar API v3 を使用し、既存登録済みイベントの重複スキップおよび更新チェックを自動実行
* **完全無人運用:** GitHub Actions（Cron）を利用した無料枠内（月間15〜20分消費）での高速・高信頼な全自動実行

---

## ⏰ 自動実行スケジュール

`.github/workflows/schedule.yml` にて以下のハイブリッドCronを設定しています。

* **通常期間 (1月〜9月, 11月〜12月):** 毎月1日 AM 9:00 (JST) に実行 (`0 0 1 * *`)
* **翌年データ警戒期間 (10月15日〜31日):** 毎日 AM 9:00 (JST) に高頻度実行 (`0 0 15-31 10 *`)
  * 毎年10月中旬〜下旬に公開される翌年版データを最速で検知し、カレンダーへ自動追加します。

---

## 🔑 環境変数・GitHub Secrets

本リポジトリの Actions を動作させるには、リポジトリの `Settings > Secrets and variables > Actions` に以下を登録する必要があります。

| Secret 名 | 説明 |
| :--- | :--- |
| `GCP_SA_KEY` | Google Cloud Service Account の JSON サービスアカウントキー |
| `CALENDAR_ID` | 同期先の Google カレンダーID（例: `xxxx@group.calendar.google.com`） |

---

## 💻 構成ファイル

```text
.
├── .github/
│   └── workflows/
│       └── schedule.yml    # GitHub Actions 実行定義ファイル
├── main.py                 # evoliaパース & Google Calendar API 同期スクリプト
├── requirements.txt        # 依存ライブラリ一覧
└── README.md               # 本ドキュメント
