"""
응답 생성 Agent

템플릿 기반으로 추천 결과를 사용자 친화적인 자연어로 변환합니다.
"""

from typing import Dict, Optional, List
from data_collection.data_parser import load_compressed_context


# ============================================
# 카테고리 메타데이터
# ============================================

CATEGORY_METADATA = {
    "digital_payment": {
        "label": "간편결제/페이",
        "description": "네이버페이, 카카오페이, 토스페이 등 간편결제 서비스",
        "strategy": "온라인 쇼핑, 배달 앱에서 간편결제로 통합하여 사용",
        "examples": "네이버페이, 카카오페이, 토스페이"
    },
    "grocery": {
        "label": "마트/식료품",
        "description": "대형마트, 슈퍼마켓, 식료품점",
        "strategy": "대형마트에서 주 1회 장보기 시 혜택 극대화",
        "examples": "이마트, 홈플러스, 롯데마트, 쿠팡"
    },
    "cafe": {
        "label": "카페",
        "description": "커피전문점 및 음료 매장",
        "strategy": "출퇴근 시 커피 구매로 매일 혜택 누리기",
        "examples": "스타벅스, 이디야, 메가커피, 커피빈"
    },
    "coffee": {
        "label": "카페",
        "description": "커피전문점 및 음료 매장",
        "strategy": "출퇴근 시 커피 구매로 매일 혜택 누리기",
        "examples": "스타벅스, 이디야, 메가커피, 커피빈"
    },
    "convenience_store": {
        "label": "편의점",
        "description": "GS25, CU, 세븐일레븐 등 편의점",
        "strategy": "소액 결제도 혜택 대상이면 자주 사용하기",
        "examples": "GS25, CU, 세븐일레븐, 이마트24"
    },
    "dining": {
        "label": "외식",
        "description": "음식점, 레스토랑, 패밀리 레스토랑",
        "strategy": "회식, 데이트 등 외식 비용 절감",
        "examples": "일반 음식점, 레스토랑, 패밀리 레스토랑"
    },
    "delivery": {
        "label": "배달앱",
        "description": "배달의민족, 쿠팡이츠 등 배달 서비스",
        "strategy": "배달 주문 시 간편결제와 중복 적용 가능한지 확인",
        "examples": "배달의민족, 쿠팡이츠, 요기요"
    },
    "subscription_video": {
        "label": "OTT 구독",
        "description": "넷플릭스, 유튜브 프리미엄 등 영상 스트리밍",
        "strategy": "정기 결제는 자동으로 혜택 적용되어 편리",
        "examples": "넷플릭스, 유튜브 프리미엄, 왓챠, 디즈니+"
    },
    "subscription_music": {
        "label": "음악/콘텐츠 구독",
        "description": "음악 스트리밍 및 디지털 콘텐츠",
        "strategy": "정기 구독료 자동 할인",
        "examples": "멜론, 지니뮤직, 스포티파이, 애플뮤직"
    },
    "subscription": {
        "label": "구독 서비스",
        "description": "각종 월정액 구독 서비스",
        "strategy": "정기 결제 혜택 자동 적용",
        "examples": "각종 구독 서비스"
    },
    "online_shopping": {
        "label": "온라인 쇼핑",
        "description": "인터넷 쇼핑몰, 오픈마켓",
        "strategy": "대형 쇼핑몰 이벤트 기간에 더 큰 혜택 가능",
        "examples": "쿠팡, 네이버쇼핑, 11번가, G마켓"
    },
    "travel": {
        "label": "여행/항공",
        "description": "여행사, 숙박, 항공권 예약",
        "strategy": "여행 계획 시 미리 카드로 결제하여 혜택 적용",
        "examples": "여행사, 호텔, 항공사"
    },
    "airline": {
        "label": "항공 마일리지",
        "description": "항공사 마일리지 적립 서비스",
        "strategy": "항공권 구매 및 일상 소비로 마일리지 적립",
        "examples": "대한항공, 아시아나항공"
    },
    "fuel": {
        "label": "주유",
        "description": "주유소 기름값 결제",
        "strategy": "리터당 할인 또는 청구할인 확인",
        "examples": "SK, GS칼텍스, 현대오일뱅크, S-OIL"
    },
    "transportation": {
        "label": "교통",
        "description": "지하철, 버스, 택시 등 교통비",
        "strategy": "대중교통 자주 이용하면 큰 절약",
        "examples": "지하철, 버스, 택시, SRT"
    },
    "public_utilities": {
        "label": "공과금",
        "description": "전기, 수도, 가스 등 공과금",
        "strategy": "자동이체 설정으로 편리하게 혜택 적용",
        "examples": "전기세, 수도세, 가스비"
    },
    "education": {
        "label": "교육",
        "description": "학원비, 교육비, 도서 구매",
        "strategy": "자녀 교육비나 자기계발비 절감",
        "examples": "학원, 교육기관, 서점"
    },
    "mobile_payment": {
        "label": "모바일 결제",
        "description": "모바일 간편결제 서비스",
        "strategy": "모바일 결제로 일상 소비 통합",
        "examples": "삼성페이, 애플페이, 구글페이"
    }
}


