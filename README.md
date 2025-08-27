# 💳 신용카드 추천 LLM 서비스

사용자의 월 소비 패턴을 분석하여 최적의 신용카드 조합(2-3개)을 추천하고, 구체적인 사용 방법과 절약 금액을 계산하는 AI 서비스입니다.

## 🚀 주요 기능

- **AI 기반 카드 추천**: LlamaIndex와 OpenAI GPT-4를 활용한 지능형 추천
- **최적화 알고리즘**: 카드 조합 최적화 및 카테고리별 할당
- **정확한 혜택 계산**: Function Calling을 통한 정확한 혜택 및 ROI 계산
- **벡터 검색**: ChromaDB를 활용한 카드 정보 벡터 인덱싱
- **REST API**: FastAPI 기반의 직관적인 API 인터페이스

## 🛠️ 기술 스택

- **Backend**: FastAPI
- **LLM Framework**: LlamaIndex
- **LLM**: OpenAI GPT-4
- **Vector DB**: ChromaDB (로컬 파일 저장)
- **Data Storage**: JSON 파일
- **Python**: 3.10+

## 📁 프로젝트 구조

```
credit-card-recommender/
├── main.py              # FastAPI 메인 애플리케이션
├── models.py            # Pydantic 데이터 모델
├── llm_service.py       # LlamaIndex LLM 서비스
├── optimizer.py         # 카드 최적화 알고리즘
├── data/
│   └── cards.json       # 신용카드 데이터
├── requirements.txt     # Python 의존성
├── env_example.txt      # 환경 변수 예시
└── README.md           # 프로젝트 문서
```

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 저장소 클론
git clone <repository-url>
cd credit-card-recommender

# Python 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. OpenAI API 키 설정

```bash
# .env 파일 생성
cp env_example.txt .env

# .env 파일에 실제 OpenAI API 키 입력
OPENAI_API_KEY=your_actual_openai_api_key_here
```

### 3. 서비스 실행

```bash
python main.py
```

서비스가 `http://localhost:8000`에서 실행됩니다.

## 📖 API 사용법

### 기본 엔드포인트

- `GET /`: 서비스 정보
- `GET /health`: 서비스 상태 확인
- `GET /cards`: 사용 가능한 카드 목록
- `POST /recommend`: 신용카드 추천
- `POST /test`: 테스트용 추천 요청

### 카드 추천 API

**POST** `/recommend`

**요청 예시:**
```json
{
  "monthly_spending": 1000000,
  "spending_breakdown": {
    "온라인쇼핑": 300000,
    "마트": 200000,
    "편의점": 100000,
    "카페": 50000,
    "대중교통": 100000,
    "주유": 150000,
    "배달앱": 100000
  },
  "subscriptions": ["넷플릭스", "유튜브프리미엄", "스포티파이"]
}
```

**응답 예시:**
```json
{
  "recommendation_text": "💳 신용카드 추천 결과...",
  "selected_cards": [...],
  "monthly_savings": 34000,
  "annual_savings": 408000,
  "usage_strategy": "각 카드별 사용 전략...",
  "total_annual_fee": 60000,
  "net_annual_savings": 348000
}
```

## 🔧 카드 데이터 구조

`data/cards.json` 파일에 신용카드 정보가 저장됩니다:

```json
{
  "cards": [
    {
      "id": "card_001",
      "name": "KB국민 마이포인트카드",
      "bank": "KB국민카드",
      "annual_fee": 20000,
      "benefits": [
        {
          "category": "간편결제",
          "type": "cashback",
          "rate": 5.0,
          "monthly_limit": 10000,
          "min_purchase": 10000
        }
      ],
      "conditions": {
        "prev_month_min": 300000,
        "benefit_cap": 20000
      }
    }
  ]
}
```

## 🧠 최적화 알고리즘

### 1. 카드 조합 최적화
- 2-3개 카드 조합 시도
- 모든 가능한 조합의 ROI 계산
- 최고 점수 조합 선택

### 2. 카테고리 할당
- 혜택률 순으로 카테고리 정렬
- 각 카드의 월 한도 및 최소 구매 조건 확인
- 최적의 카테고리-카드 매칭

### 3. ROI 계산
- 연 혜택 - 연회비 = 순혜택
- (순혜택 / 연회비) × 100 = ROI
- 수익성 있는 조합 우선 선택

## 🎯 사용 예시

### 테스트 실행
```bash
# 브라우저에서 API 문서 확인
http://localhost:8000/docs

# 테스트 요청 실행
curl -X POST "http://localhost:8000/test"
```

### 실제 추천 요청
```bash
curl -X POST "http://localhost:8000/recommend" \
  -H "Content-Type: application/json" \
  -d '{
    "monthly_spending": 800000,
    "spending_breakdown": {
      "온라인쇼핑": 200000,
      "마트": 150000,
      "카페": 30000
    },
    "subscriptions": ["넷플릭스"]
  }'
```

## 🔍 주요 특징

### 1. 지능형 분석
- LLM을 통한 소비 패턴 분석
- 벡터 검색을 통한 카드 정보 검색
- Function Calling을 통한 정확한 계산

### 2. 실용적 추천
- 전월 실적 조건 고려
- 월 한도 및 최소 구매 금액 확인
- 연회비 대비 실제 혜택 계산

### 3. 확장 가능한 구조
- 새로운 카드 추가 용이
- 카테고리 및 혜택 유형 확장 가능
- 다양한 LLM 모델 지원

## 🚨 주의사항

1. **OpenAI API 키**: 실제 사용을 위해서는 유효한 OpenAI API 키가 필요합니다.
2. **카드 정보**: `cards.json`의 카드 정보는 예시이며, 실제 사용 시 최신 정보로 업데이트해야 합니다.
3. **혜택 계산**: 실제 카드 혜택과 다를 수 있으므로 참고용으로만 사용하세요.

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 📞 문의

프로젝트에 대한 문의사항이 있으시면 이슈를 생성해주세요.

---

**💡 팁**: API 문서(`/docs`)를 통해 모든 엔드포인트를 테스트해볼 수 있습니다!
