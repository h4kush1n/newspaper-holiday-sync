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
    """テキストから指定年の「M月D日」形式を抽出"""
    dates = []
    pattern = r'(\d{1,2})\s*月\s*(\d{1,2})\s*日'
    matches = re.findall(pattern, text)
    
    for m, d in matches:
        m_int, d_int = int(m), int(d)
        if 1 <= m_int <= 12 and 1 <= d_int <= 31:
            date_str = f"{year}-{m_int:02d}-{d_int:02d}"
            if date_str not in dates:
                dates.append(date_str)
                
    return dates

def fetch_national_holiday_dates(year):
    """全国統一新聞休刊日（大手ネットワーク）から取得"""
    url = "https://www.orikomi.tv/price/kyukan.php" # 全国主要紙統一休刊日案内
    dates = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        
        year_str = f"{year}年"
        if year_str in text:
            sub_text = text.split(year_str)[-1]
            next_year_str = f"{year + 1}年"
            if next_year_str in sub_text:
                sub_text = sub_text.split(next_year_str)[0]
                
            dates = parse_dates_from_text(sub_text, year)
            print(f"[{year}年 休刊日取得成功]: {dates}")
    except Exception as e:
        print(f"{year}年の取得失敗: {e}")
    return dates

def get_holiday_dates():
    current_year = datetime.datetime.now().year
    all_dates = []
    
    # 今年と翌年の2年分を取得
    for y in [current_year, current_year + 1]:
        dates = fetch_national_holiday_dates(y)
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

    print("全国統一 新聞休刊日データを取得中...")
    holiday_dates = get_holiday_dates()
    print(f"\n=== 取得完了リスト ({len(holiday_dates)}件) ===")
    print(holiday_dates)

    if not holiday_dates:
        print("エラー: 休刊日データがありません。")
        return

    # カレンダー内の既存予定を取得して重複チェック
    existing_events = service.events().list(calendarId=calendar_id).execute().get('items', [])
    existing_dates = {}
    
    for ev in existing_events:
        start_date = ev.get('start', {}).get('date')
        if start_date:
            existing_dates[start_date] = ev['id']

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
