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
    """テキストから指定年の「M月D日」または「MM-DD」形式を正規表現で集計"""
    dates = []
    
    # パターン1: 「2026年休刊日のご案内」などのヘッダー配下にある「X月 Y日」を柔軟に捕捉
    # 例: 1月 2日（金）、10月 13日（火）など
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
    """山陰中央新報SC (https://www.dailysanin.co.jp/holiday) からの取得"""
    url = "https://www.dailysanin.co.jp/holiday"
    dates = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        
        # 該当年のセクションが含まれているか確認
        year_str = f"{year}年"
        if year_str in text:
            # 該当年のテキストブロック以降をパース
            sub_text = text.split(year_str)[-1]
            dates = parse_dates_from_text(sub_text, year)
            print(f"[山陰中央新報SC] {year}年の抽出結果: {dates}")
    except Exception as e:
        print(f"山陰中央新報SCからの取得失敗: {e}")
    return dates

def fetch_from_yomiuri_is(year):
    """読売IS ブログからの取得"""
    url = "https://www.yomiuri-is.co.jp/blog/kyukan/"
    dates = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        
        year_str = f"{year}年"
        if year_str in text:
            sub_text = text.split(year_str)[-1]
            dates = parse_dates_from_text(sub_text, year)
            print(f"[読売IS] {year}年の抽出結果: {dates}")
    except Exception as e:
        print(f"読売ISからの取得失敗: {e}")
    return dates

def get_holiday_dates():
    current_year = datetime.datetime.now().year
    
    # 当年と翌年の休刊日を取得
    all_dates = []
    for y in [current_year, current_year + 1]:
        dates = fetch_from_sanin_sc(y)
        if not dates:
            dates = fetch_from_yomiuri_is(y)
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
    print(f"\n=== 最終検出日付リスト ({len(holiday_dates)}件) ===")
    print(holiday_dates)

    if not holiday_dates:
        print("エラー: 休刊日の日付が検出されませんでした。")
        return

    for date_str in holiday_dates:
        start_time = f"{date_str}T00:00:00Z"
        end_time = f"{date_str}T23:59:59Z"
        
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            event = {
                'summary': '新聞休刊日',
                'start': {'date': date_str},
                'end': {'date': date_str},
                'transparency': 'transparent',
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 400}  # 当日 朝6:40に通知
                    ]
                }
            }
            created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
            print(f"【新規登録】 {date_str} (通知: 当日 6:40)")
        else:
            print(f"【スキップ（登録済み）】 {date_str}")

if __name__ == "__main__":
    main()
