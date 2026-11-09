import os
import json
import re
import datetime
import requests
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def parse_evolia_html(soup, year):
    """evoliaのテーブル構造 (tr > th:月, td:日) から日付を正確にパース"""
    dates = []
    
    # list-table 内の table 行を走査
    list_table = soup.find('div', class_='list-table')
    if not list_table:
        list_table = soup
        
    rows = list_table.find_all('tr')
    
    for row in rows:
        th = row.find('th')
        td = row.find('td')
        
        if not th or not td:
            continue
            
        th_text = th.get_text().strip()  # 例: "2月" や "2026年"
        
        # 「1月」「2月」などの月情報を抽出
        month_match = re.search(r'(\d{1,2})\s*月', th_text)
        if not month_match:
            continue
        month = int(month_match.group(1))
        
        # td内のテキストを取得（注記の※以降や<br>以降を除外するため、最初の要素/行を取得）
        # brタグで分割して最初の行だけを見る
        for br in td.find_all('br'):
            br.replace_with('\n')
        
        td_lines = td.get_text().split('\n')
        
        for line in td_lines:
            line = line.strip()
            # 注記行はスキップ
            if line.startswith('※') or '選挙' in line or '変更' in line:
                continue
                
            # 「24日（火）」や「2日（金）」から日を抽出
            day_match = re.search(r'(\d{1,2})\s*日', line)
            if day_match:
                day = int(day_match.group(1))
                date_str = f"{year}-{month:02d}-{day:02d}"
                if date_str not in dates:
                    dates.append(date_str)
                break  # 最初に見つかった日（休刊日本体）を採用
                
    return dates

def fetch_from_evolia(year):
    # 【変更 2026-11-09】evoliaは翌年分を年付きURL（.../newspaper-holiday{year}/）に
    # 「速報」として先行掲載し、固定URLの翌年への切り替えが遅れる（2026-11-09時点で
    # 固定URLは2026年のまま、2027年分は年付きURLにのみ掲載されていた）。
    # そのため年付きURLを優先し、固定URLを予備として併用する。
    # 巻き戻し方法: urls を固定URLのみのリストに戻す。
    urls = [
        f"https://www.evolia.co.jp/promotion/orikomi/newspaper-holiday{year}/",
        "https://www.evolia.co.jp/promotion/orikomi/newspaper-holiday/",
    ]
    for url in urls:
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            if res.status_code != 200:
                continue  # 年付きURLがまだ無い年などは次の候補へ
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')

            page_text = soup.get_text()
            year_str = f"{year}年"

            if year_str in page_text:
                dates = parse_evolia_html(soup, year)
                print(f"[evolia] {year}年の抽出結果: {dates}")
                if dates:
                    return dates
        except Exception as e:
            print(f"evoliaからの取得失敗 ({url}): {e}")
    return []

def get_holiday_dates_by_year():
    # 【変更 2026-11-09】突き合わせ処理（compute_sync_plan）の前提として、取得結果を
    # 年ごとに保持して返す。「その年の取得が成功したか」を年単位で判定するために必要。
    # 巻き戻し方法: main.py.v1_urlfix.bak_20261109 の get_holiday_dates() に戻す。
    current_year = datetime.datetime.now().year
    target_years = [current_year, current_year + 1]
    by_year = {}

    for y in target_years:
        dates = fetch_from_evolia(y)
        if dates:
            by_year[y] = dates
        else:
            print(f"[{y}年の休刊日データは未掲載または未検出]")
            by_year[y] = []

    return target_years, by_year

def get_holiday_dates():
    # 互換用: 年別の取得結果を1つのソート済みリストにまとめて返す
    _, by_year = get_holiday_dates_by_year()
    all_dates = []
    for dates in by_year.values():
        all_dates.extend(dates)
    return sorted(list(set(all_dates)))

