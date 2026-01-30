"""
LangGraph 파이프라인 - 카드 추천 워크플로우

5단계 파이프라인을 LangGraph로 오케스트레이션합니다:
1. Input Parser - 사용자 입력 파싱
2. Vector Search - 후보 카드 검색
3. Benefit Analysis - 혜택 분석
4. Recommendation - 최종 카드 선택
5. Response Generation - 응답 생성
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from pipeline.state import CardRecommendationState
from agents.input_parser import InputParser
from agents.benefit_analyzer import BenefitAnalyzer
from agents.recommender import Recommender
from agents.response_generator import ResponseGenerator
from vector_store.vector_store import CardVectorStore
from data_collection.data_parser import load_compressed_context

load_dotenv()


# ===== Node 1: Input Parser =====
def parse_input_node(state: CardRecommendationState) -> Dict[str, Any]:
    """
    사용자 입력을 파싱하여 구조화된 의도로 변환
    """
    try:
        parser = InputParser()
        user_intent = parser.parse(state["user_input"])

        return {
            "user_intent": user_intent,
            "parsing_error": None,
            "intermediate_steps": state.get("intermediate_steps", []) + [{
                "stage": "parse_input",
                "success": True,
                "output": user_intent
            }]
        }

    except Exception as e:
        return {
            "parsing_error": f"입력 파싱 실패: {str(e)}",
            "intermediate_steps": state.get("intermediate_steps", []) + [{
                "stage": "parse_input",
                "success": False,
                "error": str(e)
            }]
        }


# ===== Node 2: Vector Search =====
def vector_search_node(state: CardRecommendationState) -> Dict[str, Any]:
    """
    벡터 검색으로 후보 카드 검색
    """
    try:
        user_intent = state.get("user_intent")
        if not user_intent:
            raise ValueError("user_intent가 없습니다")

        # VectorStore 초기화
        vector_store = CardVectorStore()

        # 쿼리 텍스트와 필터 추출
        query_text = user_intent.get("query_text", "")
        filters = user_intent.get("filters", {})

        # 벡터 검색 실행
        candidate_cards = vector_store.search_cards(
            query_text=query_text,
            filters=filters,
            top_m=5,
            evidence_per_card=3
        )

        return {
            "candidate_cards": candidate_cards,
            "search_error": None,
            "intermediate_steps": state.get("intermediate_steps", []) + [{
                "stage": "vector_search",
                "success": True,
                "num_candidates": len(candidate_cards)
            }]
        }

    except Exception as e:
        return {
            "candidate_cards": [],
            "search_error": f"벡터 검색 실패: {str(e)}",
            "intermediate_steps": state.get("intermediate_steps", []) + [{
                "stage": "vector_search",
                "success": False,
                "error": str(e)
            }]
        }


# ===== Node 3: Benefit Analysis =====
async def benefit_analysis_node(state: CardRecommendationState) -> Dict[str, Any]:
    """
    후보 카드들의 혜택 분석
    """
    try:
        user_intent = state.get("user_intent")
        candidate_cards = state.get("candidate_cards", [])

        if not user_intent:
            raise ValueError("user_intent가 없습니다")

        if not candidate_cards:
            raise ValueError("후보 카드가 없습니다")

        # BenefitAnalyzer 초기화
        analyzer = BenefitAnalyzer(model="gpt-5-mini")

        # 배치 분석 실행
        analysis_results = await analyzer.analyze_batch(
            user_pattern=user_intent,
            card_contexts=candidate_cards
        )

        return {
            "analysis_results": analysis_results,
            "analysis_error": None,
            "intermediate_steps": state.get("intermediate_steps", []) + [{
                "stage": "benefit_analysis",
                "success": True,
                "num_analyzed": len(analysis_results)
            }]
        }

    except Exception as e:
        return {
            "analysis_results": [],
            "analysis_error": f"혜택 분석 실패: {str(e)}",
            "intermediate_steps": state.get("intermediate_steps", []) + [{
                "stage": "benefit_analysis",
                "success": False,
                "error": str(e)
            }]
        }


# ===== Node 4: Recommendation =====
def recommendation_node(state: CardRecommendationState) -> Dict[str, Any]:
    """
    분석된 카드 중 최적의 카드 선택
    """
    try:
        analysis_results = state.get("analysis_results", [])
        user_intent = state.get("user_intent")

        if not analysis_results:
            raise ValueError("분석 결과가 없습니다")

        # Recommender 초기화
        recommender = Recommender()

        # 사용자 선호도 추출
        user_preferences = user_intent.get("preferences") if user_intent else None

        # 최종 카드 선택
        selected_card = recommender.select_best_card(
            analysis_results=analysis_results,
            user_preferences=user_preferences
        )

        return {
            "selected_card": selected_card,
            "recommendation_error": None,
            "intermediate_steps": state.get("intermediate_steps", []) + [{
                "stage": "recommendation",
                "success": True,
                "selected_card_id": selected_card.get("selected_card")
            }]
        }

    except Exception as e:
        return {
            "selected_card": None,
            "recommendation_error": f"카드 선택 실패: {str(e)}",
            "intermediate_steps": state.get("intermediate_steps", []) + [{
                "stage": "recommendation",
                "success": False,
                "error": str(e)
            }]
        }


# ===== Node 5: Response Generation =====
def response_generation_node(state: CardRecommendationState) -> Dict[str, Any]:
    """
    최종 추천 응답 생성
    """
    try:
        selected_card = state.get("selected_card")
        user_intent = state.get("user_intent")
        analysis_results = state.get("analysis_results", [])

        if not selected_card:
            raise ValueError("선택된 카드가 없습니다")

        # 선택된 카드의 분석 결과 찾기
        card_id = selected_card.get("selected_card")
        analysis = next(
            (a for a in analysis_results if a.get("card_id") == card_id),
            None
        )

        if not analysis:
            raise ValueError(f"카드 ID {card_id}의 분석 결과를 찾을 수 없습니다")

        # 카드 메타데이터 로드
        card_metadata = load_compressed_context(card_id)
        if not card_metadata:
            raise ValueError(f"카드 ID {card_id}의 메타데이터를 찾을 수 없습니다")

        # ResponseGenerator 초기화
        generator = ResponseGenerator(model="gpt-4o-mini")

        # 응답 생성
        final_response = generator.generate(
            selected_card=selected_card,
            user_pattern=user_intent,
            analysis=analysis,
            card_metadata=card_metadata
        )

        return {
            "final_response": final_response,
            "response_error": None,
            "intermediate_steps": state.get("intermediate_steps", []) + [{
                "stage": "response_generation",
                "success": True
            }]
        }

    except Exception as e:
        return {
            "final_response": None,
            "response_error": f"응답 생성 실패: {str(e)}",
            "intermediate_steps": state.get("intermediate_steps", []) + [{
                "stage": "response_generation",
                "success": False,
                "error": str(e)
            }]
        }


# ===== Conditional Edge Functions =====
def check_parsing_error(state: CardRecommendationState) -> str:
    """파싱 에러 확인"""
    return "error" if state.get("parsing_error") else "continue"


def check_search_error(state: CardRecommendationState) -> str:
    """검색 에러 확인"""
    return "error" if state.get("search_error") else "continue"


def check_analysis_error(state: CardRecommendationState) -> str:
    """분석 에러 확인"""
    return "error" if state.get("analysis_error") else "continue"


def check_recommendation_error(state: CardRecommendationState) -> str:
    """추천 에러 확인"""
    return "error" if state.get("recommendation_error") else "continue"


# ===== Graph Builder =====
def build_recommendation_graph():
    """
    카드 추천 LangGraph 워크플로우 구성

    Returns:
        컴파일된 LangGraph 워크플로우
    """
    # StateGraph 생성
    workflow = StateGraph(CardRecommendationState)

    # 노드 추가
    workflow.add_node("parse_input", parse_input_node)
    workflow.add_node("vector_search", vector_search_node)
    workflow.add_node("benefit_analysis", benefit_analysis_node)
    workflow.add_node("recommendation", recommendation_node)
    workflow.add_node("response_generation", response_generation_node)

    # 엔트리 포인트 설정
    workflow.set_entry_point("parse_input")

    # 조건부 엣지 추가 (에러 처리)
    workflow.add_conditional_edges(
        "parse_input",
        check_parsing_error,
        {
            "error": END,
            "continue": "vector_search"
        }
    )

    workflow.add_conditional_edges(
        "vector_search",
        check_search_error,
        {
            "error": END,
            "continue": "benefit_analysis"
        }
    )

    workflow.add_conditional_edges(
        "benefit_analysis",
        check_analysis_error,
        {
            "error": END,
            "continue": "recommendation"
        }
    )

    workflow.add_conditional_edges(
        "recommendation",
        check_recommendation_error,
        {
            "error": END,
            "continue": "response_generation"
        }
    )

    # 최종 엣지
    workflow.add_edge("response_generation", END)

    # 체크포인팅 추가 (디버깅 및 재실행 지원)
    memory = MemorySaver()

    # 컴파일
    return workflow.compile(checkpointer=memory)


# ===== 사용 예시 =====
async def main():
    """테스트용 메인 함수"""
    graph = build_recommendation_graph()

    initial_state = {
        "user_input": "배달앱을 자주 쓰는데 한 달에 30만원 정도 써. 추천 좀",
        "intermediate_steps": []
    }

    # 실행
    config = {"configurable": {"thread_id": "test_001"}}
    result = await graph.ainvoke(initial_state, config)

    # 결과 출력
    print("=== 파이프라인 실행 결과 ===\n")

    if result.get("parsing_error"):
        print(f"❌ 파싱 에러: {result['parsing_error']}")
        return

    if result.get("search_error"):
        print(f"❌ 검색 에러: {result['search_error']}")
        return

    if result.get("analysis_error"):
        print(f"❌ 분석 에러: {result['analysis_error']}")
        return

    if result.get("recommendation_error"):
        print(f"❌ 추천 에러: {result['recommendation_error']}")
        return

    if result.get("response_error"):
        print(f"❌ 응답 생성 에러: {result['response_error']}")
        return

    # 성공 시 결과 출력
    print(f"✅ 선택된 카드: {result['selected_card']['name']}")
    print(f"✅ 예상 연 절약액: {result['selected_card']['annual_savings']:,}원")
    print(f"\n{result['final_response']}")

    # 중간 단계 출력
    print("\n=== 중간 단계 ===")
    for step in result.get("intermediate_steps", []):
        status = "✅" if step.get("success") else "❌"
        print(f"{status} {step['stage']}")


if __name__ == "__main__":
    asyncio.run(main())
