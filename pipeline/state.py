"""
LangGraph State 정의

카드 추천 파이프라인의 각 단계에서 사용되는 상태를 정의합니다.
"""

from typing import TypedDict, List, Dict, Optional


class CardRecommendationState(TypedDict):
    """카드 추천 파이프라인 상태"""

    # ===== Input =====
    user_input: str

    # ===== Stage 1: Input Parser =====
    user_intent: Optional[Dict]
    parsing_error: Optional[str]

    # ===== Stage 2: Vector Search =====
    candidate_cards: List[Dict]
    search_error: Optional[str]

    # ===== Stage 3: Benefit Analysis =====
    analysis_results: List[Dict]
    analysis_error: Optional[str]

    # ===== Stage 4: Recommendation =====
    selected_card: Optional[Dict]
    recommendation_error: Optional[str]

    # ===== Stage 5: Response Generation =====
    final_response: Optional[str]
    response_error: Optional[str]

    # ===== Metadata =====
    intermediate_steps: List[Dict]  # 디버깅 및 추적용
