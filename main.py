from fastapi import FastAPI, HTTPException, Query, Body, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
import os
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional 
# Security modules
from security.prompt_validator import validate_user_input, PromptAttackException
from security.request_logger import RequestLogger, RequestTimer
from security.ip_utils import get_client_ip
from security.rate_limiter import rate_limit_dependency, RateLimiter

# 새로운 RAG + Agentic 모듈
from agents.input_parser import InputParser
from agents.benefit_analyzer import BenefitAnalyzer
from agents.recommender import Recommender
from agents.response_generator import ResponseGenerator
from vector_store.vector_store import CardVectorStore
from vector_store.embeddings import EmbeddingGenerator
from data_collection.card_gorilla_client import CardGorillaClient
from data_collection.data_parser import load_compressed_context
from admin.routes import router as admin_router

# 환경 변수 로드
load_dotenv()

# RAG + Agentic 서비스 전역 변수
input_parser = None
benefit_analyzer = None
recommender = None
response_generator = None
vector_store = None
embedding_generator = None
card_client = None


CATEGORY_LABELS = {
    "digital_payment": "간편결제/페이",
    "grocery": "마트/식료품",
    "subscription_video": "OTT 구독",
    "subscription_music": "음악/콘텐츠",
    "subscription": "구독 서비스",
    "online_shopping": "온라인 쇼핑",
    "travel": "여행/항공",
    "airline": "항공 마일리지",
    "cafe": "카페",
    "coffee": "카페",
    "convenience_store": "편의점",
    "dining": "외식",
    "fuel": "주유",
    "transportation": "교통",
    "delivery": "배달앱",
    "public_utilities": "공과금",
    "education": "교육",
    "mobile_payment": "모바일 결제"
}


class NaturalLanguageRequest(BaseModel):
    """사용자 자연어 입력"""

    user_input: str = Field(
        ...,
        min_length=15,
        description="소비 패턴을 설명하는 자연어 문장 (최소 15자)"
    )


class RecommendationCard(BaseModel):
    """추천 카드 정보"""

    id: str = Field(..., description="카드 식별자 (문자열)")
    name: str = Field(..., description="카드 이름")
    brand: str = Field(..., description="카드 브랜드/발급사")
    annual_fee: str = Field(..., description="연회비 정보 (문장)")
    required_spend: str = Field(..., description="전월 실적 조건")
    benefits: List[str] = Field(default_factory=list, description="주요 혜택 목록")
    monthly_savings: int = Field(..., description="예상 월 절약액 (원)")
    annual_savings: int = Field(..., description="예상 연 절약액 (원)")
    homepage_url: Optional[str] = Field(
        default=None,
        description="카드 상세 페이지 URL"
    )


class RecommendationAnalysis(BaseModel):
    """추천 분석 메타 정보"""

    annual_savings: int
    monthly_savings: int
    net_benefit: int
    annual_fee: int
    warnings: List[str] = Field(default_factory=list)
    category_breakdown: Dict[str, int] = Field(default_factory=dict)
    conditions_met: bool = False


class RecommendResponse(BaseModel):
    """최종 추천 응답"""

    card: RecommendationCard
    explanation: str = Field(..., description="이 카드를 추천한 이유")
    analysis: RecommendationAnalysis


def _format_currency(amount: int) -> str:
    """세 자리마다 콤마를 넣어 표시"""
    return f"{amount:,}"


def _format_required_spend(amount: Optional[int]) -> str:
    if not amount:
        return "전월 실적 조건 없음"
    return f"전월 실적 {_format_currency(int(amount))}원 이상"


def _category_label(category_key: str) -> str:
    if category_key in CATEGORY_LABELS:
        return CATEGORY_LABELS[category_key]
    return category_key.replace("_", " ").title()


