# 💳 신용카드 추천 (RAG + Agentic) 서비스

사용자의 자연어 소비 패턴을 분석하여 최적의 신용카드 1장을 추천하는 AI 서비스입니다. 카드고릴라에서 실시간으로 카드 정보를 수집하고, RAG(Retrieval-Augmented Generation)와 Agentic 워크플로우를 통해 사용자에게 딱 맞는 카드를 찾아드립니다.

## 🎯 이 서비스가 특별한 이유

신용카드 혜택은 매우 복잡합니다. "전월실적 30만원 이상이면 10% 할인"처럼 단순한 규칙이 아니라, 시간대별 할인, 가맹점 제한, 복잡한 조건들이 얽혀있죠. 이 서비스는:

- **자연어로 소비 패턴 입력**: "마트에서 월 30만원 쓰고, 넷플릭스 구독 중이에요"처럼 자유롭게 말씀하시면 됩니다
- **실제 카드 데이터 활용**: 카드고릴라에서 최신 카드 정보를 가져와 정확한 추천을 제공합니다
- **정량적 혜택 계산**: 단순히 "이 카드 좋아요"가 아니라, 실제로 얼마나 절약할 수 있는지 계산해드립니다
- **단종 카드 자동 제외**: 더 이상 발급되지 않는 카드는 자동으로 제외합니다

## 🚀 주요 기능

### 1. 자연어 입력 파싱
사용자가 자유롭게 입력한 소비 패턴을 LLM이 구조화된 데이터로 변환합니다. 예를 들어 "마트에서 주로 장보고, 카페 자주 가요"를 입력하면, 카테고리별 지출 금액과 선호도를 자동으로 추출합니다.

### 2. 카드고릴라 API 연동
실시간으로 최신 카드 정보를 수집합니다. 단종된 카드(`is_discon: true`)는 자동으로 제외하여 정확한 추천을 보장합니다.

### 3. RAG 기반 검색
카드 정보를 벡터로 변환하여 의미론적 검색을 수행합니다. 단순 키워드 매칭이 아니라, 사용자의 소비 패턴과 카드 혜택의 의미를 이해하여 관련 카드를 찾습니다.

### 4. 정량적 혜택 분석
각 후보 카드에 대해 실제 절약 금액을 계산합니다. 전월실적 조건, 월 한도, 제외 항목 등을 모두 고려하여 정확한 수치를 제공합니다.

### 5. 최종 1장 추천
여러 후보 중에서 사용자에게 가장 유리한 카드 1장을 선택합니다. 단순히 혜택률만 보는 것이 아니라, 연회비, 전월실적 조건, 사용자 선호도 등을 종합적으로 고려합니다.

## 🛠️ 기술 스택

- **Backend**: FastAPI - 빠르고 현대적인 Python 웹 프레임워크
- **LLM**: OpenAI GPT-4 - 자연어 이해 및 구조화를 위한 대규모 언어 모델
- **Vector DB**: ChromaDB - 로컬 파일 기반 벡터 데이터베이스 (별도 서버 불필요)
- **Storage**: 파일 기반 JSON - 간단하고 안정적인 데이터 저장
- **Python**: 3.10+ - 최신 Python 기능 활용

## 📁 프로젝트 구조

```
radical-cardist/
├── main.py                          # FastAPI 메인 애플리케이션
├── data_collection/
│   ├── card_gorilla_client.py       # 카드고릴라 API 연동 및 데이터 수집
│   └── data_parser.py               # 원본 데이터를 압축 컨텍스트로 변환
├── vector_store/
│   ├── embeddings.py                # 카드 정보를 문서로 분해하고 임베딩 생성
│   └── vector_store.py              # 벡터 검색 및 카드 단위 집계
├── agents/
│   ├── input_parser.py              # 자연어 입력을 구조화된 데이터로 변환
│   ├── benefit_analyzer.py          # 카드 혜택을 정량적으로 분석
│   ├── recommender.py               # 최종 1장 선택 로직
│   └── response_generator.py        # 사용자 친화적인 추천 텍스트 생성
├── data/
│   └── cache/
│       └── ctx/{card_id}.json       # 압축 컨텍스트 저장소
├── chroma_db/                       # ChromaDB 벡터 데이터베이스 저장소
├── requirements.txt                 # Python 패키지 의존성
├── .env                             # 환경 변수 (OPENAI_API_KEY 등)
└── README.md                        # 이 문서
```

