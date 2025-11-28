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

class CardsData(BaseModel):
    cards: List[Card]
