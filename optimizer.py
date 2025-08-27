import json
from typing import List, Dict, Tuple, Optional, Union
from models import Card, SpendingBreakdown, CardRecommendation
import numpy as np

class CardOptimizer:
    def __init__(self, cards: List[Card]):
        self.cards = cards
        self.category_mapping = {
            "넷플릭스": "구독서비스",
            "유튜브프리미엄": "구독서비스", 
            "스포티파이": "구독서비스",
            "디즈니플러스": "구독서비스",
            "왓챠": "구독서비스",
            "티빙": "구독서비스"
        }
    
    def optimize_card_combination(self, spending_breakdown: SpendingBreakdown, 
                                subscriptions: List[str], monthly_spending: int) -> List[CardRecommendation]:
        """최적의 카드 조합을 찾고 각 카드에 카테고리를 할당합니다."""
        
        # 구독 서비스 금액 계산 (구독료는 월 15,000원으로 가정)
        subscription_amount = len(subscriptions) * 15000
        spending_dict = spending_breakdown.model_dump()
        spending_dict["구독서비스"] = subscription_amount
        
        # 사용 가능한 카드들 필터링 (전월 실적 조건 확인)
        available_cards = [card for card in self.cards if monthly_spending >= card.conditions.prev_month_min]
        
        if not available_cards:
            # 조건을 만족하는 카드가 없으면 조건을 낮춰서 재시도
            available_cards = [card for card in self.cards if monthly_spending >= card.conditions.prev_month_min * 0.5]
        
        if not available_cards:
            # 여전히 없으면 모든 카드 사용
            available_cards = self.cards
        
        # 카드 조합 최적화 (2-3개 카드)
        best_combination = self._find_best_combination(available_cards, spending_dict, monthly_spending)
        
        return best_combination
    
    def _find_best_combination(self, available_cards: List[Card], 
                              spending_dict: Dict[str, int], 
                              monthly_spending: int) -> List[CardRecommendation]:
        """최적의 카드 조합을 찾습니다."""
        
        best_score = -1
        best_combination = []
        
        # 2-3개 카드 조합 시도
        for num_cards in [2, 3]:
            if len(available_cards) < num_cards:
                continue
                
            # 가능한 모든 조합 생성
            import itertools
            for card_combination in itertools.combinations(available_cards, num_cards):
                combination_score, card_assignments = self._evaluate_combination(
                    list(card_combination), spending_dict, monthly_spending
                )
                
                if combination_score > best_score:
                    best_score = combination_score
                    best_combination = card_assignments
        
        return best_combination
    
    def _evaluate_combination(self, cards: List[Card], 
                            spending_dict: Dict[str, int], 
                            monthly_spending: int) -> Tuple[float, List[CardRecommendation]]:
        """특정 카드 조합의 점수를 계산합니다."""
        
        # 각 카드에 카테고리 할당
        category_assignments = self._assign_categories_to_cards(cards, spending_dict)
        
        # 총 혜택 계산
        total_benefit = 0
        total_annual_fee = 0
        card_recommendations = []
        
        for card in cards:
            assigned_categories = category_assignments.get(card.id, {})
            monthly_benefit = self._calculate_card_benefit(card, assigned_categories)
            annual_benefit = monthly_benefit * 12
            
            total_benefit += annual_benefit
            total_annual_fee += card.annual_fee
            
            # 사용 전략 생성
            usage_strategy = self._generate_usage_strategy(card, assigned_categories)
            
            card_recommendations.append(CardRecommendation(
                card=card,
                assigned_categories=assigned_categories,
                monthly_benefit=monthly_benefit,
                annual_benefit=annual_benefit,
                usage_strategy=usage_strategy
            ))
        
        # ROI 점수 계산 (혜택 - 연회비) / 연회비
        if total_annual_fee > 0:
            roi_score = (total_benefit - total_annual_fee) / total_annual_fee
        else:
            roi_score = total_benefit / 1000  # 연회비가 0인 경우
        
        return roi_score, card_recommendations
    
    def _assign_categories_to_cards(self, cards: List[Card], 
                                  spending_dict: Dict[str, int]) -> Dict[str, Dict[str, int]]:
        """각 카드에 최적의 카테고리를 할당합니다."""
        
        category_assignments = {card.id: {} for card in cards}
        remaining_spending = spending_dict.copy()
        
        # 각 카드별로 가장 유리한 카테고리부터 할당
        for card in cards:
            card_assignments = {}
            
            # 카드의 혜택을 혜택률 순으로 정렬
            sorted_benefits = sorted(card.benefits, key=lambda x: x.rate, reverse=True)
            
            for benefit in sorted_benefits:
                category = benefit.category
                if category in remaining_spending and remaining_spending[category] > 0:
                    # 할당할 금액 결정
                    assign_amount = min(
                        remaining_spending[category],
                        benefit.monthly_limit,
                        remaining_spending[category]
                    )
                    
                    if assign_amount >= benefit.min_purchase:
                        card_assignments[category] = assign_amount
                        remaining_spending[category] -= assign_amount
                        
                        # 카드의 월 한도 확인
                        if self._calculate_card_benefit(card, card_assignments) >= card.conditions.benefit_cap:
                            break
            
            if card_assignments:
                category_assignments[card.id] = card_assignments
        
        return category_assignments
    
    def _calculate_card_benefit(self, card: Card, assigned_categories: Dict[str, int]) -> int:
        """카드의 월 혜택을 계산합니다."""
        total_benefit = 0
        
        for category, amount in assigned_categories.items():
            # 해당 카테고리의 혜택 찾기
            benefit = next((b for b in card.benefits if b.category == category), None)
            if benefit:
                # 혜택 계산 (최소 구매 금액 확인)
                if amount >= benefit.min_purchase:
                    category_benefit = int(amount * benefit.rate / 100)
                    # 월 한도 확인
                    category_benefit = min(category_benefit, benefit.monthly_limit)
                    total_benefit += category_benefit
        
        # 카드 전체 혜택 한도 확인
        return min(total_benefit, card.conditions.benefit_cap)
    
    def _generate_usage_strategy(self, card: Card, assigned_categories: Dict[str, int]) -> str:
        """카드별 사용 전략을 생성합니다."""
        if not assigned_categories:
            return f"{card.name}은 현재 조건에서 사용하지 않습니다."
        
        strategy_parts = []
        for category, amount in assigned_categories.items():
            benefit = next((b for b in card.benefits if b.category == category), None)
            if benefit:
                monthly_benefit = int(amount * benefit.rate / 100)
                strategy_parts.append(f"{category} {amount:,}원 → 월 {monthly_benefit:,}원 적립")
        
        return f"{card.name}: " + ", ".join(strategy_parts)
    
    def calculate_total_savings(self, card_recommendations: List[CardRecommendation]) -> tuple[int, int, int, int]:
        """총 절약 금액을 계산합니다."""
        monthly_savings = sum(rec.monthly_benefit for rec in card_recommendations)
        annual_savings = monthly_savings * 12
        total_annual_fee = sum(rec.card.annual_fee for rec in card_recommendations)
        net_annual_savings = annual_savings - total_annual_fee
        
        return monthly_savings, annual_savings, total_annual_fee, net_annual_savings
    
    def generate_recommendation_text(self, card_recommendations: List[CardRecommendation], 
                                   monthly_savings: int, annual_savings: int) -> str:
        """추천 결과를 텍스트로 생성합니다."""
        text_parts = []
        
        for i, rec in enumerate(card_recommendations, 1):
            text_parts.append(f"{i}. {rec.usage_strategy}")
        
        text_parts.append(f"\n총 월 {monthly_savings:,}원, 연 {annual_savings:,}원 절약 가능합니다.")
        
        return "\n".join(text_parts)
