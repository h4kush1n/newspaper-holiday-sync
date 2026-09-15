import os
import json
import re
import datetime
import requests
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

def get_holiday_dates():
    """読売ISの休刊日案内ページから日付を抽出"""
    url = "https://www.yomiuri-is.co.jp/blog/kyukan/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    dates = []
    current_year = datetime.datetime.now().year
    target_years = [current_year, current_year + 1]
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = 'utf-8' # 日本語エンコーディングを明示
        text = res.text
        
        # 1. HTMLタグを除去したプレーンテキストを作成
        soup = BeautifulSoup(text, 'html.parser')
        plain_text = soup.get_text()
        
        # 2. 「2026年10月13日」や「2026年 10月 13日」形式を抽出
        for year in target_years:
            # 年・月・日を柔軟に拾うパターン
            pattern = rf'{year}\s*年\s*(\d{{1,2}})\s*月\s*(\d{{1,2}})\s*日'
            matches = re.findall(pattern, plain_text)
            for m, d in matches:
                date_str = f"{year}-{int(m):02d}-{int(d):02d}"
                if date_str not in dates:
                    dates.append(date_str)

    except Exception as e:
        print(f"Webスクレイピング中にエラーが発生しました: {e}")
        
    return sorted(dates)

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
    print(f"検出された休刊日リスト ({len(holiday_dates)}件): {holiday_dates}")

    if not holiday_dates:
        print("警告: 休刊日の日付が1件も検出されませんでした。")
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
                'transparency': 'transparent', # カレンダーの予定あり/なしを「フリー」に設定
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        # 終日イベントの場合、当日AM 0:00から400分後（＝朝 6:40）にポップアップ通知
                        {'method': 'popup', 'minutes': 400}
                    ]
                }
            }
            created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
            print(f"【新規登録】 {date_str} (通知: 当日 6:40)")
        else:
            print(f"【スキップ（登録済み）】 {date_str}")

if __name__ == "__main__":
    main()