## ⚙️ 설치 및 실행

### 1단계: 저장소 클론 및 가상환경 설정

```bash
# 저장소 클론
git clone <repository-url>
cd radical-cardist

# 가상환경 생성 및 활성화
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 2단계: 의존성 설치

```bash
pip install -r requirements.txt
```

필요한 주요 패키지:
- `fastapi`: 웹 프레임워크
- `openai`: OpenAI API 클라이언트
- `chromadb`: 벡터 데이터베이스
- `httpx`: 비동기 HTTP 클라이언트
- `pydantic`: 데이터 검증

### 3단계: 환경 변수 설정

`.env` 파일을 생성하고 OpenAI API 키를 입력하세요:

```bash
# .env 파일 생성
echo "OPENAI_API_KEY=your_actual_openai_api_key_here" > .env
```

또는 텍스트 에디터로 직접 생성:

```
OPENAI_API_KEY=sk-...
```

### 4단계: 서비스 실행

```bash
python main.py
```

서비스가 `http://localhost:8000`에서 실행됩니다.

### 5단계: 초기 데이터 동기화 ⚠️ 필수

**서비스를 실행한 후, 반드시 카드 데이터를 동기화해야 합니다!**

#### 방법 A) FastAPI 관리자 API 사용

```bash
# 전체 카드 동기화 (fetch + embed)
curl -X POST "http://localhost:8000/admin/cards/sync"

# 동기화 상태 확인
curl http://localhost:8000/admin/cards/stats
```

선택적으로 특정 카드만 테스트할 수도 있습니다.

```bash
# 단일 카드만 즉시 동기화
curl -X POST "http://localhost:8000/admin/cards/2862"
```

#### 방법 B) CLI 스크립트 사용 (서버 미실행 상태에서도 가능)

1. **카드 데이터 수집** – 카드고릴라 → JSON 캐시  
   ```bash
   # 기본 범위 1~4000, 단종/미존재 카드는 script/skipped_cards.json에 기록되며 이 카드들에 대한 스크래핑은 건너뜁니다.
   python script/fetch_cardgorilla_range.py 
   # 커스텀 범위 1000 ~ 6000도 가능합니다.
   python script/fetch_cardgorilla_range.py --start 1000 --end 6000
   # 특정 카드만
   python script/fetch_cardgorilla_range.py --card-ids 2862,1357 --overwrite
   ```
   - 재실행 시 `script/skipped_cards.json`을 참고하여 이미 단종/404인 카드는 자동으로 건너뜁니다.
   - JSON은 `data/cache/ctx/{card_id}.json`에 저장되며, 이후 대화 테스트 전에도 이 스크립트를 돌려 최신 데이터를 확보할 수 있습니다.

2. **임베딩 생성** – JSON → ChromaDB (`credit_cards` 컬렉션)  
   ```bash
   # 모든 JSON을 임베딩
   python script/embed_chromadb.py
   # 범위 또는 ID 지정
   python script/embed_chromadb.py --start 1 --end 4000 --overwrite
   python script/embed_chromadb.py --card-ids 2862,1357
   ```
   - `.env`의 `OPENAI_API_KEY`가 필요하며 OpenAI 크레딧이 소모됩니다.
   - FastAPI 서버와 동일한 `vector_store/embeddings.py` 로직을 사용하므로, 서버를 켜기 전에 데이터베이스를 채우고 싶을 때 유용합니다.

> **TIP**: 사용자 대화 플로우를 테스트할 때도 위 두 스크립트를 먼저 실행해 두면, 서버를 재시작하더라도 RAG/Agentic 서비스가 즉시 카드 데이터를 사용할 수 있습니다.

