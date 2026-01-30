#!/usr/bin/env python3
"""
BenefitAnalyzer 모델 비교 테스트 스크립트

gpt-4-turbo-preview vs gpt-5 계열 모델 성능 및 정확도 비교

사용법:
    python test_benefit_analyzer_models.py --all
    python test_benefit_analyzer_models.py --model gpt-5-mini
    python test_benefit_analyzer_models.py --model gpt-5
"""

import json
import time
import argparse
from typing import Dict, List, Tuple
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

# 테스트할 모델 목록
MODELS = {
    "gpt-4-turbo-preview": "현재 사용 중",
    "gpt-5-mini": "최신 가성비 모델",
    "gpt-5": "최신 플래그십 모델",
    "gpt-5.1": "개선된 추론 모델",
    "gpt-5.2": "최신 추론 모델",
    "o4-mini": "수학/추론 특화 모델",
}

# 비용 정보 (per 1M tokens)
PRICING = {
    "gpt-4-turbo-preview": {"input": 10.00, "output": 30.00},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-5": {"input": 2.50, "output": 10.00},  # 예상
    "gpt-5.1": {"input": 3.00, "output": 12.00},  # 예상
    "gpt-5.2": {"input": 3.50, "output": 14.00},  # 예상
    "o4-mini": {"input": 1.10, "output": 4.40},
}


