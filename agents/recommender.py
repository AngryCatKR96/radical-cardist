"""
추천 Agent

여러 후보 카드 중에서 최종 1장을 선택합니다.
정량적 점수 계산과 타이브레이커를 통해 최적의 카드를 선정합니다.
"""

from typing import Dict, List, Optional
from data_collection.data_parser import load_compressed_context


class Recommender:
    """추천 Agent"""
    
    def __init__(self):
        pass
    
    def select_best_card(
        self,
        analysis_results: List[Dict],
        user_preferences: Optional[Dict] = None
    ) -> Dict:
        """
        최종 1장 선택
        
        Args:
            analysis_results: 혜택 분석 결과 리스트
            user_preferences: 사용자 선호사항 (선택적)
        
        Returns:
            선택된 카드 정보 및 점수 breakdown
        """
        if not analysis_results:
            raise ValueError("분석 결과가 없습니다")
        
        if user_preferences is None:
            user_preferences = {}
        
        # 각 카드에 대해 점수 계산
        scored_cards = []
        
        for result in analysis_results:
            card_id = result.get("card_id")
            if not card_id:
                continue
            
            # 카드 메타데이터 로드
            card_data = load_compressed_context(card_id)
            if not card_data:
                continue
            
            meta = card_data.get("meta", {})
            conditions = card_data.get("conditions", {})
            fees = card_data.get("fees", {})
            
            # 연회비 추출
            annual_fee = self._extract_annual_fee(fees.get("annual_detail", ""))
            
            # 점수 계산
            annual_savings = result.get("annual_savings", 0)
            conditions_met = result.get("conditions_met", False)
            
            # 조건 미충족 시 패널티
            if not conditions_met:
                annual_savings = 0  # 조건 미충족 시 혜택 없음
            
            # 순 혜택 (연 절약액 - 연회비)
            net_benefit = annual_savings - annual_fee
            
            # 커버리지 보너스 (카테고리별 절약액이 있는 카테고리 수)
            category_breakdown = result.get("category_breakdown", {})
            coverage_bonus = len([v for v in category_breakdown.values() if v > 0])
            
            # 패널티
            penalties = 0
            
            # 경고가 많으면 패널티
            warnings = result.get("warnings", [])
            if len(warnings) > 2:
                penalties += 0.5
            
            # 최종 점수
            final_score = net_benefit + coverage_bonus - penalties
            
            scored_cards.append({
                "card_id": card_id,
                "name": meta.get("name", ""),
                "annual_savings": annual_savings,
                "annual_fee": annual_fee,
                "net_benefit": net_benefit,
                "coverage_bonus": coverage_bonus,
                "penalties": penalties,
                "final_score": final_score,
                "conditions_met": conditions_met,
                "prev_month_min": conditions.get("prev_month_min", 0),
                "warnings": warnings,
                "category_breakdown": category_breakdown
            })
        
        if not scored_cards:
            raise ValueError("점수 계산 가능한 카드가 없습니다")
        
        # 점수 순 정렬
        scored_cards.sort(key=lambda x: x["final_score"], reverse=True)
        
        # 동점 처리 (타이브레이커)
        top_score = scored_cards[0]["final_score"]
        top_cards = [c for c in scored_cards if c["final_score"] == top_score]
        
        if len(top_cards) > 1:
            # 타이브레이커 1: 연회비 낮은 순
            top_cards.sort(key=lambda x: x["annual_fee"])
            
            # 타이브레이커 2: 전월실적 낮은 순
            if len([c for c in top_cards if c["annual_fee"] == top_cards[0]["annual_fee"]]) > 1:
                top_cards.sort(key=lambda x: x["prev_month_min"])
            
            # 타이브레이커 3: 사용자 선호도
            if user_preferences:
                prefer_types = user_preferences.get("prefer_types", [])
                if prefer_types:
                    type_map = {"credit": "C", "debit": "D"}
                    for prefer_type in prefer_types:
                        prefer_type_code = type_map.get(prefer_type)
                        if prefer_type_code:
                            preferred = [c for c in top_cards if self._get_card_type(c["card_id"]) == prefer_type_code]
                            if preferred:
                                top_cards = preferred
                                break
        
        selected = top_cards[0]
        
        return {
            "selected_card": selected["card_id"],
            "name": selected["name"],
            "score_breakdown": {
                "net_benefit": selected["net_benefit"],
                "coverage_bonus": selected["coverage_bonus"],
                "penalties": selected["penalties"],
                "final_score": selected["final_score"]
            },
            "annual_savings": selected["annual_savings"],
            "annual_fee": selected["annual_fee"],
            "conditions_met": selected["conditions_met"],
            "warnings": selected["warnings"],
            "category_breakdown": selected["category_breakdown"]
        }
    
    def _extract_annual_fee(self, fee_detail: str) -> int:
        """
        연회비 문자열에서 숫자 추출
        
        Args:
            fee_detail: 연회비 상세 문자열
        
        Returns:
            연회비 (원)
        """
        import re
        
        if not fee_detail:
            return 0
        
        # 숫자 패턴 찾기
        matches = re.findall(r'(\d{1,3}(?:,\d{3})*)', fee_detail)
        if matches:
            # 첫 번째 숫자 사용
            fee_str = matches[0].replace(',', '')
            try:
                return int(fee_str)
            except:
                pass
        
        return 0
    
    def _get_card_type(self, card_id: int) -> Optional[str]:
        """
        카드 유형 조회
        
        Args:
            card_id: 카드 ID
        
        Returns:
            카드 유형 ("C", "D", "P" 등)
        """
        card_data = load_compressed_context(card_id)
        if card_data:
            return card_data.get("meta", {}).get("type")
        return None


# 사용 예시
def main():
    """테스트용 메인 함수"""
    recommender = Recommender()
    
    analysis_results = [
        {
            "card_id": 2862,
            "annual_savings": 216000,
            "conditions_met": True,
            "warnings": ["통합할인한도 초과 시 혜택 제한"],
            "category_breakdown": {"digital_payment": 18000}
        },
        {
            "card_id": 1357,
            "annual_savings": 180000,
            "conditions_met": True,
            "warnings": [],
            "category_breakdown": {"grocery": 15000}
        }
    ]
    
    result = recommender.select_best_card(analysis_results)
    print(f"선택된 카드: {result['name']} (card_id={result['selected_card']})")
    print(f"최종 점수: {result['score_breakdown']['final_score']}")


if __name__ == "__main__":
    main()