**참고**
- 동기화는 (API든 스크립트든) 카드 수에 따라 시간이 걸릴 수 있습니다.
- 진행 상황은 각각의 터미널 출력에서 확인 가능합니다.
- **동기화가 완료되지 않으면 추천 API가 작동하지 않습니다.**

### 6단계: 서비스 테스트

동기화가 완료된 후 테스트를 실행하세요:

```bash
# 테스트 스크립트 실행
python test_api.py
```

브라우저에서 `http://localhost:8000/docs`에 접속하면 API 문서를 확인하고 대화형으로 테스트할 수 있습니다.

## 🔎 아키텍처 상세 설명

이 서비스는 5단계 파이프라인으로 구성되어 있습니다:

### 1단계: 입력 파서 (LLM Function Calling)
**목적**: 사용자의 자연어 입력을 구조화된 데이터로 변환

사용자가 "마트에서 월 30만원 쓰고, 넷플릭스 구독 중이에요"라고 입력하면, LLM이 이를 다음과 같이 구조화합니다:
- 카테고리별 지출 금액 (마트: 30만원, 구독: 넷플릭스)
- 선호사항 (연회비 상한, 카드 유형 등)
- 검색용 필터 (전월실적 추정치, 연회비 최대값 등)

**왜 LLM을 사용하나요?** 자연어는 매우 다양합니다. "마트에서 장보고", "대형마트 이용", "식료품 구매" 모두 같은 의미일 수 있는데, LLM이 이를 이해하고 표준 카테고리로 매핑합니다.

### 2단계: 벡터 검색 (RAG)
**목적**: 사용자 패턴과 관련된 카드 후보를 찾기

1. **의미 검색**: 사용자 질의를 벡터로 변환하고, 카드 혜택 설명과의 유사도를 계산합니다
2. **메타 필터링**: 연회비, 전월실적 조건 등 구조화된 필터를 적용합니다
3. **카드 단위 집계**: 같은 카드의 여러 혜택이 검색되면, 이를 하나로 묶어 카드 단위 점수를 계산합니다
4. **Top-M 선정**: 점수가 높은 상위 M개(예: 5개) 카드를 후보로 선정합니다

**왜 벡터 검색을 사용하나요?** 카드 혜택 설명은 비정형 텍스트입니다. "간편결제 10% 할인"과 "네이버페이/카카오페이 결제 시 10% 청구할인"은 같은 의미지만 키워드가 다릅니다. 벡터 검색은 의미를 이해하여 이런 경우를 잘 찾아냅니다.

### 3단계: 혜택 분석 (LLM + 규칙)
**목적**: 각 후보 카드에 대해 실제 절약 금액을 계산

LLM이 카드 혜택 설명을 해석하고, 사용자의 실제 지출 패턴과 매칭하여:
- 월 절약액 계산
- 연 절약액 계산
- 주의사항 추출 (전월실적 미충족, 한도 초과 등)
- 카테고리별 절약액 분해

**왜 LLM을 사용하나요?** 카드 혜택 설명은 HTML로 되어있고, 조건이 복잡합니다. "건당 1만원 이상", "월 최대 2만원", "주말에만 적용" 같은 조건을 규칙으로 파싱하기 어렵기 때문에 LLM이 해석합니다.

### 4단계: 최종 선택 (알고리즘)
**목적**: 여러 후보 중 최고의 카드 1장 선택

점수 계산 공식:
```
최종 점수 = (연 절약액 - 연회비) + 커버리지 보너스 - 패널티
```

- **커버리지 보너스**: 사용자 지출 카테고리를 많이 커버할수록 가점
- **패널티**: 전월실적 미충족, 연회비 상한 초과 시 감점

동점일 경우: 연회비 낮은 순 → 전월실적 낮은 순 → 사용자 선호도 순으로 결정

### 5단계: 응답 생성 (LLM)
**목적**: 사용자에게 친절하고 이해하기 쉬운 추천 설명 제공