def _build_benefit_highlights(category_breakdown: Dict[str, int], fallback_titles: List[str]) -> List[str]:
    highlights = []
    for category, amount in category_breakdown.items():
        if amount <= 0:
            continue
        label = _category_label(category)
        highlights.append(f"{label}에서 월 {_format_currency(amount)}원 혜택 예상")

    if not highlights:
        # 중복 제거: 순서를 유지하면서 중복을 제거
        seen = set()
        unique_titles = []
        for title in fallback_titles:
            if title not in seen:
                seen.add(title)
                unique_titles.append(title)
        highlights = unique_titles[:3]

    return highlights or ["혜택 정보를 불러오지 못했습니다. 카드 상세 페이지를 확인해주세요."]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    
    # Startup: 애플리케이션 시작 시
    print("🚀 신용카드 추천 서비스를 시작합니다...")
    
    # OpenAI API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        print("⚠️  Warning: OPENAI_API_KEY가 설정되지 않았습니다.")
        print("   .env 파일에 실제 API 키를 설정하거나 환경 변수를 설정해주세요.")
        print("   LLM 기능은 제한적으로 작동할 수 있습니다.")

    # MongoDB 연결 확인 (필수)
    try:
        from database.mongodb_client import MongoDBClient
        mongo_client = MongoDBClient()
        if mongo_client.health_check():
            print("✅ MongoDB Atlas 연결 성공")
            stats = mongo_client.get_stats()
            if stats.get("total_documents"):
                print(f"   📊 카드 문서: {stats['total_documents']}개")
            if stats.get("documents_with_embeddings"):
                print(f"   📊 임베딩: {stats['documents_with_embeddings']}개")
        else:
            print("❌ MongoDB 연결 실패 - 서비스를 시작할 수 없습니다")
            raise ConnectionError("MongoDB 연결 실패")
    except Exception as e:
        print(f"❌ MongoDB 초기화 실패: {e}")
        print("   .env 파일의 MONGODB_URI를 확인하세요")
        raise

    # RAG + Agentic 서비스 초기화
    try:
        global input_parser, benefit_analyzer, recommender, response_generator, vector_store, embedding_generator, card_client
        input_parser = InputParser()
        benefit_analyzer = BenefitAnalyzer()
        recommender = Recommender()
        response_generator = ResponseGenerator()
        vector_store = CardVectorStore()
        embedding_generator = EmbeddingGenerator()
        card_client = CardGorillaClient()
        # 라우터 모듈에서 접근할 수 있도록 app.state에도 저장
        app.state.vector_store = vector_store
        app.state.embedding_generator = embedding_generator
        app.state.card_client = card_client
        print("✅ RAG + Agentic 서비스가 성공적으로 초기화되었습니다.")
    except Exception as e:
        print(f"⚠️  RAG + Agentic 서비스 초기화 실패: {str(e)}")
        print("   /recommend/natural-language 엔드포인트는 사용할 수 없습니다.")

    # Security 인덱스 초기화
    try:
        mongo_client.initialize_security_indexes()
    except Exception as e:
        print(f"⚠️  Security indexes 초기화 실패: {e}")
        print("   보안 기능(rate limiting, 로깅)이 제한적으로 작동할 수 있습니다.")

    yield  # 서비스 실행
    
    # Shutdown: 애플리케이션 종료 시
    print("🛑 서비스를 종료합니다...")
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

# 관리자 라우트 모듈 등록
app.include_router(admin_router)

@app.get("/")
async def root():
    """루트 엔드포인트 - 서비스 정보를 반환합니다."""
    return {
        "service": "신용카드 추천 서비스",
        "version": "2.0.0",
        "description": "사용자의 소비 패턴을 분석하여 최적의 신용카드를 추천합니다 (RAG + Agentic)",
        "endpoints": {
            "POST /recommend/natural-language": "자연어 입력 기반 카드 추천",
            "POST /recommend/structured": "구조화된 입력 기반 카드 추천",
            "GET /health": "서비스 상태 확인",
            "POST /admin/cards/fetch": "1단계: 카드고릴라에서 데이터 수집 (관리자)",
            "POST /admin/cards/embed": "2단계: JSON을 임베딩으로 변환 (관리자)",
            "POST /admin/cards/sync": "통합: fetch + embed 한번에 실행 (관리자)",
            "POST /admin/cards/{card_id}": "특정 카드 추가/업데이트 (관리자)",
            "GET /admin/cards/stats": "벡터 DB 통계 확인 (관리자)",
            "DELETE /admin/cards/reset": "벡터 DB 초기화 (관리자)"
        }
    }

