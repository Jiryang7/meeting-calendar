import time
import threading
import requests
import gspread
from flask import Flask, request, jsonify
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from datetime import datetime

app = Flask(__name__)

TELEGRAM_TOKEN = '8254324146:AAFQFiNn_fQDiySoda1S-v1P7jhn5q4J7tE'
CHAT_ID = '-1003931914339'
SPREADSHEET_NAME = '시트이름'       # ← 구글 시트 파일명으로 변경하세요
APPS_SCRIPT_URL = ''               # ← 기존 앱스크립트 웹앱 URL 입력하세요

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


def get_creds():
    creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    creds.refresh(Request())
    return creds

def get_spreadsheet():
    creds = get_creds()
    client = gspread.authorize(creds)
    return client.open(SPREADSHEET_NAME)

def send_message(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text}
    )

def generate_and_send_pdf(serial_number):
    try:
        creds = get_creds()
        ss = get_spreadsheet()
        result_sheet = ss.worksheet('결과지리뉴얼')
        result_sheet.update('T1', serial_number)
        time.sleep(5)

        ss_id = ss.id
        sheet_id = result_sheet.id
        url = (
            f"https://docs.google.com/spreadsheets/d/{ss_id}/export"
            f"?format=pdf&gid={sheet_id}&fitw=true&size=A4&portrait=true"
        )
        pdf_bytes = requests.get(
            url, headers={"Authorization": f"Bearer {creds.token}"}
        ).content

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            files={"document": (f"결과지_{serial_number}.pdf", pdf_bytes, "application/pdf")},
            data={"chat_id": CHAT_ID, "caption": f"📋 결과지 - CODE {serial_number}"}
        )
    except Exception as e:
        print(f"PDF 생성/전송 오류: {e}")


@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)

        if not data or 'name' not in data:
            return jsonify({'result': 'ok'})

        # 1. 구글 시트에 저장 (gspread 직접 저장)
        ss = get_spreadsheet()
        sheet = ss.get_worksheet(0)
        serial_number = len(sheet.get_all_values()) + 1

        row = [
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            data.get('name'),
            data.get('age'),
            data.get('phone'),
            data.get('mbti'),
            data.get('job'),
            data.get('purpose'),
            *data.get('answers', []),
            serial_number
        ]
        sheet.append_row(row)

        # 2. 기존 앱스크립트로도 전달 (앱스크립트 시트에도 저장)
        if APPS_SCRIPT_URL:
            try:
                requests.post(APPS_SCRIPT_URL, json=data, timeout=10)
            except Exception as e:
                print(f"앱스크립트 전달 오류: {e}")

        # 3. 텔레그램 알림
        try:
            send_message(
                f"📋 새 검사결과 도착!\n\n"
                f"이름: {data.get('name')}\n"
                f"나이: {data.get('age')}\n"
                f"연락처: {data.get('phone')}\n"
                f"일련번호: {serial_number}\n\n"
                f"PDF 자동 생성 중..."
            )
        except Exception as e:
            print(f"텔레그램 알림 오류: {e}")

        # 4. PDF 생성 & 전송 (백그라운드 - 웹훅 응답 먼저 반환)
        threading.Thread(
            target=generate_and_send_pdf, args=(serial_number,), daemon=True
        ).start()

        return jsonify({'result': 'success', 'serial_number': serial_number})

    except Exception as e:
        return jsonify({'result': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    print("서버 시작 - 엔드포인트: http://<서버주소>/webhook")
    app.run(host='0.0.0.0', port=5000)
