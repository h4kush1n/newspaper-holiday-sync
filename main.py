import os
import json
import re
import datetime
import requests
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

def get_holiday_dates():
    """読売IS等の休刊日案内ページから日付を抽出（フォールバック付き）"""
    url = "https://www.yomiuri-is.co.jp/blog/kyukan/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    dates = []
    current_year = datetime.datetime.now().year
    target_years = [current_year, current_year + 1]
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        
        # 「X月Y日」パターンを正規表現で検出
        # 例: 2026年 10月13日(火) や 10月13日 など
        for year in target_years:
            # 年ごとのブロック処理またはテキスト全体からの年・月日マッチング
            pattern = rf'{year}\s*年\s*(\d{{1,2}})\s*月\s*(\d{{1,2}})\s*日'
            matches = re.findall(pattern, text)
            for m, d in matches:
                date_str = f"{year}-{int(m):02d}-{int(d):02d}"
                if date_str not in dates:
                    dates.append(date_str)
                    
    except Exception as e:
        print(f"Webスクレイピング中にエラーが発生しました: {e}")
        
    return sorted(dates)

def main():
    # GitHub Secrets から環境変数を取得
    sa_key_json = os.environ.get("GCP_SA_KEY")
    calendar_id = os.environ.get("CALENDAR_ID")

    if not sa_key_json or not calendar_id:
        raise ValueError("環境変数 GCP_SA_KEY または CALENDAR_ID が設定されていません。")

    # JSON文字から認証オブジェクトを構築
    key_dict = json.loads(sa_key_json)
    scopes = ['https://www.googleapis.com/auth/calendar']
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    service = build('calendar', 'v3', credentials=creds)

    print("休刊日データを取得中...")
    holiday_dates = get_holiday_dates()
    print(f"検出された休刊日リスト ({len(holiday_dates)}件): {holiday_dates}")

    for date_str in holiday_dates:
        # 既存登録の重複チェック
        start_time = f"{date_str}T00:00:00Z"
        end_time = f"{date_str}T23:59:59Z"
        
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True
        ).execute()
        
        events = events_result.get('items', [])
        
        # 同日にすでに登録がなければ新規追加
        if not events:
            event = {
                'summary': '新聞休刊日',
                'start': {'date': date_str},
                'end': {'date': date_str},
                'transparency': 'transparent'  # 予定あり/なしを「フリー」に設定
            }
            created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
            print(f"【新規登録】 {date_str}")
        else:
            print(f"【スキップ（登録済み）】 {date_str}")

if __name__ == "__main__":
    main()