@app.get("/health")
async def health_check():
    """서비스 상태를 확인합니다."""
    return {
        "status": "healthy",
        "rag_service": "available" if vector_store else "unavailable",
        "openai_api_key": "configured" if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_API_KEY") != "your_openai_api_key_here" else "not_configured"
    }

# ========== 새로운 RAG + Agentic 엔드포인트 ==========

@app.post(
    "/recommend/natural-language",
    response_model=RecommendResponse,
    summary="자연어 소비 패턴으로 카드 추천",
    dependencies=[Depends(rate_limit_dependency)]
)
async def recommend_natural_language(
    request: Request,
    payload: NaturalLanguageRequest
):
    """
    자연어 입력 기반 카드 추천

    사용자가 자연어로 소비 패턴을 입력하면, 최적의 카드 1장을 추천합니다.

    - **user_input**: 자연어 소비 패턴 (예: "마트 30만원, 넷플릭스 구독, 간편결제 자주 씀. 연회비 2만원 이하")

    파이프라인:
    1. 자연어 입력 파싱 (Input Parser)
    2. 벡터 검색으로 후보 Top-M 선정
    3. 혜택 분석 (Benefit Analyzer)
    4. 최종 1장 선택 (Recommender)
    5. 응답 생성 (Response Generator)
    """
    import time
    import traceback

    # 로깅 및 타이머 초기화
    timer = RequestTimer()
    timer.start()
    request_logger = RequestLogger()
    ip_address = get_client_ip(request)

    # 프롬프트 공격 여부 추적
    prompt_attack_detected = False
    attack_patterns = []

    try:
        user_input = payload.user_input.strip()

        # 프롬프트 공격 검증
        try:
            validate_user_input(user_input)
        except PromptAttackException as attack_error:
            # 프롬프트 공격 탐지됨
            prompt_attack_detected = True
            attack_patterns = attack_error.matched_patterns

            # 로깅
            await request_logger.log_request(
                ip_address=ip_address,
                endpoint="/recommend/natural-language",
                user_input=user_input,
                processing_time_ms=timer.get_total_time(),
                status="validation_error",
                prompt_attack_detected=True,
                attack_patterns=attack_patterns,
                error={
                    "message": str(attack_error.detail),
                    "type": "prompt_attack",
                    "status_code": 400
                },
                performance=timer.get_performance_dict()
            )
            raise HTTPException(
                status_code=400,
                detail=attack_error.detail
            )

        if not all([input_parser, benefit_analyzer, recommender, response_generator, vector_store]):
            raise HTTPException(
                status_code=503,
                detail="RAG + Agentic 서비스를 사용할 수 없습니다. 서비스 초기화를 확인해주세요."
            )
        
        # 전체 처리 시작
        print(f"\n[PERF] ========== 전체 처리 시작 ==========")

        # 1. 입력 파싱
        print(f"\n[INFO] Step 1: Input Parsing")
        print(f"Input: {user_input}")
        user_intent = input_parser.parse(user_input)
        timer.mark_step("step1_input_parsing_ms")
        print(f"Parsed Intent: {user_intent}")
        print(f"[PERF] Step 1 완료")
        
        # 2. 벡터 검색 (Top-M 후보 선정)
        query_text = user_intent.get("query_text", user_input)
        filters = user_intent.get("filters", {})
        
        # None 값을 가진 필터 키 제거
        if filters:
            filters = {k: v for k, v in filters.items() if v is not None}
        
        print(f"\n[INFO] Step 2: Vector Search")
        print(f"Query: {query_text}")
        print(f"Filters: {filters}")

        candidates = vector_store.search_cards(query_text, filters, top_m=5)
        timer.mark_step("step2_vector_search_ms")
        print(f"Candidates Found: {len(candidates)}")
        for i, c in enumerate(candidates):
            print(f"  [{i+1}] ID: {c.get('card_id')} (Score: {c.get('aggregate_score', 0.0):.4f})")
        print(f"[PERF] Step 2 완료")
        
        if not candidates:
            print("[INFO] No candidates found. Returning error.")
            raise HTTPException(
                status_code=404,
                detail="조건에 맞는 카드를 찾을 수 없습니다. 연회비/전월실적 조건을 완화해 다시 시도해보세요."
            )
        
        # 3. 혜택 분석
        print(f"\n[INFO] Step 3: Benefit Analysis")
        user_pattern = {
            "spending": user_intent.get("spending", {}),
            "preferences": user_intent.get("preferences", {}),
            "constraints": user_intent.get("constraints", {})
        }
        print(f"User Pattern: {user_pattern}")

        card_contexts = [
            {
                "card_id": c["card_id"],
                "evidence_chunks": c["evidence_chunks"]
            }
            for c in candidates
        ]

        analysis_results = await benefit_analyzer.analyze_batch(user_pattern, card_contexts)
        timer.mark_step("step3_benefit_analysis_ms")
        print(f"Analysis Results: {len(analysis_results)} cards analyzed")
        print(f"[PERF] Step 3 완료")
        
        # 4. 최종 선택
        print(f"\n[INFO] Step 4: Final Selection")
        recommendation_result = recommender.select_best_card(
            analysis_results,
            user_preferences=user_intent.get("preferences")
        )
        timer.mark_step("step4_recommendation_ms")
        print(f"Selected Card ID: {recommendation_result.get('selected_card')}")
        print(f"Net Benefit: {recommendation_result.get('score_breakdown', {}).get('net_benefit')}")
        print(f"[PERF] Step 4 완료")
        
        # 5. 응답 생성
        print(f"\n[INFO] Step 5: Response Generation")
        recommendation_text = response_generator.generate(
            recommendation_result,
            user_pattern=user_pattern
        )
        timer.mark_step("step5_response_generation_ms")
        print("Response generated successfully.")
        print(f"[PERF] Step 5 완료")

        # 전체 처리 완료
        total_time_seconds = timer.get_total_time() / 1000
        print(f"\n[PERF] ========== 전체 처리 완료: {total_time_seconds:.3f}초 ==========")
        print(f"[PERF] 단계별 시간: {timer.get_performance_dict()}")
        
        selected_card_id = recommendation_result["selected_card"]
        card_context = load_compressed_context(selected_card_id)
        if not card_context:
            raise HTTPException(
                status_code=500,
                detail="카드 메타데이터를 불러오지 못했습니다. 관리자에게 문의해주세요."
            )

        meta = card_context.get("meta", {})
        conditions = card_context.get("conditions", {})
        fees = card_context.get("fees", {})
        hints = card_context.get("hints", {})

        annual_savings = int(recommendation_result.get("annual_savings", 0))
        monthly_savings = annual_savings // 12 if annual_savings > 0 else 0
        score_breakdown = recommendation_result.get("score_breakdown", {})
        net_benefit = int(score_breakdown.get("net_benefit", 0))
        annual_fee_amount = int(recommendation_result.get("annual_fee", 0))

        brand_candidates = hints.get("brands", [])
        brand = (
            brand_candidates[0]
            if brand_candidates
            else meta.get("issuer", "정보 없음")
        )

        annual_fee_text = (
            fees.get("annual_detail")
            or fees.get("annual_basic")
            or (f"{_format_currency(annual_fee_amount)}원" if annual_fee_amount else "연회비 정보 확인 필요")
        )

        required_spend = _format_required_spend(conditions.get("prev_month_min"))
        category_breakdown = recommendation_result.get("category_breakdown", {})
        benefit_highlights = _build_benefit_highlights(
            category_breakdown,
            hints.get("top_titles", [])
        )

        card_payload = RecommendationCard(
            id=str(selected_card_id),
            name=recommendation_result.get("name", meta.get("name", "")),
            brand=brand,
            annual_fee=annual_fee_text,
            required_spend=required_spend,
            benefits=benefit_highlights,
            monthly_savings=monthly_savings,
            annual_savings=annual_savings,
            homepage_url=None
        )

        analysis_payload = RecommendationAnalysis(
            annual_savings=annual_savings,
            monthly_savings=monthly_savings,
            net_benefit=net_benefit,
            annual_fee=annual_fee_amount,
            warnings=recommendation_result.get("warnings", []),
            category_breakdown=category_breakdown,
            conditions_met=recommendation_result.get("conditions_met", False)
        )

        response = RecommendResponse(
            card=card_payload,
            explanation=recommendation_text.strip(),
            analysis=analysis_payload
        )

        # 성공 로깅
        await request_logger.log_request(
            ip_address=ip_address,
            endpoint="/recommend/natural-language",
            user_input=user_input,
            processing_time_ms=timer.get_total_time(),
            status="success",
            recommendation={
                "card_id": str(selected_card_id),
                "card_name": recommendation_result.get("name", meta.get("name", "")),
                "annual_savings": annual_savings,
                "monthly_savings": monthly_savings,
                "net_benefit": net_benefit,
                "annual_fee": annual_fee_amount,
                "explanation": recommendation_text.strip(),
                "category_breakdown": category_breakdown,
                "warnings": recommendation_result.get("warnings", [])
            },
            performance=timer.get_performance_dict(),
            alternative_cards=[str(c["card_id"]) for c in candidates[:5]]
        )

        # Rate limit 정보를 헤더에 포함 
        rate_limiter = RateLimiter()
        remaining = getattr(request.state, "rate_limit_remaining", rate_limiter.daily_limit)
        reset_time = getattr(request.state, "rate_limit_reset", None)
        
        headers = {
            "X-RateLimit-Limit": str(rate_limiter.daily_limit),
            "X-RateLimit-Remaining": str(remaining),
        }
        if reset_time:
            headers["X-RateLimit-Reset"] = str(int(reset_time.timestamp()))
        
        return Response(
            content=response.model_dump_json(),
            media_type="application/json",
            headers=headers
        )

    except HTTPException as e:
        # 프롬프트 공격은 이미 로깅됨
        if prompt_attack_detected:
            raise

        # HTTPException 로깅 (rate limit, not found 등)
        error_status = "rate_limited" if e.status_code == 429 else \
                      "validation_error" if e.status_code == 400 else \
                      "not_found" if e.status_code == 404 else \
                      "service_unavailable" if e.status_code == 503 else "error"

        await request_logger.log_request(
            ip_address=ip_address,
            endpoint="/recommend/natural-language",
            user_input=payload.user_input.strip(),
            processing_time_ms=timer.get_total_time(),
            status=error_status,
            error={
                "message": str(e.detail),
                "type": error_status,
                "status_code": e.status_code
            },
            performance=timer.get_performance_dict(),
            prompt_attack_detected=False
        )
        raise

    except Exception as e:
        # 일반 예외 로깅
        await request_logger.log_request(
            ip_address=ip_address,
            endpoint="/recommend/natural-language",
            user_input=payload.user_input.strip(),
            processing_time_ms=timer.get_total_time(),
            status="error",
            error={
                "message": str(e),
                "type": "internal",
                "detail": traceback.format_exc()
            },
            performance=timer.get_performance_dict()
        )

        raise HTTPException(
            status_code=500,
            detail=f"추천 생성 중 오류가 발생했습니다: {str(e)}"
        )