class ResponseGenerator:
    """템플릿 기반 응답 생성 Agent"""

    def __init__(self):
        """초기화 - 템플릿 기반이므로 외부 의존성 없음"""
        pass

    def generate(
        self,
        recommendation_result: Dict,
        user_pattern: Optional[Dict] = None
    ) -> str:
        """
        템플릿 기반 추천 응답 생성

        Args:
            recommendation_result: 추천 결과 Dict
                - selected_card: 카드 ID
                - annual_savings: 연 절약액
                - annual_fee: 연회비
                - score_breakdown.net_benefit: 순 혜택
                - category_breakdown: 카테고리별 월 절약액
                - warnings: 주의사항 리스트
            user_pattern: 사용자 소비 패턴 (선택적)
                - spending: 카테고리별 소비액

        Returns:
            자연어 추천 텍스트
        """
        # 1. 카드 ID 검증
        card_id = recommendation_result.get("selected_card")
        if not card_id:
            return "추천할 카드를 찾을 수 없습니다."

        # 2. 카드 데이터 로드
        card_data = load_compressed_context(card_id)
        if not card_data:
            return f"카드 정보를 불러올 수 없습니다 (card_id={card_id})"

        # 3. 메타데이터 추출
        meta = card_data.get("meta", {})
        conditions = card_data.get("conditions", {})
        category_breakdown = recommendation_result.get("category_breakdown", {})
        warnings = recommendation_result.get("warnings", [])

        # 4. 5개 섹션 생성
        header = self._generate_header(
            meta.get("name", "추천 카드"),
            meta.get("issuer", "")
        )

        reason = self._generate_recommendation_reason(
            category_breakdown,
            user_pattern
        )

        strategy = self._generate_usage_strategy(category_breakdown)

        warning = self._generate_warnings(
            warnings,
            conditions.get("prev_month_min", 0),
            conditions.get("benefit_cap")
        )

        savings = self._generate_savings_summary(
            recommendation_result.get("annual_savings", 0),
            recommendation_result.get("annual_fee", 0),
            recommendation_result.get("score_breakdown", {}).get("net_benefit", 0)
        )

        # 5. 섹션 조합
        return "\n\n".join([header, reason, strategy, warning, savings])

    # ============================================
    # 유틸리티 함수
    # ============================================

    def _format_currency(self, amount: int) -> str:
        """
        금액을 천 단위 콤마로 포맷

        Args:
            amount: 금액 (원)

        Returns:
            포맷된 문자열 (예: "216,000원")
        """
        if amount == 0:
            return "없음"
        return f"{amount:,}원"

    def _get_category_info(self, category: str) -> Dict:
        """
        카테고리 메타데이터 조회

        Args:
            category: 카테고리 키

        Returns:
            카테고리 메타데이터 (label, description, strategy, examples)
        """
        return CATEGORY_METADATA.get(category, {
            "label": category,
            "description": "",
            "strategy": "이 카테고리를 자주 사용하면 혜택을 받을 수 있습니다",
            "examples": ""
        })

    # ============================================
    # 섹션 생성 함수
    # ============================================

    def _generate_header(self, card_name: str, issuer: str) -> str:
        """
        헤더 섹션 생성

        Args:
            card_name: 카드명
            issuer: 발급사

        Returns:
            헤더 텍스트
        """
        if issuer:
            return f"**추천 카드: {card_name}** ({issuer})"
        return f"**추천 카드: {card_name}**"

    def _generate_recommendation_reason(
        self,
        category_breakdown: Dict[str, int],
        user_pattern: Optional[Dict]
    ) -> str:
        """
        추천 이유 섹션 생성

        Args:
            category_breakdown: 카테고리별 월 절약액
            user_pattern: 사용자 소비 패턴

        Returns:
            추천 이유 텍스트
        """
        if not category_breakdown:
            return "### 추천 이유\n이 카드는 다양한 소비 카테고리에서 골고루 혜택을 제공합니다."

        lines = ["### 추천 이유"]

        # 절약액 순으로 정렬 (상위 5개만)
        sorted_categories = sorted(
            category_breakdown.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        for category, monthly_savings in sorted_categories:
            cat_info = self._get_category_info(category)

            # 사용자 소비액 확인
            user_amount = None
            if user_pattern:
                spending = user_pattern.get("spending", {})
                if category in spending:
                    user_amount = spending[category].get("amount", 0)

            # 문장 생성
            if user_amount and user_amount > 0:
                line = f"- **{cat_info['label']}**에서 월 {self._format_currency(user_amount)} 사용 시, "
                line += f"월 약 {self._format_currency(monthly_savings)} 혜택을 받을 수 있습니다."
            else:
                line = f"- **{cat_info['label']}** 카테고리에서 월 약 {self._format_currency(monthly_savings)} 혜택"

            # 예시 추가
            if cat_info.get("examples"):
                line += f" ({cat_info['examples']})"

            lines.append(line)

        return "\n".join(lines)

    def _generate_usage_strategy(self, category_breakdown: Dict[str, int]) -> str:
        """
        사용 전략 섹션 생성

        Args:
            category_breakdown: 카테고리별 월 절약액

        Returns:
            사용 전략 텍스트
        """
        if not category_breakdown:
            return "### 사용 전략\n1. 일상 소비를 이 카드로 통합하여 사용하세요"

        lines = ["### 사용 전략"]

        # 상위 3개 카테고리 선택
        top_categories = sorted(
            category_breakdown.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        for i, (category, _) in enumerate(top_categories, 1):
            cat_info = self._get_category_info(category)
            strategy = cat_info.get("strategy", "이 카테고리를 자주 사용하세요")
            lines.append(f"{i}. {strategy}")

        return "\n".join(lines)

    def _generate_warnings(
        self,
        warnings: List[str],
        prev_month_min: int,
        benefit_cap: Optional[int]
    ) -> str:
        """
        주의사항 섹션 생성

        Args:
            warnings: 주의사항 리스트
            prev_month_min: 전월실적 최소액
            benefit_cap: 통합할인한도

        Returns:
            주의사항 텍스트
        """
        lines = ["### 주의사항"]

        # 분석기가 제공한 경고
        for warning in warnings:
            lines.append(f"- {warning}")

        # 전월실적 조건
        if prev_month_min > 0:
            lines.append(f"- 전월실적: {self._format_currency(prev_month_min)} 이상 사용 필요")
        else:
            lines.append("- 전월실적: 조건 없음 (사용 제한 없이 혜택 제공)")

        # 혜택 한도
        if benefit_cap and benefit_cap > 0:
            lines.append(f"- 통합할인한도: 월 {self._format_currency(benefit_cap)}")

        # 공통 제외 항목
        lines.append("- 국세, 지방세, 공과금, 아파트관리비 등은 일반적으로 할인 제외")

        return "\n".join(lines)

    def _generate_savings_summary(
        self,
        annual_savings: int,
        annual_fee: int,
        net_benefit: int
    ) -> str:
        """
        예상 절약액 섹션 생성

        Args:
            annual_savings: 연 절약액
            annual_fee: 연회비
            net_benefit: 순 혜택 (연 절약액 - 연회비)

        Returns:
            예상 절약액 텍스트
        """
        monthly_savings = annual_savings // 12 if annual_savings > 0 else 0

        lines = [
            "### 예상 절약액",
            f"- 월 예상 혜택: 약 {self._format_currency(monthly_savings)}",
            f"- 연 예상 혜택: 약 {self._format_currency(annual_savings)}",
            f"- 연회비: {self._format_currency(annual_fee)}",
            f"- **순 혜택(연회비 제외): 연 {self._format_currency(net_benefit)}**"
        ]

        return "\n".join(lines)


# 사용 예시
def main():
    """테스트용 메인 함수"""
    generator = ResponseGenerator()

    # 테스트 케이스 1: 단일 카테고리
    print("=" * 60)
    print("테스트 케이스 1: 단일 카테고리 (간편결제)")
    print("=" * 60)

    recommendation_result = {
        "selected_card": 2862,
        "name": "MG+ S 하나카드",
        "annual_savings": 216000,
        "annual_fee": 17000,
        "score_breakdown": {
            "net_benefit": 199000
        },
        "warnings": ["통합할인한도 초과 시 혜택 제한"],
        "category_breakdown": {
            "digital_payment": 18000
        }
    }

    user_pattern = {
        "spending": {
            "digital_payment": {"amount": 200000}
        }
    }

    response = generator.generate(recommendation_result, user_pattern)
    print(response)

    # 테스트 케이스 2: 다수 카테고리
    print("\n" + "=" * 60)
    print("테스트 케이스 2: 다수 카테고리 (카페, 배달, 간편결제)")
    print("=" * 60)

    recommendation_result_2 = {
        "selected_card": 129,
        "name": "청춘대로 톡톡카드",
        "annual_savings": 120000,
        "annual_fee": 10000,
        "score_breakdown": {
            "net_benefit": 110000
        },
        "warnings": ["상품권 구매 및 건물 내 임대매장 이용금액은 서비스 제외"],
        "category_breakdown": {
            "cafe": 4000,
            "delivery": 3000,
            "digital_payment": 3000
        }
    }

    user_pattern_2 = {
        "spending": {
            "cafe": {"amount": 100000},
            "delivery": {"amount": 80000},
            "digital_payment": {"amount": 50000}
        }
    }

    response_2 = generator.generate(recommendation_result_2, user_pattern_2)
    print(response_2)

    # 테스트 케이스 3: 경고 없음
    print("\n" + "=" * 60)
    print("테스트 케이스 3: 경고 없음 (마트)")
    print("=" * 60)

    recommendation_result_3 = {
        "selected_card": 100,
        "name": "테스트 카드",
        "annual_savings": 50000,
        "annual_fee": 0,
        "score_breakdown": {
            "net_benefit": 50000
        },
        "warnings": [],
        "category_breakdown": {
            "grocery": 4000
        }
    }

    response_3 = generator.generate(recommendation_result_3, None)
    print(response_3)


if __name__ == "__main__":
    main()
