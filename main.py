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

def parse_dates_from_text(text, target_years):
    """テキストから年・月・日のパターンを正規表現で抽出"""
    dates = []
    for year in target_years:
        # パターン1: 2026年10月13日 / 2026年 10月 13日
        pattern1 = rf'{year}\s*年\s*(\d{{1,2}})\s*月\s*(\d{{1,2}})\s*日'
        matches1 = re.findall(pattern1, text)
        for m, d in matches1:
            date_str = f"{year}-{int(m):02d}-{int(d):02d}"
            if date_str not in dates:
                dates.append(date_str)
                
        # パターン2: 10/13 または 10月13日（年がヘッダー等にある場合）
        # ※誤検知を防ぐため「月休刊日」などの文脈から抽出
    return dates

def fetch_from_orikomi_try(target_years):
    """オリコミトライ (休刊日案内) からの取得"""
    url = "https://www.orikomi-try.com/kyukan/"
    dates = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        dates = parse_dates_from_text(text, target_years)
    except Exception as e:
        print(f"オリコミトライからの取得失敗: {e}")
    return dates

def fetch_from_yomiuri_is(target_years):
    """読売IS からの取得（予備）"""
    url = "https://www.yomiuri-is.co.jp/blog/kyukan/"
    dates = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        dates = parse_dates_from_text(text, target_years)
    except Exception as e:
        print(f"読売ISからの取得失敗: {e}")
    return dates

def fetch_from_sanin_sc(target_years):
    """山陰中央新報SC からの取得（予備）"""
    url = "https://www.dailysanin.co.jp/holiday"
    dates = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        dates = parse_dates_from_text(text, target_years)
    except Exception as e:
        print(f"山陰中央新報SCからの取得失敗: {e}")
    return dates

def get_holiday_dates():
    current_year = datetime.datetime.now().year
    target_years = [current_year, current_year + 1]
    
    # 複数ソースを順番に試行（最初に成功したものを採用）
    sources = [
        ("オリコミトライ", fetch_from_orikomi_try),
        ("読売IS", fetch_from_yomiuri_is),
        ("山陰中央新報SC", fetch_from_sanin_sc)
    ]
    
    for name, fetch_func in sources:
        print(f"ソース [{name}] から休刊日データを試行中...")
        dates = fetch_func(target_years)
        if dates:
            print(f"成功: [{name}] から {len(dates)} 件の日付を取得しました。")
            return sorted(dates)
            
    return []

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
        print("エラー: 全てのソースから休刊日の日付が検出されませんでした。")
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
                'transparency': 'transparent',  # カレンダーの予定あり/なしを「フリー」に設定
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
