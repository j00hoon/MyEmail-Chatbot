from flask import Flask, jsonify
from flask_cors import CORS
import redis
import json
from gmail_lib import fetch_emails

app = Flask(__name__)
CORS(app) # React 프론트엔드와의 통신 허용

# 1. Redis 연결 설정 (Docker로 띄운 기본 설정)
# decode_responses=True를 설정해야 데이터를 문자열로 바로 읽을 수 있습니다.
try:
    cache = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
except Exception as e:
    print(f"Redis 연결 실패: {e}")

@app.route('/api/emails', methods=['GET'])
def get_gmail_data():
    # 2. Redis 캐시 확인 (Key 이름: 'gmail_cache')
    cached_data = cache.get('gmail_cache')
    
    if cached_data:
        # 캐시에 데이터가 있다면 즉시 반환 (Cache Hit)
        print("💡 Redis Cache Hit! 데이터를 캐시에서 불러옵니다.")
        return jsonify(json.loads(cached_data))

    # 3. 캐시에 데이터가 없다면 (Cache Miss)
    print("🚀 API Calling... Gmail에서 데이터를 새로 가져옵니다.")
    try:
        data = fetch_emails()
        
        # 4. 가져온 데이터를 Redis에 저장 (SET)
        # setex: 데이터 저장 + 유효기간 설정 (600초 = 10분)
        cache.setex('gmail_cache', 600, json.dumps(data))
        
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Flask 서버 실행 (포트 5000)
    app.run(port=5000, debug=True)