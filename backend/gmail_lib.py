import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 읽기 전용 권한 설정
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_service():
    creds = None
    # 이전에 로그인한 기록(token.json)이 있는지 확인
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # 기록이 없거나 만료되었다면 새로 로그인 프로세스 진행
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # credentials.json 파일을 읽어 인증창 띄움
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # 로그인 정보를 token.json에 저장 (다음 실행 시 자동 로그인)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def fetch_emails():
    service = get_service()
    # Primary 카테고리 메일만 최대 10개 필터링
    results = service.users().messages().list(userId='me', q='category:primary', maxResults=10).execute()
    messages = results.get('messages', [])
    
    parsed_emails = []
    for msg in messages:
        # 각 메일의 상세 정보(본문, 헤더 등) 가져오기
        detail = service.users().messages().get(userId='me', id=msg['id']).execute()
        headers = detail['payload'].get('headers', [])
        
        # 제목(Subject) 추출
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '제목 없음')
        
        # 첨부파일 이름 리스트 추출
        attachments = []
        if 'parts' in detail['payload']:
            for part in detail['payload']['parts']:
                if part.get('filename'):
                    attachments.append(part['filename'])
        
        parsed_emails.append({
            "id": msg['id'],
            "subject": subject,
            "snippet": detail.get('snippet', ''), # 메일 본문 앞부분 요약
            "attachments": attachments
        })
    return parsed_emails