단순히 "이 카드 추천합니다"가 아니라:
- 왜 이 카드를 추천하는지 (사용자 소비 패턴과의 매칭)
- 어떻게 사용해야 하는지 (구체적인 사용 전략)
- 주의해야 할 점 (전월실적, 한도 등)
- 실제 절약 금액 (월/연 기준)

## 📊 데이터 흐름 상세

### Phase 1: 데이터 수집 및 압축 컨텍스트 생성

#### 1.1 카드고릴라 API 클라이언트

카드고릴라 API에서 카드 정보를 가져옵니다. 

**주요 기능:**
- Rate limiting: API 서버에 부하를 주지 않도록 요청 속도 제한
- 에러 처리: 네트워크 오류, 타임아웃 등에 대한 재시도 로직
- 캐싱: 한 번 가져온 데이터는 파일로 저장하여 재사용
- 단종 카드 제외: `is_discon: true`인 카드는 저장하지 않음

**예시:**
```python
client = CardGorillaClient()
card_data = await client.fetch_card_detail(2862)
# card_data는 원본 API 응답 JSON
```

#### 1.2 압축 컨텍스트 생성

원본 API 응답은 매우 큽니다 (SEO 메타데이터, 관련 글, 이미지 URL 등). LLM에 전달할 때는 필요한 정보만 추출하여 토큰을 절약합니다.

**포함하는 필드:**
- `meta`: 카드 기본 정보 (ID, 이름, 발급사, 유형)
- `conditions`: 전월실적 조건
- `fees`: 연회비 정보
- `hints`: 검색 힌트 (태그, 카테고리 등)
- `benefits_html`: 혜택 설명 (HTML 형태)

**제외하는 필드:**
- SEO 메타데이터
- 관련 글 목록
- 이미지 URL (로고 제외)
- 홍보 문구

**저장 위치:** `data/cache/ctx/{card_id}.json`

### Phase 2: 임베딩 및 벡터 검색

#### 2.1 문서 분해 및 임베딩

하나의 카드는 여러 문서(chunk)로 나뉩니다:

1. **Summary 문서 (1개)**: 카드 전체 요약
   - 예: "MG새마을금고 'MG+ S 하나카드'(Mastercard, 체크카드). 전월실적 30만원 이상, 연회비 17,000원. 간편결제 10% 청구할인, 디지털 구독 최대 50% 청구할인."

2. **Benefit 문서 (N개)**: 카테고리별 혜택 설명
   - 예: "간편결제 혜택: 네이버페이/카카오페이/토스페이 결제 시 10% 청구할인. 건당 1만원 이상."

3. **Notes 문서 (0~1개)**: 유의사항 및 제외 항목
   - 예: "유의사항: 통합할인한도 구간별 제한. 제외 항목: 국세, 지방세, 공과금 등"

각 문서는 OpenAI Embeddings API로 벡터화되어 ChromaDB에 저장됩니다.

**왜 문서를 나누나요?** 
- 하나의 긴 문서보다 여러 작은 문서가 검색 정확도를 높입니다
- 사용자가 "간편결제"에 관심이 있으면, 간편결제 혜택 문서만 검색됩니다
- 카드별로 여러 혜택이 검색되면, 그 카드가 사용자에게 적합하다는 신호입니다

#### 2.2 검색 파이프라인

**단계별 설명:**

1. **의미 검색**: 사용자 질의를 벡터로 변환하고, 유사한 문서를 찾습니다
   - Top-K (예: 50개) 문서를 검색
   - Benefit 문서를 우선적으로 검색 (Summary, Notes는 보조)

2. **카드 단위 그룹화**: 같은 카드의 문서들을 묶습니다
   - 예: 카드 2862의 간편결제 문서, 구독 문서가 모두 검색되면 하나로 묶음

3. **증거 캡**: 각 카드당 상위 2~3개 문서만 사용
   - 사용자 지출 카테고리와 일치하는 Benefit 문서 우선
   - Notes 문서가 있으면 포함
   - Summary는 보조적으로 사용

