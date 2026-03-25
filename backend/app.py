from flask import Flask, jsonify, request
from flask_cors import CORS
import redis
import json
from gmail_lib import fetch_emails

app = Flask(__name__)
CORS(app)  # React 프론트엔드와의 통신 허용
            # Allow communication with the React frontend.

# 1. Redis 연결 설정 (Docker로 띄운 기본 설정)
# 1. Configure Redis connection (default settings running in Docker).
# decode_responses=True를 설정해야 데이터를 문자열로 바로 읽을 수 있습니다.
# decode_responses=True lets us read the data directly as strings.
try:
    cache = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
except Exception as e:
    cache = None
    print(f"Redis 연결 실패: {e}")

@app.route('/api/emails', methods=['GET'])
def get_gmail_data():
    try:
        count = int(request.args.get('count', 10))
    except (TypeError, ValueError):
        return jsonify({"error": "count must be an integer."}), 400

    if not 1 <= count <= 50:
        return jsonify({"error": "count must be between 1 and 50."}), 400

    cache_key = f'gmail_cache_{count}'

    # 2. Redis 캐시 확인 (Key 이름: 개수별로 분리)
    # 2. Check the Redis cache (separate key for each count).
    cached_data = None
    if cache:
        try:
            cached_data = cache.get(cache_key)
        except Exception as e:
            print(f"Redis 캐시 조회 실패: {e}")
    
    if cached_data:
        # 캐시에 데이터가 있다면 즉시 반환 (Cache Hit)
        # If cached data exists, return it immediately (cache hit).
        print(f"💡 Redis Cache Hit! count={count} 데이터를 캐시에서 불러옵니다.")
        return jsonify(json.loads(cached_data))

    # 3. 캐시에 데이터가 없다면 (Cache Miss)
    # 3. If there is no cached data (cache miss).
    print(f"🚀 API Calling... Gmail에서 count={count} 데이터를 새로 가져옵니다.")
    try:
        data = fetch_emails(count)
        
        # 4. 가져온 데이터를 Redis에 저장 (SET)
        # 4. Store the fetched data in Redis (SET).
        # setex: 데이터 저장 + 유효기간 설정 (600초 = 10분)
        # setex: save data and set an expiration time (600 seconds = 10 minutes).
        if cache:
            try:
                cache.setex(cache_key, 600, json.dumps(data))
            except Exception as e:
                print(f"Redis 캐시 저장 실패: {e}")
        
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Flask 서버 실행 (포트 5000)
    # Run the Flask server (port 5000).
    app.run(port=5000, debug=True)
