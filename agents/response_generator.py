"""
응답 생성 Agent - LLM 기반

LLM을 사용하여 추천 결과를 사용자 친화적이고 자연스러운 자연어로 변환합니다.
하드코딩된 템플릿 대신 동적이고 맥락에 맞는 응답을 생성합니다.
"""

import os
from typing import Dict
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()


class ResponseGenerator:
    """응답 생성기 - LLM 기반"""

    def __init__(self, model: str = "gpt-4o-mini"):
        """
        ResponseGenerator 초기화

        Args:
            model: 사용할 OpenAI 모델 (기본값: gpt-4o-mini - 자연스러운 응답 생성)
        """
        # LangChain ChatOpenAI 초기화
        self.llm = ChatOpenAI(
            model=model,
            temperature=0.7,  # 창의적이고 자연스러운 응답을 위해
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )

        # 프롬프트 템플릿 정의
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """당신은 신용카드 추천 전문가입니다.
사용자에게 친근하고 이해하기 쉬운 방식으로 카드 추천 이유를 설명합니다.
전문적이면서도 따뜻한 어조를 유지하며, 구체적인 절약 금액과 사용 전략을 제시합니다.

**응답 구조:**
1. **추천 카드 소개** (1-2문장): 카드 이름과 발급사를 소개
2. **선정 이유** (2-3문장): 왜 이 카드가 사용자에게 적합한지 설명
3. **예상 절약액** (2-3문장): 구체적인 월/연 절약액과 연회비 정보
4. **사용 전략** (3-4개 항목, 각 1문장): 혜택을 최대화하는 방법
5. **주의사항** (있는 경우만): 전월실적, 한도, 제외 항목 등

**주의:**
- 이모지나 특수 기호는 사용하지 마세요
- 구체적인 숫자와 카테고리를 명시하세요
- 너무 길지 않게, 핵심만 전달하세요"""),
            ("user", """다음 카드를 추천합니다:

## 카드 정보
- 이름: {card_name}
- 발급사: {issuer}
- 연회비: {annual_fee}원
- 카드 유형: {card_type}

## 분석 결과
- 월 절약액: {monthly_savings:,}원
- 연 절약액: {annual_savings:,}원
- 순 혜택 (연 절약액 - 연회비): {net_benefit:,}원
- 조건 충족 여부: {conditions_met}

## 주요 혜택 카테고리
{category_list}

## 사용자 소비 패턴
{spending_summary}

## 주의사항
{warnings}

위 정보를 바탕으로 사용자에게 친근하고 설득력 있는 추천 메시지를 작성해주세요.""")
        ])

    def generate(
        self,
        selected_card: Dict,
        user_pattern: Dict,
        analysis: Dict,
        card_metadata: Dict
    ) -> str:
        """
        LLM을 사용해 자연스러운 추천 응답 생성

        Args:
            selected_card: 선택된 카드 정보 (recommender 출력)
            user_pattern: 사용자 소비 패턴 (input_parser 출력)
            analysis: 혜택 분석 결과 (benefit_analyzer 출력)
            card_metadata: 카드 메타데이터 (compressed context)

        Returns:
            자연어 추천 응답
        """
        # 카드 메타데이터 추출
        meta = card_metadata.get("meta", {})
        card_name = meta.get("name", "알 수 없는 카드")
        issuer = meta.get("issuer", "알 수 없는 발급사")
        card_type = "신용카드" if meta.get("type") == "C" else "체크카드" if meta.get("type") == "D" else "알 수 없음"

        # 절약액 계산
        annual_savings = analysis.get("annual_savings", 0)
        monthly_savings = analysis.get("monthly_savings", 0)
        annual_fee = selected_card.get("annual_fee", 0)
        net_benefit = annual_savings - annual_fee
        conditions_met = "예" if analysis.get("conditions_met", False) else "아니오"

        # 카테고리 리스트 생성
        category_breakdown = analysis.get("category_breakdown", {})
        if category_breakdown:
            category_items = [f"- {cat}: {amount:,}원/월" for cat, amount in category_breakdown.items() if amount > 0]
            category_list = "\n".join(category_items[:5])  # 최대 5개
        else:
            category_list = "- 없음"

        # 사용자 소비 패턴 요약
        spending = user_pattern.get("spending", {})
        if spending:
            spending_items = []
            for cat, detail in spending.items():
                if isinstance(detail, dict):
                    amount = detail.get("amount", 0)
                    if amount > 0:
                        spending_items.append(f"- {cat}: {amount:,}원/월")
            spending_summary = "\n".join(spending_items[:5]) if spending_items else "- 구체적인 금액 정보 없음"
        else:
            spending_summary = "- 구체적인 금액 정보 없음"

        # 주의사항
        warnings = analysis.get("warnings", [])
        if warnings:
            warnings_text = "\n".join([f"- {w}" for w in warnings[:6]])
        else:
            warnings_text = "- 없음"

        # LangChain 체인 구성 및 실행
        chain = self.prompt | self.llm

        try:
            result = chain.invoke({
                "card_name": card_name,
                "issuer": issuer,
                "annual_fee": annual_fee,
                "card_type": card_type,
                "monthly_savings": monthly_savings,
                "annual_savings": annual_savings,
                "net_benefit": net_benefit,
                "conditions_met": conditions_met,
                "category_list": category_list,
                "spending_summary": spending_summary,
                "warnings": warnings_text
            })

            return result.content

        except Exception as e:
            # 에러 발생 시 기본 응답
            return f"""추천 카드: {card_name} ({issuer})

이 카드는 연간 약 {annual_savings:,}원의 절약이 예상되며,
연회비 {annual_fee:,}원을 제외하면 순 혜택이 {net_benefit:,}원입니다.

자세한 정보는 카드사 홈페이지를 확인해주세요."""


# 사용 예시
def main():
    """테스트용 메인 함수"""
    generator = ResponseGenerator()

    selected_card = {
        "selected_card": 2862,
        "name": "테스트 카드",
        "annual_fee": 10000,
        "annual_savings": 216000,
        "conditions_met": True
    }

    user_pattern = {
        "spending": {
            "digital_payment": {"amount": 200000},
            "grocery": {"amount": 300000}
        }
    }

    analysis = {
        "monthly_savings": 18000,
        "annual_savings": 216000,
        "conditions_met": True,
        "warnings": ["통합할인한도 초과 시 혜택 제한"],
        "category_breakdown": {"digital_payment": 10000, "grocery": 8000}
    }

    card_metadata = {
        "meta": {
            "name": "테스트 카드",
            "issuer": "테스트 은행",
            "type": "C"
        }
    }

    response = generator.generate(selected_card, user_pattern, analysis, card_metadata)
    print(response)


if __name__ == "__main__":
    main()