@app.post("/recommend/structured")
async def recommend_structured(user_intent: dict):
    """
    구조화된 입력 기반 카드 추천
    
    이미 구조화된 UserIntent를 입력하면, 벡터 검색 단계부터 시작합니다.
    
    - **user_intent**: UserIntent JSON 객체
    
    파이프라인:
    1. 벡터 검색으로 후보 Top-M 선정 (입력 파싱 생략)
    2. 혜택 분석 (Benefit Analyzer)
    3. 최종 1장 선택 (Recommender)
    4. 응답 생성 (Response Generator)
    """
    try:
        if not all([benefit_analyzer, recommender, response_generator, vector_store]):
            raise HTTPException(
                status_code=503,
                detail="RAG + Agentic 서비스를 사용할 수 없습니다. 서비스 초기화를 확인해주세요."
            )
        
        # 1. 벡터 검색 (Top-M 후보 선정)
        query_text = user_intent.get("query_text", "")
        filters = user_intent.get("filters", {})
        
        # None 값을 가진 필터 키 제거
        if filters:
            filters = {k: v for k, v in filters.items() if v is not None}
        
        candidates = vector_store.search_cards(query_text, filters, top_m=5)
        
        if not candidates:
            return {
                "error": "조건에 맞는 카드를 찾을 수 없습니다.",
                "recommendation_text": "죄송합니다. 입력하신 조건에 맞는 카드를 찾을 수 없습니다."
            }
        
        # 2. 혜택 분석
        user_pattern = {
            "spending": user_intent.get("spending", {}),
            "preferences": user_intent.get("preferences", {})
        }
        
        card_contexts = [
            {
                "card_id": c["card_id"],
                "evidence_chunks": c["evidence_chunks"]
            }
            for c in candidates
        ]
        
        analysis_results = await benefit_analyzer.analyze_batch(user_pattern, card_contexts)
        
        # 3. 최종 선택
        recommendation_result = recommender.select_best_card(
            analysis_results,
            user_preferences=user_intent.get("preferences")
        )
        
        # 4. 응답 생성
        recommendation_text = response_generator.generate(
            recommendation_result,
            user_pattern=user_pattern
        )
        
        return {
            "recommendation_text": recommendation_text,
            "selected_card": {
                "card_id": recommendation_result["selected_card"],
                "name": recommendation_result.get("name", "")
            },
            "annual_savings": recommendation_result.get("annual_savings", 0),
            "monthly_savings": recommendation_result.get("annual_savings", 0) // 12,
            "annual_fee": recommendation_result.get("annual_fee", 0),
            "net_benefit": recommendation_result.get("score_breakdown", {}).get("net_benefit", 0),
            "analysis_details": {
                "warnings": recommendation_result.get("warnings", []),
                "category_breakdown": recommendation_result.get("category_breakdown", {}),
                "conditions_met": recommendation_result.get("conditions_met", False)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"추천 생성 중 오류가 발생했습니다: {str(e)}"
        )
"""
관리자 관련 라우트(/admin/*)는 `admin/routes.py`로 모듈화되었습니다.
`main.py`에서는 `app.include_router(admin_router)`로만 등록합니다.
"""

if __name__ == "__main__":
    print("📝 사용법:")
    print("   1. .env 파일에 OPENAI_API_KEY를 설정하세요")
    print("   2. pip install -r requirements.txt로 의존성을 설치하세요")
    print("   3. python main.py로 서비스를 시작하세요")
    print("   4. http://localhost:8000/docs에서 API 문서를 확인하세요")
    print("   5. POST /recommend/natural-language로 테스트해보세요")
    print()
    
    # 포트 8000이 사용 중인지 확인
    PORT = 8000
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=True,
        log_level="info"
    )
