#!/usr/bin/env python3
"""
GPT 모델 비교 테스트 스크립트

gpt-4-turbo-preview vs gpt-4o-mini vs gpt-5-mini 성능 및 비용 비교

사용법:
    python test_model_comparison.py --agent input_parser
    python test_model_comparison.py --agent response_generator
    python test_model_comparison.py --all
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
    "gpt-4o-mini": "저렴한 대안",
    "gpt-5-mini": "최신 모델"
}

# 비용 정보 (per 1M tokens)
PRICING = {
    "gpt-4-turbo-preview": {"input": 10.00, "output": 30.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-5-mini": {"input": 0.25, "output": 2.00}
}


class ModelComparator:
    """모델 성능 비교 클래스"""

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def test_input_parser(self, model: str, test_cases: List[str]) -> List[Dict]:
        """InputParser Agent 테스트"""
        print(f"\n{'='*60}")
        print(f"InputParser 테스트: {model}")
        print(f"{'='*60}")

        results = []

        # gpt-5-mini는 temperature=1만 지원
        temperature = 1.0 if model == "gpt-5-mini" else 0.1

        # Function Calling 스키마 (실제 프로젝트에서 사용하는 것과 동일)
        function_schema = {
            "name": "extract_spending_pattern",
            "description": "사용자의 자연어 입력에서 소비 패턴, 선호사항, 제약 조건을 추출하여 구조화된 데이터로 변환합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spending": {
                        "type": "object",
                        "description": "카테고리별 월 예상 지출 금액 (원 단위)",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "amount": {"type": "number", "description": "월 지출 금액 (원)"},
                                "merchants": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "주로 이용하는 가맹점/서비스"
                                }
                            },
                            "required": ["amount"]
                        }
                    },
                    "preferences": {
                        "type": "object",
                        "properties": {
                            "max_annual_fee": {"type": "number", "description": "최대 연회비 (원)"},
                            "prefer_types": {
                                "type": "array",
                                "items": {"type": "string", "enum": ["credit", "debit", "both"]}
                            }
                        }
                    },
                    "query_text": {
                        "type": "string",
                        "description": "벡터 검색용 자연어 요약"
                    },
                    "filters": {
                        "type": "object",
                        "properties": {
                            "annual_fee_max": {"type": "number"},
                            "type": {"type": "string", "enum": ["credit", "debit", "both"]}
                        }
                    }
                },
                "required": ["spending", "query_text", "filters"]
            }
        }

        system_prompt = """당신은 사용자의 자연어 소비 패턴 입력을 구조화된 데이터로 변환하는 전문가입니다.
사용자가 언급한 모든 정보를 정확하게 추출하세요.
특히 '연회비 2만원 이하'와 같은 조건이 있을 때, '넘어도 된다', '선호한다' 등의 유연한 표현이 함께 있다면
이를 강제 필터(filters)가 아닌 선호사항(preferences)으로 분류해야 합니다.
'절대', '무조건', '이상은 안됨' 등의 강한 표현이 있을 때만 filters에 값을 설정하세요."""

        for i, user_input in enumerate(test_cases, 1):
            print(f"\n[테스트 케이스 {i}]")
            print(f"입력: {user_input}")

            start_time = time.time()

            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_input}
                    ],
                    tools=[{"type": "function", "function": function_schema}],
                    tool_choice={"type": "function", "function": {"name": "extract_spending_pattern"}},
                    temperature=temperature
                )

                elapsed_time = time.time() - start_time

                # 토큰 사용량
                usage = response.usage
                input_tokens = usage.prompt_tokens
                output_tokens = usage.completion_tokens

                # 비용 계산
                cost = (
                    (input_tokens / 1_000_000) * PRICING[model]["input"] +
                    (output_tokens / 1_000_000) * PRICING[model]["output"]
                )

                # Function call 결과 추출
                message = response.choices[0].message
                if message.tool_calls and len(message.tool_calls) > 0:
                    tool_call = message.tool_calls[0]
                    parsed_data = json.loads(tool_call.function.arguments)

                    print(f"✓ 성공")
                    print(f"  - 소요시간: {elapsed_time:.2f}초")
                    print(f"  - Input 토큰: {input_tokens:,}")
                    print(f"  - Output 토큰: {output_tokens:,}")
                    print(f"  - 비용: ${cost:.6f}")
                    print(f"  - 추출된 데이터 샘플:")
                    print(f"    * spending 카테고리 수: {len(parsed_data.get('spending', {}))}")
                    print(f"    * query_text: {parsed_data.get('query_text', '')[:80]}...")

                    results.append({
                        "success": True,
                        "elapsed_time": elapsed_time,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cost": cost,
                        "data": parsed_data
                    })
                else:
                    print(f"✗ 실패: Function call 없음")
                    results.append({"success": False, "error": "No function call"})

            except Exception as e:
                print(f"✗ 오류: {str(e)}")
                results.append({"success": False, "error": str(e)})

        return results

    def test_response_generator(self, model: str, test_cases: List[Dict]) -> List[Dict]:
        """ResponseGenerator Agent 테스트"""
        print(f"\n{'='*60}")
        print(f"ResponseGenerator 테스트: {model}")
        print(f"{'='*60}")

        results = []

        # gpt-5-mini는 temperature=1만 지원
        temperature = 1.0 if model == "gpt-5-mini" else 0.7

        system_prompt = "당신은 신용카드 추천 전문가입니다. 사용자에게 친절하고 이해하기 쉬운 추천 설명을 작성합니다."

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n[테스트 케이스 {i}]")
            print(f"카드: {test_case['card_name']}")

            # 프롬프트 생성 (실제 프로젝트와 동일한 형식)
            prompt = f"""다음은 신용카드 추천 결과입니다.

