"""
자연어 입력 파서 Agent - LangChain 기반

사용자의 자연어 입력을 구조화된 UserIntent로 변환합니다.
LangChain with_structured_output()을 사용하여 정확한 구조화를 수행합니다.
"""

import json
import os
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()


# Pydantic 모델 정의
class SpendingDetail(BaseModel):
    """카테고리별 지출 상세"""
    amount: float = Field(description="월 지출 금액 (원). 명시되지 않으면 0")
    merchants: List[str] = Field(default_factory=list, description="주로 이용하는 가맹점/서비스")
    payment_methods: List[str] = Field(default_factory=list, description="주로 사용하는 결제 수단")
    notes: Optional[str] = Field(default=None, description="추가 정보")


class Preferences(BaseModel):
    """사용자 선호사항"""
    card_count_preference: Optional[str] = Field(default=None, description="원하는 카드 개수")
    max_annual_fee: Optional[float] = Field(default=None, description="최대 연회비 (원)")
    prefer_types: List[str] = Field(default_factory=list, description="선호하는 카드 유형")
    prefer_brands: List[str] = Field(default_factory=list, description="선호하는 브랜드")
    exclude_banks: List[str] = Field(default_factory=list, description="제외하고 싶은 발급사")
    only_online: Optional[bool] = Field(default=None, description="온라인 전용 카드만 원하는지 여부")


class Constraints(BaseModel):
    """제약 조건"""
    pre_month_spending_estimate: Optional[float] = Field(default=None, description="예상 전월 실적 (원)")
    must_include_categories: List[str] = Field(default_factory=list, description="반드시 포함되어야 하는 카테고리")
    must_exclude_categories: List[str] = Field(default_factory=list, description="제외해야 하는 카테고리")


class Filters(BaseModel):
    """벡터 검색 필터"""
    annual_fee_max: Optional[float] = Field(default=None, description="최대 연회비 필터 (원)")
    pre_month_min_max: Optional[float] = Field(default=None, description="최대 전월실적 조건 (원)")
    type: Optional[str] = Field(default=None, description="카드 유형 필터 (credit/debit/both)")
    only_online: Optional[bool] = Field(default=None, description="온라인 전용 필터")


class UserIntent(BaseModel):
    """구조화된 사용자 의도"""
    spending: Dict[str, SpendingDetail] = Field(
        description="카테고리별 월 예상 지출. 사용자가 언급한 모든 소비 카테고리를 반드시 포함"
    )
    subscriptions: List[str] = Field(
        default_factory=list,
        description="구독 중인 서비스 목록"
    )
    preferences: Optional[Preferences] = Field(
        default=None,
        description="사용자 선호사항"
    )
    constraints: Optional[Constraints] = Field(
        default=None,
        description="제약 조건"
    )
    confidence: float = Field(
        ge=0,
        le=1,
        description="추출 신뢰도 (0-1)"
    )
    uncertainties: List[str] = Field(
        default_factory=list,
        description="불확실한 부분이나 모호한 정보"
    )
    query_text: str = Field(
        description="벡터 검색용 자연어 요약"
    )
    filters: Filters = Field(
        description="메타데이터 필터"
    )


class InputParser:
    """자연어 입력 파서 - LangChain 기반"""

    def __init__(self):
        # LangChain ChatOpenAI 초기화
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=1.0,
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )

        # Structured output으로 변환 (function_calling 방식 사용)
        self.structured_llm = self.llm.with_structured_output(UserIntent, method="function_calling")

        # 프롬프트 템플릿 정의
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """당신은 사용자의 자연어 소비 패턴 입력을 구조화된 데이터로 변환하는 전문가입니다.

**중요 규칙**:
1. **spending 객체는 절대 비어있으면 안 됩니다**. 사용자가 언급한 모든 소비 카테고리를 반드시 포함하세요.
2. 금액이 명시되지 않았어도 카테고리만 언급되면 spending에 추가하고 amount=0으로 설정하세요.
3. 카테고리 매핑 예시:
   - "스타벅스 자주 가" → cafe: {{amount: 0, merchants: ["스타벅스"]}}
   - "쿠팡에서 장보거나 네이버 쇼핑" → online_shopping: {{amount: 0, merchants: ["쿠팡", "네이버쇼핑"]}}, grocery: {{amount: 0, merchants: ["쿠팡"]}}
   - "해외여행" → travel: {{amount: 0}}
   - "배달 자주 시켜먹어" → delivery: {{amount: 0}}
4. 사용 가능한 카테고리: online_shopping, grocery, cafe, coffee, travel, delivery, digital_payment, convenience_store, dining, fuel, transportation, subscription_video, subscription_music 등
5. spending이 비어있다면 must_include_categories를 참고하여 채워 넣으세요.
6. '연회비 낮을수록 좋음'은 preferences에, '연회비 절대 2만원 이하'는 filters에 넣으세요."""),
            ("user", "{user_input}")
        ])

    def parse(self, user_input: str) -> Dict:
        """
        자연어 입력을 구조화된 UserIntent로 변환 - LangChain 사용

        Args:
            user_input: 사용자 자연어 입력

        Returns:
            UserIntent Dict
        """
        try:
            # LangChain 체인 구성 (LCEL)
            chain = self.prompt | self.structured_llm

            # 실행
            result = chain.invoke({"user_input": user_input})

            # Pydantic 모델을 Dict로 변환
            return result.model_dump()

        except Exception as e:
            raise ValueError(f"입력 파싱 실패: {e}")

    def _normalize_amount(self, amount_str: str) -> int:
        """
        금액 문자열을 숫자로 변환

        Args:
            amount_str: 금액 문자열 (예: "30만원", "100,000원")

        Returns:
            금액 (원 단위)
        """
        # 간단한 휴리스틱 (LLM이 이미 변환해주지만 백업용)
        amount_str = amount_str.replace(",", "").replace("원", "").strip()

        if "만" in amount_str:
            num = float(amount_str.replace("만", ""))
            return int(num * 10000)
        elif "천" in amount_str:
            num = float(amount_str.replace("천", ""))
            return int(num * 1000)
        else:
            try:
                return int(float(amount_str))
            except:
                return 0


# 사용 예시
def main():
    """테스트용 메인 함수"""
    parser = InputParser()

    user_input = "마트 30만원, 넷플릭스/유튜브 구독, 간편결제 자주 씀. 연회비 2만원 이하, 체크카드 선호."

    result = parser.parse(user_input)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
