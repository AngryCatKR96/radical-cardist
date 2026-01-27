from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AdminVectorStoreStatsResponse(BaseModel):
    database: str
    collection: str
    total_documents: int = 0
    documents_with_embeddings: int = 0
    doc_type_counts: Dict[str, int] = Field(default_factory=dict)


class CardMetaModel(BaseModel):
    id: Optional[int] = None
    corpCode: Optional[str] = None
    name: Optional[str] = None
    issuer: Optional[str] = None
    type: Optional[str] = None


class CardConditionsModel(BaseModel):
    prev_month_min: Optional[int] = None


class CardFeesModel(BaseModel):
    annual_basic: Optional[str] = None
    annual_detail: Optional[str] = None


class CardHintsModel(BaseModel):
    top_tags: Optional[List[str]] = None
    top_titles: Optional[List[str]] = None
    search_titles: Optional[List[str]] = None
    search_options: Optional[List[str]] = None
    brands: Optional[List[str]] = None


class BenefitHtmlItemModel(BaseModel):
    category: str
    html: str


class CardEmbeddingModel(BaseModel):
    doc_id: Optional[str] = None
    doc_type: Optional[str] = None
    text: Optional[str] = None
    embedding: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None
    # 관리자 쿼리 응답에는 score/distance가 붙을 수 있음
    score: Optional[float] = None
    distance: Optional[float] = None


class AdminCardListItemModel(BaseModel):
    card_id: int
    meta: Optional[CardMetaModel] = None
    conditions: Optional[CardConditionsModel] = None
    fees: Optional[CardFeesModel] = None
    hints: Optional[CardHintsModel] = None
    is_discon: Optional[bool] = None
    updated_at: Optional[datetime] = None
    embeddings_count: Optional[int] = None


class AdminCardListResponseModel(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[AdminCardListItemModel] = Field(default_factory=list)


class AdminCardDetailModel(BaseModel):
    card_id: int
    meta: Optional[CardMetaModel] = None
    conditions: Optional[CardConditionsModel] = None
    fees: Optional[CardFeesModel] = None
    hints: Optional[CardHintsModel] = None
    is_discon: Optional[bool] = None
    benefits_html: Optional[List[BenefitHtmlItemModel]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    embeddings: Optional[List[CardEmbeddingModel]] = None
    embeddings_count: Optional[int] = None


class AdminVectorQueryRequest(BaseModel):
    query_text: str = Field(..., min_length=3)
    filters: Optional[Dict[str, Any]] = None
    top_k: int = Field(20, ge=1, le=200)
    doc_types: Optional[List[str]] = Field(
        default=None,
        description="예: ['summary','benefit_core','notes']",
    )
    doc_type_weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="예: {'summary': 1.2, 'benefit_core': 1.0, 'notes': 0.7}",
    )
    explain: bool = Field(
        default=True,
        description="True면 raw_score/adjusted_score/keyword_overlap 등을 포함",
    )