class BenefitAnalyzerTester:
    """BenefitAnalyzer 모델 성능 비교 클래스"""

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _get_function_schema(self) -> Dict:
        """Function Calling 스키마 (실제 BenefitAnalyzer와 동일)"""
        return {
            "name": "analyze_benefit",
            "description": "카드 혜택 설명과 사용자 소비 패턴을 분석하여 실제 절약 금액을 계산합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "monthly_savings": {
                        "type": "number",
                        "description": "월 예상 절약액 (원)",
                    },
                    "annual_savings": {
                        "type": "number",
                        "description": "연 예상 절약액 (원)",
                    },
                    "conditions_met": {
                        "type": "boolean",
                        "description": "전월실적 등 조건 충족 여부",
                    },
                    "warnings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "주의사항 (전월실적 미충족, 한도 초과, 제외 항목 등)",
                    },
                    "category_breakdown": {
                        "type": "object",
                        "description": "카테고리별 월 절약액 (원)",
                        "additionalProperties": {"type": "number"},
                    },
                    "optimization_tips": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "혜택 최대화를 위한 사용 전략",
                    },
                    "reasoning": {"type": "string", "description": "계산 근거 및 가정"},
                },
                "required": [
                    "monthly_savings",
                    "annual_savings",
                    "conditions_met",
                    "warnings",
                ],
            },
        }

    def test_model(self, model: str, test_cases: List[Dict]) -> List[Dict]:
        """모델 테스트"""
        print(f"\n{'='*70}")
        print(f"BenefitAnalyzer 테스트: {model}")
        print(f"{'='*70}")

        results = []
        function_schema = self._get_function_schema()

        # gpt-5 계열과 o4-mini는 temperature=1만 지원
        temperature = 1.0 if (model.startswith("gpt-5") or model == "o4-mini") else 0.1

        system_prompt = "당신은 신용카드 혜택 분석 전문가입니다. 사용자의 실제 소비 패턴과 카드 혜택을 정확히 매칭하여 정량적 절약액을 계산합니다."

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n[테스트 케이스 {i}] {test_case['name']}")
            print(f"카드: {test_case['card_name']}")
            print(f"예상 답: 월 {test_case['expected_monthly_savings']:,}원")

            # 프롬프트 생성
            user_summary = test_case["user_pattern"]
            evidence_context = test_case["card_benefits"]

            prompt = f"""다음은 사용자의 소비 패턴과 카드 혜택 정보입니다.

[사용자 소비 패턴]
{user_summary}

[카드 혜택 정보]
{evidence_context}

위 정보를 바탕으로:
1. 사용자가 이 카드를 사용할 때 실제로 얼마나 절약할 수 있는지 계산하세요.
2. 전월실적 조건, 최소 구매금액, 월 한도 등 모든 조건을 고려하세요.
3. 제외 항목이 있으면 warnings에 기록하세요.
4. 계산 근거를 reasoning에 상세히 기록하세요.

중요:
- 할인율이 있으면 실제 사용 금액에 적용하여 절약액을 계산하세요.
- 월 한도가 있으면 그 한도 내에서만 계산하세요.
- 여러 카테고리 혜택이 있으면 각각 계산하고 category_breakdown에 기록하세요.

**전월실적 조건 처리 규칙** (o4-mini 최적화):
- 사용자의 전월실적 정보가 명시적으로 제공되지 않은 경우, 사용자가 제시한 월 소비 패턴이 전월에도 유사하게 발생했다고 가정하세요.
- 예: 사용자가 "간편결제 200,000원/월" 사용한다면, 전월에도 유사한 소비가 있었다고 간주합니다.
- 사용자의 월 소비 총액이 전월실적 조건을 충족하면 conditions_met를 true로 설정하세요.
- 명백히 전월실적을 충족할 수 없는 경우(예: 월 소비 30만원인데 전월실적 100만원 요구)에만 conditions_met를 false로 설정하세요.
- 전월실적 조건이 있으면 항상 warnings에 조건을 명시하세요.
"""

            start_time = time.time()

            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    tools=[{"type": "function", "function": function_schema}],
                    tool_choice={
                        "type": "function",
                        "function": {"name": "analyze_benefit"},
                    },
                    temperature=temperature,
                )

                elapsed_time = time.time() - start_time

                # 토큰 사용량
                usage = response.usage
                input_tokens = usage.prompt_tokens
                output_tokens = usage.completion_tokens

                # 비용 계산
                cost = (input_tokens / 1_000_000) * PRICING[model]["input"] + (
                    output_tokens / 1_000_000
                ) * PRICING[model]["output"]

                # Function call 결과 추출
                message = response.choices[0].message
                if message.tool_calls and len(message.tool_calls) > 0:
                    tool_call = message.tool_calls[0]
                    result_data = json.loads(tool_call.function.arguments)

                    monthly_savings = result_data.get("monthly_savings", 0)
                    annual_savings = result_data.get("annual_savings", 0)
                    conditions_met = result_data.get("conditions_met", False)
                    warnings = result_data.get("warnings", [])
                    reasoning = result_data.get("reasoning", "")

                    # 정확도 계산
                    expected = test_case["expected_monthly_savings"]
                    error_rate = (
                        abs(monthly_savings - expected) / expected * 100
                        if expected > 0
                        else 0
                    )

                    print(f"✓ 성공")
                    print(f"  - 소요시간: {elapsed_time:.2f}초")
                    print(f"  - Input 토큰: {input_tokens:,}")
                    print(f"  - Output 토큰: {output_tokens:,}")
                    print(f"  - 비용: ${cost:.6f}")
                    print(
                        f"  - 계산 결과: 월 {monthly_savings:,}원 (연 {annual_savings:,}원)"
                    )
                    print(f"  - 오차율: {error_rate:.1f}%")
                    print(f"  - 조건 충족: {'예' if conditions_met else '아니오'}")
                    if warnings:
                        print(f"  - 주의사항: {', '.join(warnings[:2])}")
                    print(f"  - 계산 근거: {reasoning[:100]}...")

                    results.append(
                        {
                            "success": True,
                            "elapsed_time": elapsed_time,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "cost": cost,
                            "monthly_savings": monthly_savings,
                            "annual_savings": annual_savings,
                            "expected_monthly_savings": expected,
                            "error_rate": error_rate,
                            "conditions_met": conditions_met,
                            "warnings": warnings,
                            "reasoning": reasoning,
                        }
                    )
                else:
                    print(f"✗ 실패: Function call 없음")
                    results.append({"success": False, "error": "No function call"})

            except Exception as e:
                print(f"✗ 오류: {str(e)}")
                results.append({"success": False, "error": str(e)})

        return results

    def print_summary(self, model_results: Dict[str, List[Dict]]):
        """결과 요약 출력"""
        print(f"\n{'='*70}")
        print(f"BenefitAnalyzer - 모델 비교 요약")
        print(f"{'='*70}")

        print(
            f"\n{'모델':<25} {'평균 시간':>12} {'평균 비용':>12} {'평균 오차':>12} {'성공률':>10}"
        )
        print("-" * 70)

        for model, results in model_results.items():
            successful = [r for r in results if r.get("success")]
            if successful:
                avg_time = sum(r["elapsed_time"] for r in successful) / len(successful)
                avg_cost = sum(r["cost"] for r in successful) / len(successful)
                avg_error = sum(r["error_rate"] for r in successful) / len(successful)
                success_rate = len(successful) / len(results) * 100

                print(
                    f"{model:<25} {avg_time:>10.2f}초 ${avg_cost:>10.6f} {avg_error:>10.1f}% {success_rate:>9.0f}%"
                )

        print()