4. **점수 집계**: 카드 단위 점수를 계산
   ```
   점수 = s1 + 0.6*s2 + 0.3*s3 + 커버리지_보너스 - 패널티
   ```
   - s1, s2, s3: 선택된 문서의 유사도 점수 (내림차순)
   - 커버리지 보너스: 사용자 지출 카테고리와 매칭되는 카테고리 수
   - 패널티: 전월실적 미충족, 연회비 상한 초과 등
   - 정규화: 카드의 총 문서 수로 나누어 길이 편향 보정

5. **Top-M 선정**: 점수 상위 M개(예: 5개) 카드를 후보로 선정

### Phase 3: 입력 파서

사용자의 자연어 입력을 구조화된 데이터로 변환합니다.

**입력 예시:**
```
"저는 직장인이고, 마트에서 월 30만원 정도 쓰고, 
넷플릭스랑 유튜브 프리미엄 구독 중이에요. 
간편결제도 자주 쓰는데 월 20만원 정도예요.
연회비는 2만원 이하면 좋겠고, 체크카드 선호해요."
```

**출력 (UserIntent):**
```json
{
  "spending": {
    "grocery": {"amount": 300000},
    "subscription_video": {
      "amount": 30000,
      "merchants": ["netflix", "youtube"]
    },
    "digital_payment": {"amount": 200000}
  },
  "preferences": {
    "card_count_preference": "1",
    "max_annual_fee": 20000,
    "prefer_types": ["debit"]
  },
  "constraints": {
    "pre_month_spending_estimate": 500000
  },
  "query_text": "마트 30만원, OTT 구독, 간편결제 많이 사용, 연회비 2만원 이하, 체크카드 선호",
  "filters": {
    "annual_fee_max": 20000,
    "pre_month_min_max": 500000,
    "type": "debit"
  }
}
```

**주요 필드 설명:**
- `spending`: 카테고리별 월 지출 금액 (원)
- `preferences`: 사용자 선호사항 (카드 수, 연회비 상한, 카드 유형 등)
- `constraints`: 제약 조건 (전월실적 추정치 등)
- `query_text`: 벡터 검색용 자연어 요약
- `filters`: 메타데이터 필터 (연회비, 전월실적, 카드 유형 등)

### Phase 4: 혜택 분석 및 추천

#### 4.1 혜택 분석

각 후보 카드에 대해 실제 절약 금액을 계산합니다.

**입력:**
- 사용자 소비 패턴 (카테고리별 지출)
- 카드 컨텍스트 (검색된 문서들)

**출력:**
```json
{
  "card_id": 2862,
  "monthly_savings": 18000,
  "annual_savings": 216000,
  "conditions_met": true,
  "warnings": ["통합할인한도 초과 시 혜택 제한"],
  "category_breakdown": {
    "digital_payment": 18000
  }
}
```

**계산 과정:**
1. LLM이 카드 혜택 설명을 해석
2. 사용자 지출 패턴과 매칭
3. 조건 확인 (전월실적, 최소 구매금액 등)
4. 한도 확인 (월 최대 혜택액)
5. 실제 절약액 계산

#### 4.2 최종 선택

여러 후보 중 최고의 카드 1장을 선택합니다.

**점수 계산:**
```python
최종_점수 = (연_절약액 - 연회비) + 커버리지_보너스 - 패널티
```

**예시:**
- 카드 A: 연 절약 21.6만원, 연회비 1.7만원, 커버리지 2, 패널티 0
  - 점수 = (21.6 - 1.7) + 2 - 0 = 19.9 + 2 = 21.9
- 카드 B: 연 절약 18만원, 연회비 1.5만원, 커버리지 1, 패널티 0
  - 점수 = (18 - 1.5) + 1 - 0 = 16.5 + 1 = 17.5

→ 카드 A 선택

#### 4.3 응답 생성

사용자에게 친절하고 이해하기 쉬운 추천 설명을 생성합니다.

**생성되는 내용:**
1. 추천 카드명
2. 추천 이유 (사용자 소비 패턴과의 매칭)
3. 사용 전략 (어떻게 사용해야 최대 혜택인지)
4. 주의사항 (전월실적, 한도, 제외 항목 등)
5. 예상 절약액 (월/연 기준)