def compute_sync_plan(by_year, target_years, existing_events):
    """カレンダー同期の実行計画（追加・削除）を計算して返す。

    【追加 2026-11-09】日付変更・取消を取得データ側に合わせてカレンダーへ反映するための
    突き合わせ処理。従来は「未登録なら追加」のみだったため、登録後に休刊日が変更されると
    古い日付のイベントが残り続けていた（例: 選挙による日程変更）。
    安全性の要点（フェイルセーフ）:
      - 削除対象はタイトルが「新聞休刊日」の終日イベントだけに限定する。
      - 対象年（今年・来年）のイベントだけを扱い、過去年などの履歴には触れない。
      - その年の取得が成功（1件以上）した年だけ削除を許可する。取得失敗・未掲載の年に
        ついては削除を一切行わない（取得側の一時的な不調で既存登録を消さないため）。
      - 同一日付に複数イベントがある場合は1件だけ残し、残りを重複として削除する。
    巻き戻し方法: main() で to_delete を適用しないよう戻すか、
    main.py.v1_urlfix.bak_20261109 にファイルごと戻す。
    戻り値: (to_insert, to_delete)
      to_insert: 追加すべき日付文字列のリスト
      to_delete: (日付文字列, イベントID, 理由) のリスト
    """
    fetched_all = set()
    for dates in by_year.values():
        fetched_all.update(dates)
    verified_years = {y for y, dates in by_year.items() if dates}

    # 自分が登録したイベント（タイトル「新聞休刊日」の終日イベント）だけを日付→ID群に整理
    existing_map = {}
    for ev in existing_events:
        if ev.get('summary') != '新聞休刊日':
            continue
        date_str = ev.get('start', {}).get('date')
        if not date_str:
            continue  # 時刻指定イベントは対象外
        existing_map.setdefault(date_str, []).append(ev['id'])

    to_insert = sorted(fetched_all - set(existing_map.keys()))

    to_delete = []
    for date_str, ids in existing_map.items():
        year = int(date_str[:4])
        if year not in target_years:
            continue  # 過去年などの履歴イベントには触れない
        if date_str in fetched_all:
            # 登録継続。重複がある場合だけ余分を削除する
            for extra_id in ids[1:]:
                to_delete.append((date_str, extra_id, '同一日付の重複'))
        elif year in verified_years:
            for ev_id in ids:
                to_delete.append((date_str, ev_id, '取得データに存在しない（日付変更・取消の反映）'))
        # 取得できなかった年のイベントは、フェイルセーフのため何もしない

    return to_insert, to_delete

def main():
    sa_key_json = os.environ.get("GCP_SA_KEY")
    calendar_id = os.environ.get("CALENDAR_ID")

    if not sa_key_json or not calendar_id:
        raise ValueError("環境変数が設定されていません。")

    key_dict = json.loads(sa_key_json)
    scopes = ['https://www.googleapis.com/auth/calendar']
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    service = build('calendar', 'v3', credentials=creds)

    print("evolia から新聞休刊日データを取得中...")
    target_years, by_year = get_holiday_dates_by_year()
    holiday_dates = sorted({d for dates in by_year.values() for d in dates})
    print(f"\n=== 最終取得リスト ({len(holiday_dates)}件) ===")
    print(holiday_dates)

    if not holiday_dates:
        print("エラー: 休刊日データが取得できませんでした。")
        return

    # 【変更 2026-11-09】既存予定を全ページ取得し、compute_sync_plan の突き合わせで
    # 追加・削除を決める。従来は先頭ページのみの取得＋追加のみで、日付変更が反映されなかった。
    existing_events = []
    page_token = None
    while True:
        resp = service.events().list(calendarId=calendar_id, pageToken=page_token, maxResults=2500).execute()
        existing_events.extend(resp.get('items', []))
        page_token = resp.get('nextPageToken')
        if not page_token:
            break

    to_insert, to_delete = compute_sync_plan(by_year, target_years, existing_events)
    kept_count = len([d for d in holiday_dates if d not in to_insert])
    print(f"突き合わせ結果: 新規 {len(to_insert)}件 / 削除 {len(to_delete)}件 / 継続 {kept_count}件")

    for date_str in to_insert:
        event = {
            'summary': '新聞休刊日',
            'start': {'date': date_str},
            'end': {'date': date_str},
            'transparency': 'transparent',
            'reminders': {
                'useDefault': True
            }
        }
        service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"【新規登録】 {date_str}")

    for date_str, ev_id, reason in to_delete:
        service.events().delete(calendarId=calendar_id, eventId=ev_id).execute()
        print(f"【削除】 {date_str} （{reason}）")

if __name__ == "__main__":
    main()