[추천 카드]
- 이름: {test_case['card_name']}
- 발급사: {test_case['issuer']}
- 전월실적 조건: {test_case['required_spend']:,}원 이상
- 연회비: {test_case['annual_fee']}

[예상 절약액]
- 연 절약액: {test_case['annual_savings']:,}원
- 연회비: {test_case['annual_fee_amount']:,}원
- 순 혜택: {test_case['net_benefit']:,}원

[카테고리별 절약액]
{json.dumps(test_case['category_breakdown'], ensure_ascii=False, indent=2)}

[주의사항]
{chr(10).join(test_case['warnings'])}

[사용자 소비 패턴]
{test_case['user_pattern']}

위 정보를 바탕으로 사용자에게 친절하고 이해하기 쉬운 추천 설명을 작성해주세요.

포함해야 할 내용:
1. 추천 카드명
2. 추천 이유 (사용자 소비 패턴과의 매칭)
3. 사용 전략 (어떻게 사용해야 최대 혜택인지)
4. 주의사항 (전월실적, 한도, 제외 항목 등)
5. 예상 절약액 (월/연 기준, 연회비 제외 전/후)

형식:
- 자연스러운 문체로 작성
- 구체적인 숫자와 예시 포함
- 사용자가 바로 실행할 수 있는 조언 제공
"""

            start_time = time.time()

            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=temperature
                )

                elapsed_time = time.time() - start_time

                # 토큰 사용량
                usage = response.usage
                input_tokens = usage.prompt_tokens
                output_tokens = usage.completion_tokens

                # 비용 계산
                cost = (
                    (input_tokens / 1_000_000) * PRICING[model]["input"] +
                    (output_tokens / 1_000_000) * PRICING[model]["output"]
                )

                generated_text = response.choices[0].message.content

                print(f"✓ 성공")
                print(f"  - 소요시간: {elapsed_time:.2f}초")
                print(f"  - Input 토큰: {input_tokens:,}")
                print(f"  - Output 토큰: {output_tokens:,}")
                print(f"  - 비용: ${cost:.6f}")
                print(f"  - 생성된 텍스트 (처음 200자):")
                print(f"    {generated_text[:200]}...")

                results.append({
                    "success": True,
                    "elapsed_time": elapsed_time,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": cost,
                    "text": generated_text
                })

            except Exception as e:
                print(f"✗ 오류: {str(e)}")
                results.append({"success": False, "error": str(e)})

        return results

    def print_summary(self, agent_name: str, model_results: Dict[str, List[Dict]]):
        """결과 요약 출력"""
        print(f"\n{'='*60}")
        print(f"{agent_name} - 모델 비교 요약")
        print(f"{'='*60}")

        print(f"\n{'모델':<25} {'평균 시간':>12} {'평균 비용':>12} {'성공률':>10}")
        print("-" * 60)

        for model, results in model_results.items():
            successful = [r for r in results if r.get("success")]
            if successful:
                avg_time = sum(r["elapsed_time"] for r in successful) / len(successful)
                avg_cost = sum(r["cost"] for r in successful) / len(successful)
                success_rate = len(successful) / len(results) * 100

                print(f"{model:<25} {avg_time:>10.2f}초 ${avg_cost:>10.6f} {success_rate:>9.0f}%")

        print()


def get_input_parser_test_cases() -> List[str]:
    """InputParser 테스트 케이스"""
    return [
        # 케이스 1: 간단한 입력 (짧음)
        "스타벅스 자주 가는데 카드 추천해줘",

        # 케이스 2: 중간 복잡도 (test_api.py와 동일)
        "마트 30만원, 넷플릭스/유튜브 구독, 간편결제 자주 씀. 연회비 2만원 이하, 체크카드 선호.",

        # 케이스 3: 복잡한 입력 (긴 문장, 여러 조건)
        """온라인 쇼핑 월 50만원 정도 하고, 주말에는 주로 카페(스타벅스, 투썸) 가요.
        일주일에 3-4번 정도. 그리고 넷플릭스, 유튜브 프리미엄 구독 중이고,
        네이버페이랑 카카오페이 자주 써요. 편의점도 자주 가는 편이에요.
        연회비는 무조건 2만원 넘으면 안되고, 체크카드로 찾고 있어요.
        전월실적은 30만원 정도까지는 충족 가능할 것 같아요.""",

        # 케이스 4: 모호한 표현 (preferences vs filters 구분 테스트)
        "마트 많이 이용해요. 연회비는 적을수록 좋고, 가능하면 체크카드가 좋은데 신용카드도 괜찮아요.",

        # 케이스 5: 숫자 변환 테스트
        "카페 10만원, 온라인쇼핑 30만 원, 편의점 5만 원 정도 씁니다."
    ]


def get_response_generator_test_cases() -> List[Dict]:
    """ResponseGenerator 테스트 케이스"""
    return [
        # 케이스 1: 간단한 카드 추천
        {
            "card_name": "MG+ S 하나카드",
            "issuer": "하나카드",
            "required_spend": 300000,
            "annual_fee": "국내전용 17,000원",
            "annual_savings": 216000,
            "annual_fee_amount": 17000,
            "net_benefit": 199000,
            "category_breakdown": {
                "digital_payment": 18000
            },
            "warnings": ["통합할인한도 초과 시 혜택 제한"],
            "user_pattern": "간편결제 200,000원/월"
        },

        # 케이스 2: 복잡한 혜택 구조
        {
            "card_name": "신한카드 Deep Dream",
            "issuer": "신한카드",
            "required_spend": 500000,
            "annual_fee": "국내전용 50,000원",
            "annual_savings": 480000,
            "annual_fee_amount": 50000,
            "net_benefit": 430000,
            "category_breakdown": {
                "grocery": 36000,
                "cafe": 24000,
                "digital_payment": 18000
            },
            "warnings": [
                "전월실적 50만원 이상 필요",
                "카테고리별 월 한도 있음",
                "국세, 지방세 제외"
            ],
            "user_pattern": "마트 300,000원/월\n카페 100,000원/월\n간편결제 200,000원/월"
        },

        # 케이스 3: 연회비 무료 카드
        {
            "card_name": "카카오뱅크 체크카드",
            "issuer": "카카오뱅크",
            "required_spend": 0,
            "annual_fee": "없음",
            "annual_savings": 120000,
            "annual_fee_amount": 0,
            "net_benefit": 120000,
            "category_breakdown": {
                "convenience": 10000
            },
            "warnings": [],
            "user_pattern": "편의점 100,000원/월"
        }
    ]


def main():
    parser = argparse.ArgumentParser(description="GPT 모델 비교 테스트")
    parser.add_argument(
        "--agent",
        choices=["input_parser", "response_generator"],
        help="테스트할 Agent 선택"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="모든 Agent 테스트"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        choices=list(MODELS.keys()),
        default=list(MODELS.keys()),
        help="테스트할 모델 선택 (기본값: 전체)"
    )

    args = parser.parse_args()

    if not args.agent and not args.all:
        parser.error("--agent 또는 --all 중 하나를 선택해야 합니다.")

    comparator = ModelComparator()

    # InputParser 테스트
    if args.agent == "input_parser" or args.all:
        print("\n" + "="*60)
        print("InputParser Agent 모델 비교 테스트")
        print("="*60)

        test_cases = get_input_parser_test_cases()
        model_results = {}

        for model in args.models:
            try:
                results = comparator.test_input_parser(model, test_cases)
                model_results[model] = results
            except Exception as e:
                print(f"\n✗ {model} 테스트 실패: {e}")

        comparator.print_summary("InputParser", model_results)

    # ResponseGenerator 테스트
    if args.agent == "response_generator" or args.all:
        print("\n" + "="*60)
        print("ResponseGenerator Agent 모델 비교 테스트")
        print("="*60)

        test_cases = get_response_generator_test_cases()
        model_results = {}

        for model in args.models:
            try:
                results = comparator.test_response_generator(model, test_cases)
                model_results[model] = results
            except Exception as e:
                print(f"\n✗ {model} 테스트 실패: {e}")

        comparator.print_summary("ResponseGenerator", model_results)

    print("\n" + "="*60)
    print("테스트 완료!")
    print("="*60)


if __name__ == "__main__":
    main()