## 📡 API 사용법

### 사용자 API

#### POST `/recommend/natural-language`

자연어로 소비 패턴을 입력하면 최적의 카드 1장을 추천받습니다.

**요청:**
```bash
curl -X POST "http://localhost:8000/recommend/natural-language" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "마트 30만원, 넷플릭스/유튜브 구독, 간편결제 자주 씀. 연회비 2만원 이하, 체크카드 선호."
  }'
```

**응답:**
```json
{
  "card": {
    "id": "2862",
    "name": "MG+ S 하나카드",
    "brand": "MG새마을금고",
    "annual_fee": "국내전용 10,000원 / 해외겸용 17,000원",
    "required_spend": "전월 실적 30만원 이상",
    "benefits": [
      "간편결제/페이에서 월 18,000원 혜택",
      "OTT 구독료 월 5,000원 절약"
    ],
    "monthly_savings": 18000,
    "annual_savings": 216000
  },
  "explanation": "간편결제 비중이 높은 소비 패턴과 카드 핵심 혜택이 정확히 맞아떨어집니다!",
  "analysis": {
    "annual_savings": 216000,
    "monthly_savings": 18000,
    "net_benefit": 199000,
    "annual_fee": 17000,
    "warnings": ["통합 할인한도 초과 시 혜택이 줄어듭니다."],
    "category_breakdown": {
      "digital_payment": 18000
    },
    "conditions_met": true
  }
}
```

#### POST `/recommend/structured`

이미 구조화된 UserIntent를 입력하면 바로 검색 단계부터 시작합니다.

**요청:**
```json
{
  "spending": {
    "grocery": {"amount": 300000},
    "digital_payment": {"amount": 200000}
  },
  "preferences": {
    "max_annual_fee": 20000,
    "prefer_types": ["debit"]
  },
  "filters": {
    "annual_fee_max": 20000,
    "pre_month_min_max": 500000,
    "type": "debit"
  }
}
```

### 관리자 API

운영 중에 카드 데이터를 동적으로 관리할 수 있는 API입니다.

#### GET `/admin/cards/stats`

벡터 DB 통계를 확인합니다.

**요청:**
```bash
curl http://localhost:8000/admin/cards/stats
```

**응답:**
```json
{
  "total_documents": 750,
  "total_cards": 250,
  "collection_name": "credit_cards",
  "chroma_db_path": "chroma_db"
}
```

#### POST `/admin/cards/fetch` ⭐ 1단계

카드고릴라 API에서 카드 데이터를 수집하여 JSON 파일로 저장합니다.

**💰 OpenAI 크레딧: 사용 안함** ✅

**파라미터:**
- `card_ids`: 카드 ID 리스트 (선택사항)
- `overwrite`: 기존 JSON 파일 덮어쓰기 여부 (기본값: false)
- `start_id`: card_ids 없을 때 시작 ID (기본값: 1)
- `end_id`: card_ids 없을 때 종료 ID (기본값: 5000)

**요청:**
```bash
# 전체 카드 수집 (1~5000)
curl -X POST "http://localhost:8000/admin/cards/fetch"

# 범위 지정
curl -X POST "http://localhost:8000/admin/cards/fetch?start_id=1&end_id=3000"

# 특정 카드만
curl -X POST "http://localhost:8000/admin/cards/fetch" \
  -H "Content-Type: application/json" \
  -d '{"card_ids": [2862, 1357, 2000]}'
```

**응답:**
```json
{
  "success": true,
  "message": "1단계 완료: 성공 245개, 실패 5개, 건너뜀 4750개",
  "summary": {
    "total_tried": 5000,
    "success_count": 245,
    "failed_count": 5,
    "skipped_count": 4750
  },
  "next_step": "POST /admin/cards/embed 를 실행하여 임베딩을 생성하세요"
}
```

