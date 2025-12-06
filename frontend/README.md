# 나에게 맞는 신용카드 추천 (Frontend)
Radical Cardist 백엔드(`FastAPI`)의 `POST /recommend/natural-language` 엔드포인트를 호출하여 **사용자 소비 패턴 기반 신용카드 1장**을 추천해주는 Next.js 14(App Router) 클라이언트입니다.

## 주요 기능
- 자연어 입력 텍스트 영역 + 샘플 프롬프트 버튼
- 최소 15자 검증, 부족 시 안내 문구 노출
- 로딩/성공/에러 3단계 상태
  - 로딩: 스피너 + “소비 패턴을 분석하고 있어요…”
  - 성공: 카드 메타(연회비/전월 실적/순 혜택) + 혜택 리스트 + 추천 사유 + 카테고리별 절약액 + 주의사항
  - 에러: 조건 완화 안내 + 재시도 버튼
- “조건 조금 바꿔서 다시 질문하기” / “새로 입력하기” 액션
- SEO 대응 메타데이터(`app/layout.tsx`): OG, 키워드, 한국어 lang

## 기술 스택
- Next.js 14(App Router) + TypeScript
- CSS Module(`app/page.module.css`)
- Fetch API 기반 비동기 통신

## 개발 환경 실행
```bash
cd frontend
npm install
npm run dev
# 기본 포트: http://localhost:3000
```

### 환경 변수
백엔드 주소 변경 시 `.env.local`(또는 환경 변수)에서 설정합니다.
```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```
미설정 시 `http://localhost:8000`을 기본값으로 사용합니다.

## API 연동 규격
- 요청: `POST {API_BASE_URL}/recommend/natural-language`
```json
{
  "user_input": "마트 30만원, 넷플릭스 구독, 간편결제 자주 씀..."
}
```
- 응답:
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
  "explanation": "간편결제 비중이 높은 소비 패턴과 카드 혜택이 일치합니다...",
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

## 디렉터리 구조
```
frontend/
├── app/
│   ├── page.tsx          # 메인 페이지(UI/로직)
│   ├── page.module.css   # 화면 스타일
│   ├── globals.css       # 전역 스타일 및 폰트
│   └── layout.tsx        # SEO 메타/폰트 설정
├── types/recommendation.ts # 백엔드 응답 타입 정의
├── next.config.ts
├── package.json
└── README.md
``` 
