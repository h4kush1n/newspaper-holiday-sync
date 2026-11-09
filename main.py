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

def get_holiday_dates():
    current_year = datetime.datetime.now().year
    target_years = [current_year, current_year + 1]
    all_dates = []

    for y in target_years:
        dates = fetch_from_evolia(y)
        if dates:
            all_dates.extend(dates)
        else:
            print(f"[{y}年の休刊日データは未掲載または未検出]")

    return sorted(list(set(all_dates)))

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
    holiday_dates = get_holiday_dates()
    print(f"\n=== 最終取得リスト ({len(holiday_dates)}件) ===")
    print(holiday_dates)

    if not holiday_dates:
        print("エラー: 休刊日データが取得できませんでした。")
        return

    # カレンダー内の既存予定を取得して重複チェック
    existing_events = service.events().list(calendarId=calendar_id).execute().get('items', [])
    existing_dates = {ev.get('start', {}).get('date'): ev['id'] for ev in existing_events if ev.get('start', {}).get('date')}

    for date_str in holiday_dates:
        if date_str in existing_dates:
            print(f"【スキップ】登録済み: {date_str}")
        else:
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

if __name__ == "__main__":
    main()