**동작:**
1. 카드고릴라 API에서 카드 상세 정보 조회
2. 단종 카드(`is_discon: true`) 자동 제외
3. 압축 컨텍스트 생성 및 저장 (`data/cache/ctx/{card_id}.json`)

**특징:**
- OpenAI 크레딧을 사용하지 않으므로 안전하게 대량 수집 가능
- 중간에 중단되어도 이미 수집된 JSON 파일은 유지됨
- 재실행 시 `overwrite=false`면 기존 파일은 건너뜀

#### POST `/admin/cards/embed` ⭐ 2단계

JSON 파일을 읽어서 임베딩을 생성하고 ChromaDB에 저장합니다.

**💰 OpenAI 크레딧: 사용함** ⚠️ (text-embedding-3-small)

**파라미터:**
- `card_ids`: 카드 ID 리스트 (선택사항, 없으면 모든 JSON 파일 처리)
- `overwrite`: 기존 임베딩 덮어쓰기 여부 (기본값: false)

**요청:**
```bash
# 모든 JSON 파일 처리
curl -X POST "http://localhost:8000/admin/cards/embed"

# 특정 카드만
curl -X POST "http://localhost:8000/admin/cards/embed" \
  -H "Content-Type: application/json" \
  -d '{"card_ids": [2862, 1357, 2000]}'
```

**응답:**
```json
{
  "success": true,
  "message": "2단계 완료: 성공 245개, 실패 0개, 건너뜀 0개",
  "summary": {
    "success_count": 245,
    "failed_count": 0,
    "skipped_count": 0
  },
  "next_step": "GET /admin/cards/stats 로 벡터 DB 상태를 확인하세요"
}
```

**동작:**
1. `data/cache/ctx/{card_id}.json` 파일 읽기
2. 카드 데이터를 문서(chunk)로 분해 (Summary, Benefit×N, Notes)
3. OpenAI Embeddings API로 벡터화
4. ChromaDB에 저장

**특징:**
- OpenAI 크레딧을 사용하므로 필요한 카드만 선택적으로 처리 가능
- 1단계(fetch)와 분리되어 있어 임베딩만 다시 생성 가능
- JSON 파일이 없는 카드는 자동으로 건너뜀

#### POST `/admin/cards/sync` ⭐ 통합

1단계(fetch)와 2단계(embed)를 순차적으로 실행합니다.

**💰 OpenAI 크레딧: 2단계에서 사용** ⚠️

**파라미터:**
- `card_ids`: 카드 ID 리스트 (선택사항)
- `overwrite`: 덮어쓰기 여부 (기본값: false)
- `start_id`: 시작 ID (기본값: 1)
- `end_id`: 종료 ID (기본값: 5000)

**요청:**
```bash
# 전체 동기화 (1~5000)
curl -X POST "http://localhost:8000/admin/cards/sync"

# 범위 지정
curl -X POST "http://localhost:8000/admin/cards/sync?start_id=1&end_id=3000"
```

**응답:**
```json
{
  "success": true,
  "message": "전체 완료: 수집 245개, 임베딩 245개",
  "summary": {
    "total_tried": 5000,
    "fetch_success": 245,
    "embed_success": 245
  },
  "fetch_results": { ... },
  "embed_results": { ... }
}
```

#### POST `/admin/cards/{card_id}`

특정 카드 1개를 즉시 동기화합니다 (fetch + embed).

**파라미터:**
- `card_id`: 카드 ID (예: 2862)
- `overwrite`: 기존 데이터 덮어쓰기 여부 (기본값: false)

**요청:**
```bash
# 새 카드 추가
curl -X POST "http://localhost:8000/admin/cards/2862"

# 기존 카드 업데이트
curl -X POST "http://localhost:8000/admin/cards/2862?overwrite=true"
```

#### DELETE `/admin/cards/reset`

벡터 DB의 모든 데이터를 삭제하고 초기화합니다.

**⚠️ 주의: 되돌릴 수 없는 작업입니다!**

**요청:**
```bash
curl -X DELETE "http://localhost:8000/admin/cards/reset"
```

