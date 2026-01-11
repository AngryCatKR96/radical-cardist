from fastapi import FastAPI, HTTPException, Query, Body, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Dict, List, Optional 
# Security modules
from security.admin_auth import require_admin_auth
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


# ========== 관리자 API 엔드포인트 ==========

@app.get("/admin/cards/stats", dependencies=[Depends(require_admin_auth)])
async def get_vector_db_stats():
    """
    MongoDB 벡터 DB 통계 확인

    Returns:
        MongoDB 컬렉션의 통계 정보
    """
    try:
        from database.mongodb_client import MongoDBClient

        mongo_client = MongoDBClient()
        stats = mongo_client.get_stats()

        return {
            "database": stats.get("database"),
            "collection": stats.get("collection"),
            "total_documents": stats.get("total_documents", 0),
            "documents_with_embeddings": stats.get("documents_with_embeddings", 0),
            "indexes": stats.get("indexes", []),
            "search_indexes": stats.get("search_indexes", []),
            "vector_search_ready": stats.get("vector_search_ready", False)
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"통계 조회 중 오류가 발생했습니다: {str(e)}"
        )


@app.get("/admin/mongodb/health", dependencies=[Depends(require_admin_auth)])
async def mongodb_health_check():
    """
    MongoDB Atlas 연결 상태 및 인덱스 확인

    Returns:
        MongoDB 연결 상태, 인덱스 목록, 문서 수 등
    """
    try:
        from database.mongodb_client import MongoDBClient

        mongo_client = MongoDBClient()
        is_connected = mongo_client.health_check()

        if not is_connected:
            return {
                "status": "disconnected",
                "message": "MongoDB 연결 실패"
            }

        # 통계 정보 조회
        stats = mongo_client.get_stats()

        return {
            "status": "connected",
            "database": stats.get("database"),
            "collection": stats.get("collection"),
            "total_documents": stats.get("total_documents", 0),
            "documents_with_embeddings": stats.get("documents_with_embeddings", 0),
            "indexes": stats.get("indexes", []),
            "search_indexes": stats.get("search_indexes", []),
            "vector_search_ready": stats.get("vector_search_ready", False)
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


async def _fetch_cards_from_cardgorilla(card_ids: List[int], overwrite: bool):
    """1단계: 카드고릴라에서 데이터 수집 및 JSON 생성"""
    results = {
        "success": [],
        "failed": [],
        "skipped": []
    }
    
    print(f"📥 1단계: 카드 데이터 수집 시작 ({len(card_ids)}개 ID)")
    
    for idx, card_id in enumerate(card_ids, 1):
        try:
            if idx % 100 == 0:
                print(f"  진행: {idx}/{len(card_ids)} ({idx*100//len(card_ids)}%)")
            
            # 카드 데이터 조회 (자동으로 JSON 저장됨)
            card_data = await card_client.fetch_card_detail(card_id, use_cache=not overwrite)
            
            if card_data:
                results["success"].append({
                    "card_id": card_id,
                    "name": card_data["meta"]["name"]
                })
            else:
                results["skipped"].append({
                    "card_id": card_id,
                    "reason": "카드를 찾을 수 없거나 단종됨"
                })
                
        except Exception as e:
            results["failed"].append({
                "card_id": card_id,
                "error": str(e)
            })
            continue
    
    print(f"✅ 1단계 완료: 성공 {len(results['success'])}개, 실패 {len(results['failed'])}개, 건너뜀 {len(results['skipped'])}개")
    return results


async def _embed_cards_to_chromadb(card_ids: Optional[List[int]], overwrite: bool):
    """2단계: JSON 파일을 읽어서 임베딩 생성 및 ChromaDB 저장"""
    results = {
        "success": [],
        "failed": [],
        "skipped": []
    }
    
    # card_ids가 없으면 data/cache/ctx 폴더의 모든 JSON 파일 처리
    if not card_ids:
        import json
        from pathlib import Path
        
        ctx_dir = Path("data/cache/ctx")
        if not ctx_dir.exists():
            print("⚠️  data/cache/ctx 폴더가 없습니다. 먼저 1단계(fetch)를 실행하세요.")
            return results
        
        json_files = list(ctx_dir.glob("*.json"))
        card_ids = [int(f.stem) for f in json_files]
        print(f"📂 {len(card_ids)}개 JSON 파일 발견")
    
    print(f"🔨 2단계: 임베딩 생성 시작 ({len(card_ids)}개)")
    
    for idx, card_id in enumerate(card_ids, 1):
        try:
            print(f"  [{idx}/{len(card_ids)}] 카드 ID {card_id} 임베딩 중...")
            
            # JSON 파일 로드
            from pathlib import Path
            import json
            
            json_file = Path("data/cache/ctx") / f"{card_id}.json"
            
            if not json_file.exists():
                results["skipped"].append({
                    "card_id": card_id,
                    "reason": "JSON 파일 없음"
                })
                continue
            
            with open(json_file, 'r', encoding='utf-8') as f:
                card_data = json.load(f)
            
            # ChromaDB에 추가 (문서 분해 + 임베딩 생성)
            embedding_generator.add_card(card_data, overwrite=overwrite)
            
            results["success"].append({
                "card_id": card_id,
                "name": card_data["meta"]["name"]
            })
            print(f"  ✅ 카드 ID {card_id} 완료")
                
        except Exception as e:
            error_msg = str(e)
            
            # OpenAI 크레딧/할당량 부족 감지
            if "insufficient_quota" in error_msg.lower() or "quota" in error_msg.lower():
                print(f"\n💰 OpenAI 크레딧 부족 감지!")
                print(f"   처리 완료: {len(results['success'])}개")
                print(f"   미처리: {len(card_ids) - idx}개")
                print(f"   다음 카드부터 재개: card_id={card_id}")
                
                results["failed"].append({
                    "card_id": card_id,
                    "error": "OpenAI 크레딧 부족으로 중단"
                })
                
                # 크레딧 부족은 치명적 에러이므로 즉시 중단
                break
            
            # Rate Limit 감지
            elif "rate_limit" in error_msg.lower():
                print(f"  ⏳ Rate Limit 도달, 60초 대기 후 재시도...")
                import asyncio
                await asyncio.sleep(60)
                
                # 재시도
                try:
                    embedding_generator.add_card(card_data, overwrite=overwrite)
                    results["success"].append({
                        "card_id": card_id,
                        "name": card_data["meta"]["name"]
                    })
                    print(f"  ✅ 카드 ID {card_id} 완료 (재시도 성공)")
                except Exception as retry_error:
                    results["failed"].append({
                        "card_id": card_id,
                        "error": f"재시도 실패: {str(retry_error)}"
                    })
                    print(f"  ❌ 카드 ID {card_id} 재시도 실패: {retry_error}")
            else:
                # 일반 에러는 기록하고 계속
                results["failed"].append({
                    "card_id": card_id,
                    "error": error_msg
                })
                print(f"  ❌ 카드 ID {card_id} 실패: {e}")
            
            continue
    
    print(f"✅ 2단계 완료: 성공 {len(results['success'])}개, 실패 {len(results['failed'])}개, 건너뜀 {len(results['skipped'])}개")
    return results


async def _sync_cards_background(card_ids: List[int], overwrite: bool):
    """여러 카드 동기화 (동기 방식으로 결과 반환)"""
    results = {
        "success": [],
        "failed": [],
        "skipped": []
    }
    
    print(f"🔄 카드 동기화 시작: {len(card_ids)}개 카드")
    
    for idx, card_id in enumerate(card_ids, 1):
        try:
            print(f"  [{idx}/{len(card_ids)}] 카드 ID {card_id} 처리 중...")
            
            # 카드 데이터 조회
            card_data = await card_client.fetch_card_detail(card_id, use_cache=not overwrite)
            
            if card_data:
                # ChromaDB에 추가
                embedding_generator.add_card(card_data, overwrite=overwrite)
                results["success"].append({
                    "card_id": card_id,
                    "name": card_data["meta"]["name"]
                })
                print(f"  ✅ 카드 ID {card_id} 완료")
            else:
                results["skipped"].append({
                    "card_id": card_id,
                    "reason": "카드를 찾을 수 없거나 단종됨"
                })
                print(f"  ⏭️  카드 ID {card_id} 건너뜀 (단종 또는 없음)")
                
        except Exception as e:
            results["failed"].append({
                "card_id": card_id,
                "error": str(e)
            })
            print(f"  ❌ 카드 ID {card_id} 실패: {e}")
            continue
    
    print(f"✅ 동기화 완료: 성공 {len(results['success'])}개, 실패 {len(results['failed'])}개, 건너뜀 {len(results['skipped'])}개")
    return results


@app.post("/admin/cards/fetch", dependencies=[Depends(require_admin_auth)])
async def fetch_cards_from_cardgorilla(
    overwrite: bool = Query(False),
    start_id: int = Query(1),
    end_id: int = Query(5000),
    card_ids: Optional[List[int]] = Body(None)
):
    """
    1단계: 카드고릴라에서 데이터 수집 및 JSON 생성
    
    카드고릴라 API에서 카드 정보를 가져와 압축 컨텍스트 JSON 파일로 저장합니다.
    (data/cache/ctx/{card_id}.json)
    
    💰 OpenAI 크레딧: 사용하지 않음 ✅
    
    Args:
        card_ids: 카드 ID 리스트 (지정하면 해당 ID만)
        overwrite: 기존 JSON 파일 덮어쓰기 여부
        start_id: card_ids 없을 때 시작 ID (기본값: 1)
        end_id: card_ids 없을 때 종료 ID (기본값: 5000)
    
    Returns:
        수집 결과 (성공/실패/건너뜀 목록)
    """
    try:
        if not card_client:
            raise HTTPException(
                status_code=503,
                detail="카드 수집 서비스를 사용할 수 없습니다."
            )
        
        # card_ids가 없으면 범위 생성
        if not card_ids:
            card_ids = list(range(start_id, end_id + 1))
            print(f"📋 카드 ID 범위: {start_id}~{end_id} ({len(card_ids)}개)")
        
        # 1단계 실행
        results = await _fetch_cards_from_cardgorilla(card_ids, overwrite)
        
        return {
            "success": True,
            "message": f"1단계 완료: 성공 {len(results['success'])}개, 실패 {len(results['failed'])}개, 건너뜀 {len(results['skipped'])}개",
            "summary": {
                "total_tried": len(card_ids),
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "skipped_count": len(results["skipped"])
            },
            "details": results,
            "next_step": "POST /admin/cards/embed 를 실행하여 임베딩을 생성하세요"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"카드 수집 중 오류가 발생했습니다: {str(e)}"
        )


@app.post("/admin/cards/embed", dependencies=[Depends(require_admin_auth)])
async def embed_cards_to_chromadb(
    overwrite: bool = Query(False),
    start_id: int = Query(None),
    end_id: int = Query(None),
    card_ids: Optional[List[int]] = Body(None)
):
    """
    2단계: JSON을 임베딩으로 변환하여 ChromaDB에 저장
    
    data/cache/ctx 폴더의 JSON 파일들을 읽어서:
    - 문서로 분해
    - OpenAI Embeddings 생성
    - ChromaDB에 저장
    
    💰 OpenAI 크레딧: 사용함 ⚠️ (text-embedding-3-small)
    
    Args:
        card_ids: 카드 ID 리스트 (지정하면 해당 ID만)
        overwrite: 기존 임베딩 덮어쓰기 여부
        start_id: card_ids 없을 때 시작 ID (선택사항)
        end_id: card_ids 없을 때 종료 ID (선택사항)
    
    Returns:
        임베딩 생성 결과
        
    Example:
        # 모든 JSON 파일 처리
        POST /admin/cards/embed
        
        # 범위 지정
        POST /admin/cards/embed?start_id=1&end_id=100
        
        # 특정 카드만
        POST /admin/cards/embed
        {"card_ids": [2862, 1357]}
    """
    try:
        if not embedding_generator:
            raise HTTPException(
                status_code=503,
                detail="임베딩 서비스를 사용할 수 없습니다."
            )
        
        # card_ids 결정
        if not card_ids:
            if start_id is not None and end_id is not None:
                # 범위 지정된 경우
                card_ids = list(range(start_id, end_id + 1))
                print(f"📋 카드 ID 범위: {start_id}~{end_id} ({len(card_ids)}개)")
            else:
                # 범위 없으면 모든 JSON 파일
                card_ids = None
                print(f"📂 모든 JSON 파일 처리")
        
        # 2단계 실행
        results = await _embed_cards_to_chromadb(card_ids, overwrite)
        
        return {
            "success": True,
            "message": f"2단계 완료: 성공 {len(results['success'])}개, 실패 {len(results['failed'])}개, 건너뜀 {len(results['skipped'])}개",
            "summary": {
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "skipped_count": len(results["skipped"])
            },
            "details": results,
            "next_step": "GET /admin/cards/stats 로 벡터 DB 상태를 확인하세요"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"임베딩 생성 중 오류가 발생했습니다: {str(e)}"
        )


@app.post("/admin/cards/sync", dependencies=[Depends(require_admin_auth)])
async def sync_cards_batch(
    overwrite: bool = Query(False),
    start_id: int = Query(1),
    end_id: int = Query(5000),
    card_ids: Optional[List[int]] = Body(None)
):
    """
    통합: fetch + embed 한번에 실행
    
    1단계(fetch)와 2단계(embed)를 순차적으로 실행합니다.
    
    💰 OpenAI 크레딧: 2단계에서 사용 ⚠️
    
    Args:
        card_ids: 카드 ID 리스트
        overwrite: 덮어쓰기 여부
        start_id: 시작 ID
        end_id: 종료 ID
    
    Returns:
        전체 동기화 결과
    """
    try:
        if not all([card_client, embedding_generator]):
            raise HTTPException(
                status_code=503,
                detail="동기화 서비스를 사용할 수 없습니다."
            )
        
        # card_ids가 없으면 범위 생성
        if not card_ids:
            card_ids = list(range(start_id, end_id + 1))
            print(f"📋 카드 ID 범위: {start_id}~{end_id} ({len(card_ids)}개)")
        
        # 1단계: 데이터 수집
        print(f"🔄 1/2 단계: 카드 데이터 수집")
        fetch_results = await _fetch_cards_from_cardgorilla(card_ids, overwrite)
        
        # 성공한 카드들만 2단계로
        successful_ids = [item["card_id"] for item in fetch_results["success"]]
        
        if not successful_ids:
            return {
                "success": True,
                "message": "수집된 카드가 없어 임베딩 단계를 건너뜁니다.",
                "fetch_results": fetch_results,
                "embed_results": {"success": [], "failed": [], "skipped": []}
            }
        
        # 2단계: 임베딩 생성
        print(f"🔄 2/2 단계: 임베딩 생성 ({len(successful_ids)}개)")
        embed_results = await _embed_cards_to_chromadb(successful_ids, overwrite)
        
        return {
            "success": True,
            "message": f"전체 완료: 수집 {len(fetch_results['success'])}개, 임베딩 {len(embed_results['success'])}개",
            "summary": {
                "total_tried": len(card_ids),
                "fetch_success": len(fetch_results["success"]),
                "embed_success": len(embed_results["success"])
            },
            "fetch_results": fetch_results,
            "embed_results": embed_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"동기화 중 오류가 발생했습니다: {str(e)}"
        )


@app.post("/admin/cards/{card_id}", dependencies=[Depends(require_admin_auth)])
async def sync_single_card(card_id: int, overwrite: bool = False):
    """
    특정 카드 데이터 동기화
    
    카드고릴라 API에서 카드 정보를 가져와 압축 컨텍스트를 생성하고,
    ChromaDB에 저장합니다.
    
    Args:
        card_id: 카드 ID
        overwrite: 기존 데이터 덮어쓰기 여부
    
    Returns:
        동기화 결과
    """
    try:
        if not all([card_client, embedding_generator]):
            raise HTTPException(
                status_code=503,
                detail="카드 동기화 서비스를 사용할 수 없습니다."
            )
        
        # 1. 카드 데이터 조회 및 압축 컨텍스트 생성
        card_data = await card_client.fetch_card_detail(card_id, use_cache=not overwrite)
        
        if not card_data:
            raise HTTPException(
                status_code=404,
                detail=f"카드를 찾을 수 없거나 단종된 카드입니다. (card_id={card_id})"
            )
        
        # 2. ChromaDB에 추가
        embedding_generator.add_card(card_data, overwrite=overwrite)
        
        return {
            "success": True,
            "card_id": card_id,
            "card_name": card_data["meta"]["name"],
            "issuer": card_data["meta"]["issuer"],
            "message": "카드 동기화 완료"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"카드 동기화 중 오류가 발생했습니다: {str(e)}"
        )


@app.delete("/admin/cards/reset", dependencies=[Depends(require_admin_auth)])
async def reset_vector_db():
    """
    벡터 DB 초기화 (모든 데이터 삭제)
    
    ⚠️ 주의: 이 작업은 되돌릴 수 없습니다!
    ChromaDB 컬렉션의 모든 카드 데이터를 삭제합니다.
    
    Returns:
        초기화 결과
    """
    try:
        if not embedding_generator:
            raise HTTPException(
                status_code=503,
                detail="임베딩 서비스를 사용할 수 없습니다."
            )
        
        collection = embedding_generator.collection
        
        # 현재 데이터 수 확인
        count_before = collection.count()
        
        # 컬렉션 삭제 및 재생성
        collection_name = embedding_generator.collection_name
        embedding_generator.chroma_client.delete_collection(name=collection_name)
        
        # 새 컬렉션 생성
        embedding_generator.collection = embedding_generator.chroma_client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        # vector_store도 재초기화
        global vector_store
        if vector_store:
            vector_store.collection = embedding_generator.collection
        
        return {
            "success": True,
            "message": "벡터 DB가 초기화되었습니다.",
            "deleted_documents": count_before,
            "collection_name": collection_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"벡터 DB 초기화 중 오류가 발생했습니다: {str(e)}"
        )
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
