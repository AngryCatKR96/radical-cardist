# 💳 카데몽 (Cardemon)

카데몽은 사용자의 **자연어 소비 패턴**을 분석하여
**가장 유리한 신용/체크카드 1장**을 추천하는 AI 기반 카드 추천 서비스입니다.

복잡한 카드 혜택(전월실적, 할인한도, 가맹점 제한, 조건부 혜택)을
정량적으로 해석하여 **월·연 절약 금액 기준으로 최적의 카드**를 도출합니다.

export ADMIN_API_KEY="(너의 키)"


---

## 핵심 특징

* **자연어 입력 지원**
  예: “마트에서 월 30만원 쓰고, 넷플릭스 구독 중입니다”

* **실제 카드 데이터 기반**
  카드고릴라 API를 통해 최신 카드 정보 동기화

* **정량적 혜택 계산**
  감각적 추천이 아닌 실제 월·연 절약 금액 계산

* **단종 카드 자동 제외**
  발급 중단 카드는 수집·검색·추천 전 과정에서 제외

---

## 빠른 시작 (Quickstart)

### 1. 저장소 클론 및 환경 설정

```bash
git clone <repository-url>
cd radical-cardist

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

### 2. 환경 변수 설정

`.env.example`을 참고하여 `.env` 파일을 생성합니다. 

---

### 3. 서버 실행

```bash
python main.py
```

* API 서버: `http://localhost:8000`
* Swagger 문서: `http://localhost:8000/docs`

---

### 4. 카드 데이터 초기 동기화 (필수)

```bash
./script/sync_cards.sh
``` 

## 전체 아키텍처 요약

### 추천 파이프라인

1. **Input Parser (LLM)**
   자연어 입력 → 구조화된 UserIntent(JSON)

2. **Vector Search (RAG)**
   MongoDB Vector Search 기반 카드 후보 검색

3. **Benefit Analyzer (LLM + 규칙)**
   카드 혜택 해석 및 월·연 절약액 계산

4. **Recommender (Algorithm)**
   (연 절약액 - 연회비) + 커버리지 - 패널티 기준 최종 카드 선택

5. **Response Generator**
   사용자 응답용 최종 JSON 생성

> 상세 흐름은 `diagram.png` 참고

---

## 프로젝트 구조

```text
radical-cardist/
├── main.py                  # FastAPI 엔트리 포인트
├── agents/                  # Parser / Analyzer / Recommender
├── vector_store/            # 임베딩 생성 및 검색
├── database/                # MongoDB 연결 및 헬스체크
├── data_collection/         # 카드고릴라 수집 로직
├── security/                # 인증 / 레이트리밋 / 로깅
├── script/                  # 수집·임베딩 CLI
├── test/                    # 테스트 코드
├── utils/                   # 공용 유틸
├── frontend/                # Next.js 관리자 UI
└── README.md
```

---

## 데이터 동기화 구조 (운영 관점)

### 1단계. 카드 데이터 수집 (fetch)

* 카드고릴라 API 호출
* 불필요한 필드 제거 후 **압축 컨텍스트 JSON** 생성
* OpenAI 크레딧 사용 안 함

```bash
python script/fetch_cardgorilla_range.py
python script/fetch_cardgorilla_range.py --start 1000 --end 6000
python script/fetch_cardgorilla_range.py --card-ids 2862,1357 --overwrite
```

저장 위치:

```
data/cache/ctx/{card_id}.json
```

---

### 2단계. 임베딩 생성 (embed)

* JSON → 문서 분해 (summary / benefit / notes)
* OpenAI `text-embedding-3-small` 사용
* MongoDB Vector Store 저장

```bash
python script/embed_mongodb.py
python script/embed_mongodb.py --card-ids 2862,1357
```

---

### 통합 실행

```bash
POST /admin/cards/sync
```

---

## API 사용법

### 사용자 API

#### POST `/recommend/natural-language`

```bash
curl -X POST "http://localhost:8000/recommend/natural-language" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "마트 30만원, OTT 구독, 간편결제 자주 사용. 연회비 2만원 이하"
  }'
```

---

#### POST `/recommend/structured`

구조화된 UserIntent를 직접 전달하여 추천 수행

---

### 관리자 API

| 기능       | 엔드포인트                         |
| -------- | ----------------------------- |
| 카드 수집    | `POST /admin/cards/fetch`     |
| 임베딩 생성   | `POST /admin/cards/embed`     |
| 통합 동기화   | `POST /admin/cards/sync`      |
| 카드 1개 갱신 | `POST /admin/cards/{card_id}` |
| 통계 조회    | `GET /admin/cards/stats`      |
| 전체 초기화   | `DELETE /admin/cards/reset`   |

---

## 운영 규칙 및 주의사항

* **단종 카드 자동 제외**
  `is_discon = true` 카드는 수집 단계에서 제외

* **Rate Limiting**
  초당 5회 / 분당 60회
  429 발생 시 지수 백오프 재시도

* **에러 처리 정책**

  * 네트워크/타임아웃: 최대 3회 재시도
  * 404: 스킵 후 로그 기록
  * 5xx: 재시도 후 실패 시 오류 기록

---

## 참고 자료

* 카드고릴라 API
  [https://api.card-gorilla.com:8080/v1/cards/{card_id}](https://api.card-gorilla.com:8080/v1/cards/{card_id})

* OpenAI API
  [https://platform.openai.com/docs](https://platform.openai.com/docs) 