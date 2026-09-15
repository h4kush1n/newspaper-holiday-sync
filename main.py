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

def parse_dates_from_text(text, year):
    dates = []
    pattern1 = r'(\d{1,2})\s*月\s*(\d{1,2})\s*日'
    matches = re.findall(pattern1, text)
    
    for m, d in matches:
        m_int, d_int = int(m), int(d)
        if 1 <= m_int <= 12 and 1 <= d_int <= 31:
            date_str = f"{year}-{m_int:02d}-{d_int:02d}"
            if date_str not in dates:
                dates.append(date_str)
                
    return dates

def fetch_from_sanin_sc(year):
    url = "https://www.dailysanin.co.jp/holiday"
    dates = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        
        year_str = f"{year}年"
        if year_str in text:
            sub_text = text.split(year_str)[-1]
            dates = parse_dates_from_text(sub_text, year)
    except Exception as e:
        print(f"山陰中央新報SCからの取得失敗: {e}")
    return dates

def get_holiday_dates():
    current_year = datetime.datetime.now().year
    all_dates = []
    for y in [current_year, current_year + 1]:
        dates = fetch_from_sanin_sc(y)
        all_dates.extend(dates)
        
    return sorted(list(set(all_dates)))

def main():
    sa_key_json = os.environ.get("GCP_SA_KEY")
    calendar_id = os.environ.get("CALENDAR_ID")

    if not sa_key_json or not calendar_id:
        raise ValueError("環境変数 GCP_SA_KEY または CALENDAR_ID が設定されていません。")

    key_dict = json.loads(sa_key_json)
    scopes = ['https://www.googleapis.com/auth/calendar']
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    service = build('calendar', 'v3', credentials=creds)

    print("休刊日データを取得中...")
    holiday_dates = get_holiday_dates()
    print(f"最終検出リスト ({len(holiday_dates)}件): {holiday_dates}")

    if not holiday_dates:
        print("エラー: 休刊日の日付が検出されませんでした。")
        return

    for date_str in holiday_dates:
        start_time = f"{date_str}T00:00:00Z"
        end_time = f"{date_str}T23:59:59Z"
        
        # 同一日の既存予定を取得
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True
        ).execute()
        
        events = events_result.get('items', [])
        
        # 既存の古い予定を一旦削除（クリーンアップ）
        for event in events:
            service.events().delete(calendarId=calendar_id, eventId=event['id']).execute()
            print(f"【旧予定削除】 {date_str}")

        # カレンダー本体のデフォルト通知（当日6:40）を適用して新規作成
        event = {
            'summary': '新聞休刊日',
            'start': {'date': date_str},
            'end': {'date': date_str},
            'transparency': 'transparent',
            'reminders': {
                'useDefault': True  # カレンダー側のデフォルト通知設定に従う
            }
        }
        created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"【新規再作成】 {date_str} (デフォルト通知適用)")

if __name__ == "__main__":
    main()