**응답:**
```json
{
  "success": true,
  "message": "벡터 DB가 초기화되었습니다.",
  "deleted_documents": 750,
  "collection_name": "credit_cards"
}
```

**동작:**
1. ChromaDB 컬렉션 삭제
2. 새 컬렉션 생성
3. 벡터 스토어 재초기화

**참고:** JSON 파일(`data/cache/ctx/*.json`)은 삭제되지 않으므로, 다시 `POST /admin/cards/embed`로 복구 가능합니다.

### 관리자 API 사용 시나리오

1. **초기 설정 (단계별)**: 카드 데이터 수집 → 임베딩 생성
   ```bash
   # 1단계: 데이터 수집 (크레딧 안씀)
   curl -X POST "http://localhost:8000/admin/cards/fetch"
   
   # 2단계: 임베딩 생성 (크레딧 사용)
   curl -X POST "http://localhost:8000/admin/cards/embed"
   ```

2. **초기 설정 (한번에)**: fetch + embed 자동 실행
   ```bash
   curl -X POST "http://localhost:8000/admin/cards/sync"
   ```

3. **신규 카드 추가**: 새로운 카드가 출시되면 추가
   ```bash
   curl -X POST "http://localhost:8000/admin/cards/3000"
   ```

4. **카드 정보 갱신**: 혜택이 변경된 카드를 업데이트
   ```bash
   curl -X POST "http://localhost:8000/admin/cards/2862?overwrite=true"
   ```

5. **통계 확인**: 현재 벡터 DB 상태 확인
   ```bash
   curl http://localhost:8000/admin/cards/stats
   ```

6. **벡터 DB 재구성**: 초기화 후 JSON 파일로 재생성
   ```bash
   curl -X DELETE "http://localhost:8000/admin/cards/reset"
   curl -X POST "http://localhost:8000/admin/cards/embed"
   ```

## ✅ 운영 규칙 및 주의사항

### 단종 카드 자동 제외
- `is_discon: true`인 카드는 데이터 수집 단계에서 제외됩니다
- 저장, 임베딩, 검색, LLM 입력 모두에서 사용되지 않습니다
- 사용자는 항상 발급 가능한 카드만 추천받습니다

### 캐싱 전략
- 카드고릴라 API 응답은 `data/cache/` 디렉터리에 JSON 파일로 저장됩니다
- 같은 카드를 다시 조회할 때는 API 호출 없이 캐시를 사용합니다
- 캐시를 무효화하려면 해당 파일을 삭제하세요

### Rate Limiting
- API 서버에 부하를 주지 않도록 초당 5회, 분당 60회로 제한합니다
- 429 (Too Many Requests) 응답을 받으면 자동으로 대기 후 재시도합니다

### 에러 처리
- 네트워크 오류, 타임아웃: 최대 3회 재시도 (지수 백오프)
- 404 (Not Found): 해당 카드는 스킵하고 다음으로 진행
- 5xx 서버 오류: 재시도 후 실패 시 에러 로그 기록

## 🔗 참고 자료

- **카드고릴라 API**: `https://api.card-gorilla.com:8080/v1/cards/{card_id}`
- **OpenAI API 문서**: https://platform.openai.com/docs
- **ChromaDB 문서**: https://docs.trychroma.com/

## 🤝 기여하기

버그 리포트, 기능 제안, 코드 기여를 환영합니다!

1. 이 저장소를 Fork하세요
2. 기능 브랜치를 생성하세요 (`git checkout -b feature/AmazingFeature`)
3. 변경사항을 커밋하세요 (`git commit -m 'Add some AmazingFeature'`)
4. 브랜치에 푸시하세요 (`git push origin feature/AmazingFeature`)
5. Pull Request를 생성하세요

## 📄 라이선스

이 프로젝트의 라이선스 정보는 별도로 명시되지 않았습니다.

## 📞 문의

프로젝트에 대한 문의사항이 있으시면 이슈를 생성해주세요.

---

**💡 팁**: API 문서(`http://localhost:8000/docs`)를 통해 모든 엔드포인트를 대화형으로 테스트해볼 수 있습니다!
