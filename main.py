import os
import time
from datetime import datetime, timedelta
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# 환경 변수 가져오기
SMARTIX_URL = "https://admin.smartix.co.kr"  # 스마틱스 실제 관리자 주소
SMARTIX_ID = os.environ.get("SMARTIX_ID")
SMARTIX_PW = os.environ.get("SMARTIX_PW")
SPREADSHEET_KEY = os.environ.get("SPREADSHEET_KEY")

DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 조회 날짜 (전일 기준)
yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

def fetch_smartix_excel():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            accept_downloads=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        stealth_sync(page)

        print(f"[{datetime.now()}] 스마틱스 접속 중...")
        page.goto(SMARTIX_URL)
        page.wait_for_load_state("networkidle")

        # 1. 로그인 (휴먼 타입 지연시간 적용)
        page.type("input[name='id']", SMARTIX_ID, delay=100)
        page.type("input[name='password']", SMARTIX_PW, delay=100)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # 2. 예매내역 메뉴 이동
        page.click("text=예매내역")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # 3. 기간 수정 (전일자 설정)
        # ※ 셀렉터는 실제 스마틱스 HTML ID/Class에 맞춰 수정
        page.fill("#startDate", yesterday)
        page.fill("#endDate", yesterday)
        time.sleep(0.5)

        # 4. 검색 버튼 클릭
        page.click("button:has-text('검색')")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # 5. 엑셀 다운로드
        print("엑셀 다운로드 진행 중...")
        with page.expect_download() as download_info:
            page.click("button:has-text('엑셀')")
        
        download = download_info.value
        save_path = os.path.join(DOWNLOAD_DIR, f"sales_{yesterday}.xlsx")
        download.save_as(save_path)
        
        browser.close()
        return save_path

def process_and_stack_to_gsheet(excel_path):
    print("데이터 정제 작업 시작...")
    # 상위 7행 삭제 (8번째 행부터 데이터를 읽음)
    df = pd.read_excel(excel_path, skiprows=7)
    df = df.dropna(how='all').fillna('')
    
    data_to_append = df.values.tolist()
    if not data_to_append:
        print("추가할 데이터가 없습니다.")
        return

    # 구글 시트 연동 및 Append
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    client = gspread.authorize(creds)

    doc = client.open_by_key(SPREADSHEET_KEY)
    sheet = doc.sheet1  # 첫 번째 시트

    sheet.append_rows(data_to_append, value_input_option='USER_ENTERED')
    print(f"성공: {len(data_to_append)}건의 데이터가 구글 시트 하단에 누적되었습니다.")

if __name__ == "__main__":
    file_path = fetch_smartix_excel()
    process_and_stack_to_gsheet(file_path)