def get_test_cases() -> List[Dict]:
    """BenefitAnalyzer 테스트 케이스"""
    return [
        # 케이스 1: 간단한 할인율 계산
        {
            "name": "단순 할인율",
            "card_name": "간편결제 10% 할인카드",
            "user_pattern": "간편결제: 200,000원/월",
            "card_benefits": """
[혜택]
- 간편결제(네이버페이, 카카오페이) 10% 청구할인
- 월 할인한도: 20,000원
- 전월실적: 30만원 이상

[제외항목]
- 없음
""",
            "expected_monthly_savings": 20000,  # 200,000 * 10% = 20,000 (한도 내)
        },
        # 케이스 2: 복잡한 조건 (한도 초과)
        {
            "name": "한도 초과 케이스",
            "card_name": "마트 5% 할인카드",
            "user_pattern": "마트: 500,000원/월",
            "card_benefits": """
[혜택]
- 대형마트 5% 청구할인
- 월 할인한도: 10,000원
- 전월실적: 50만원 이상

[제외항목]
- 온라인 마트 제외
""",
            "expected_monthly_savings": 10000,  # 500,000 * 5% = 25,000 -> 한도 10,000
        },
        # 케이스 3: 여러 카테고리 혜택
        {
            "name": "다중 카테고리",
            "card_name": "통합 혜택카드",
            "user_pattern": """
마트: 300,000원/월
카페: 100,000원/월
간편결제: 200,000원/월
""",
            "card_benefits": """
[혜택]
1. 마트 5% 할인, 월 한도 15,000원
2. 카페 10% 할인, 월 한도 10,000원
3. 간편결제 8% 할인, 월 한도 12,000원
- 전월실적: 50만원 이상

[제외항목]
- 국세, 지방세, 공과금
""",
            "expected_monthly_savings": 35000,  # 15,000 + 10,000 + 12,000 (각 한도 내)
        },
        # 케이스 4: 전월실적 미충족
        {
            "name": "전월실적 미충족",
            "card_name": "고액 전월실적 카드",
            "user_pattern": "총 지출: 300,000원/월",
            "card_benefits": """
[혜택]
- 모든 가맹점 2% 할인
- 월 할인한도: 30,000원
- 전월실적: 100만원 이상 (필수)

[제외항목]
- 없음
""",
            "expected_monthly_savings": 0,  # 전월실적 미충족으로 혜택 없음
        },
        # 케이스 5: 복잡한 계산 (건당 최소 금액)
        {
            "name": "건당 최소 금액 조건",
            "card_name": "스타벅스 특화카드",
            "user_pattern": """
스타벅스: 월 10회, 회당 평균 5,000원 (총 50,000원)
기타 카페: 월 20,000원
""",
            "card_benefits": """
[혜택]
- 스타벅스 15% 할인
- 건당 10,000원 이상 결제 시에만 적용
- 월 할인한도: 20,000원
- 전월실적: 30만원 이상

[제외항목]
- 기타 카페는 혜택 없음
""",
            "expected_monthly_savings": 0,  # 건당 5,000원으로 최소금액 미충족
        },
        # 케이스 6: 구간별 할인율
        {
            "name": "구간별 할인율",
            "card_name": "구간별 혜택카드",
            "user_pattern": "온라인쇼핑: 600,000원/월",
            "card_benefits": """
[혜택]
- 온라인쇼핑 청구할인
  * 30만원까지: 5%
  * 30만원 초과분: 3%
- 월 할인한도: 30,000원
- 전월실적: 50만원 이상

[제외항목]
- 해외직구 제외
""",
            "expected_monthly_savings": 24000,  # (300,000 * 5%) + (300,000 * 3%) = 15,000 + 9,000
        },
    ]


def main():
    parser = argparse.ArgumentParser(description="BenefitAnalyzer 모델 비교 테스트")
    parser.add_argument(
        "--model", choices=list(MODELS.keys()), help="테스트할 모델 선택"
    )
    parser.add_argument("--all", action="store_true", help="모든 모델 테스트")

    args = parser.parse_args()

    if not args.model and not args.all:
        parser.error("--model 또는 --all 중 하나를 선택해야 합니다.")

    tester = BenefitAnalyzerTester()
    test_cases = get_test_cases()

    print("\n" + "=" * 70)
    print("BenefitAnalyzer 모델 비교 테스트")
    print("=" * 70)
    print(f"\n테스트 케이스 수: {len(test_cases)}")
    print("테스트 시나리오:")
    for i, tc in enumerate(test_cases, 1):
        print(
            f"  {i}. {tc['name']} - 예상 절약액: 월 {tc['expected_monthly_savings']:,}원"
        )

    models_to_test = list(MODELS.keys()) if args.all else [args.model]
    model_results = {}

    for model in models_to_test:
        try:
            results = tester.test_model(model, test_cases)
            model_results[model] = results
        except Exception as e:
            print(f"\n✗ {model} 테스트 실패: {e}")

    tester.print_summary(model_results)

    print("\n" + "=" * 70)
    print("테스트 완료!")
    print("=" * 70)


if __name__ == "__main__":
    main()
