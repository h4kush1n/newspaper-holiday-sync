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
        raise ValueError("環境変数が設定されていません。")

    key_dict = json.loads(sa_key_json)
    scopes = ['https://www.googleapis.com/auth/calendar']
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    service = build('calendar', 'v3', credentials=creds)

    print("休刊日データを取得中...")
    holiday_dates = get_holiday_dates()
    print(f"取得できた休刊日: {holiday_dates}")

    if not holiday_dates:
        print("休刊日データがありません。")
        return

    # カレンダー内の既存予定をすべて取得
    existing_events = service.events().list(calendarId=calendar_id).execute().get('items', [])
    existing_dates = {}
    
    for ev in existing_events:
        start_date = ev.get('start', {}).get('date')
        if start_date:
            existing_dates[start_date] = ev['id']

    # 取得した日付ごとに処理
    for date_str in holiday_dates:
        if date_str in existing_dates:
            print(f"【スキップ】すでに登録されています: {date_str}")
        else:
            # 新規登録（通知はカレンダー側のデフォルト通知を使用）
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
