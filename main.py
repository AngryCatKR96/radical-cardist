from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
import os
from dotenv import load_dotenv

from models import RecommendationRequest, RecommendationResponse
from llm_service import CreditCardLLMService

# 환경 변수 로드
load_dotenv()

# LLM 서비스 전역 변수
llm_service = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    global llm_service
    
    # Startup: 애플리케이션 시작 시
    print("🚀 신용카드 추천 LLM 서비스를 시작합니다...")
    
    # OpenAI API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        print("⚠️  Warning: OPENAI_API_KEY가 설정되지 않았습니다.")
        print("   .env 파일에 실제 API 키를 설정하거나 환경 변수를 설정해주세요.")
        print("   LLM 기능은 제한적으로 작동할 수 있습니다.")
    
    try:
        llm_service = CreditCardLLMService()
        print("✅ LLM 서비스가 성공적으로 초기화되었습니다.")
    except Exception as e:
        print(f"❌ LLM 서비스 초기화 실패: {str(e)}")
        print("   기본 추천 기능만 사용 가능합니다.")
    
    yield  # 서비스 실행
    
    # Shutdown: 애플리케이션 종료 시
    print("🛑 서비스를 종료합니다...")
    if llm_service:
        print("   LLM 서비스 정리 중...")
    print("✅ 서비스가 안전하게 종료되었습니다.")

# FastAPI 앱 생성 (lifespan 포함)
app = FastAPI(
    title="Radical Cardists",
    description="사용자의 소비 패턴을 분석하여 최적의 신용카드 조합을 추천하는 AI 서비스",
    version="0.1.0",
    lifespan=lifespan
)

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """루트 엔드포인트 - 서비스 정보를 반환합니다."""
    return {
        "service": "신용카드 추천 LLM 서비스",
        "version": "1.0.0",
        "description": "사용자의 소비 패턴을 분석하여 최적의 신용카드 조합을 추천합니다",
        "endpoints": {
            "POST /recommend": "신용카드 추천",
            "GET /health": "서비스 상태 확인"
        }
    }

@app.get("/health")
async def health_check():
    """서비스 상태를 확인합니다."""
    return {
        "status": "healthy",
        "llm_service": "available" if llm_service else "unavailable",
        "openai_api_key": "configured" if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_API_KEY") != "your_openai_api_key_here" else "not_configured"
    }

@app.post("/recommend", response_model=RecommendationResponse)
async def recommend_cards(request: RecommendationRequest):
    """
    사용자의 소비 패턴을 분석하여 최적의 신용카드 조합을 추천합니다.
    
    - **monthly_spending**: 월 총 소비 금액
    - **spending_breakdown**: 카테고리별 소비 금액
    - **subscriptions**: 구독 서비스 목록
    """
    try:
        if not llm_service:
            raise HTTPException(
                status_code=503, 
                detail="LLM 서비스를 사용할 수 없습니다. 서비스 초기화를 확인해주세요."
            )
        
        # 추천 생성
        result = llm_service.get_recommendation(request)
        
        # 에러가 있는 경우
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        # 응답 모델 생성
        response = RecommendationResponse(
            recommendation_text=result["recommendation_text"],
            selected_cards=result["selected_cards"],
            monthly_savings=result["monthly_savings"],
            annual_savings=result["annual_savings"],
            usage_strategy=result["usage_strategy"],
            total_annual_fee=result["total_annual_fee"],
            net_annual_savings=result["net_annual_savings"]
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"추천 생성 중 오류가 발생했습니다: {str(e)}"
        )

@app.get("/cards")
async def get_available_cards():
    """사용 가능한 카드 목록을 반환합니다."""
    try:
        if not llm_service:
            raise HTTPException(
                status_code=503, 
                detail="LLM 서비스를 사용할 수 없습니다."
            )
        
        cards = []
        for card in llm_service.cards:
            card_info = {
                "id": card.id,
                "name": card.name,
                "bank": card.bank,
                "annual_fee": card.annual_fee,
                "benefits": [
                    {
                        "category": benefit.category,
                        "type": benefit.type,
                        "rate": benefit.rate,
                        "monthly_limit": benefit.monthly_limit,
                        "min_purchase": benefit.min_purchase
                    }
                    for benefit in card.benefits
                ],
                "conditions": {
                    "prev_month_min": card.conditions.prev_month_min,
                    "benefit_cap": card.conditions.benefit_cap
                }
            }
            cards.append(card_info)
        
        return {"cards": cards, "total": len(cards)}
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"카드 정보 조회 중 오류가 발생했습니다: {str(e)}"
        )

@app.post("/test")
async def test_recommendation():
    """테스트용 추천 요청을 실행합니다."""
    test_request = RecommendationRequest(
        monthly_spending=1000000,
        spending_breakdown={
            "온라인쇼핑": 300000,
            "마트": 200000,
            "편의점": 100000,
            "카페": 50000,
            "대중교통": 100000,
            "주유": 150000,
            "배달앱": 100000
        },
        subscriptions=["넷플릭스", "유튜브프리미엄", "스포티파이"]
    )
    
    return await recommend_cards(test_request)

if __name__ == "__main__":
    print("📝 사용법:")
    print("   1. .env 파일에 OPENAI_API_KEY를 설정하세요")
    print("   2. pip install -r requirements.txt로 의존성을 설치하세요")
    print("   3. python main.py로 서비스를 시작하세요")
    print("   4. http://localhost:8000/docs에서 API 문서를 확인하세요")
    print("   5. POST /test로 테스트해보세요")
    print()
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
