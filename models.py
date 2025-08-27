from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Union
from decimal import Decimal

class Benefit(BaseModel):
    category: str
    type: str  # cashback, discount, point
    rate: float
    monthly_limit: int
    min_purchase: int

class Conditions(BaseModel):
    prev_month_min: int
    benefit_cap: int

class Card(BaseModel):
    id: str
    name: str
    bank: str
    annual_fee: int
    benefits: List[Benefit]
    conditions: Conditions

class SpendingBreakdown(BaseModel):
    온라인쇼핑: Optional[int] = 0
    마트: Optional[int] = 0
    편의점: Optional[int] = 0
    카페: Optional[int] = 0
    대중교통: Optional[int] = 0
    주유: Optional[int] = 0
    배달앱: Optional[int] = 0
    구독서비스: Optional[int] = 0
    간편결제: Optional[int] = 0

class RecommendationRequest(BaseModel):
    monthly_spending: int = Field(..., description="월 총 소비 금액")
    spending_breakdown: SpendingBreakdown
    subscriptions: List[str] = Field(default=[], description="구독 서비스 목록")

class CardRecommendation(BaseModel):
    card: Card
    assigned_categories: Dict[str, int]
    monthly_benefit: int
    annual_benefit: int
    usage_strategy: str

class RecommendationResponse(BaseModel):
    recommendation_text: str
    selected_cards: List[CardRecommendation]
    monthly_savings: int
    annual_savings: int
    usage_strategy: str
    total_annual_fee: int
    net_annual_savings: int

class CardsData(BaseModel):
    cards: List[Card]
