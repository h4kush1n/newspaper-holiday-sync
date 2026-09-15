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

def parse_dates_from_tables(soup, year):
    """HTMLの <table> 要素内（セル）のみから休刊日の日付を抽出（テーブル外の注記を完全排除）"""
    dates = []
    pattern = r'(\d{1,2})\s*月\s*(\d{1,2})\s*日'
    
    # ページ内のすべてのテーブルを取得
    tables = soup.find_all('table')
    
    for table in tables:
        # テーブル内の各セル（td, th）からテキストを取得
        cells = table.find_all(['td', 'th'])
        for cell in cells:
            text = cell.get_text().strip()
            
            # 注記などの記号が含まれるセルは除外
            if "※" in text or "注" in text or "変更" in text or "選挙" in text:
                continue
                
            matches = re.findall(pattern, text)
            for m, d in matches:
                m_int, d_int = int(m), int(d)
                if 1 <= m_int <= 12 and 1 <= d_int <= 31:
                    date_str = f"{year}-{m_int:02d}-{d_int:02d}"
                    if date_str not in dates:
                        dates.append(date_str)
                        
    return dates

def fetch_from_evolia(year):
    """evolia公式の新聞休刊日固定ページから取得"""
    url = "https://www.evolia.co.jp/promotion/orikomi/newspaper-holiday/"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        page_text = soup.get_text()
        year_str = f"{year}年"
        
        if year_str in page_text:
            dates = parse_dates_from_tables(soup, year)
            print(f"[evolia] {year}年の抽出結果: {dates}")
            return dates
    except Exception as e:
        print(f"evoliaからの取得失敗: {e}")
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
