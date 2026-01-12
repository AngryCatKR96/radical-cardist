"""
혜택 분석 Agent

후보 카드에 대해 사용자의 실제 소비 패턴을 기반으로 정량적 혜택을 계산합니다.
LLM이 카드 혜택 설명을 해석하고, 사용자 지출과 매칭하여 월/연 절약액을 산출합니다.
"""

from utils import measure_time
import json
import asyncio
import sys
from pathlib import Path
from typing import Dict, List
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


load_dotenv()


class BenefitAnalyzer:
    def __init__(self, model: str = "gpt-5-mini"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 설정되어 있지 않습니다.")
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    @staticmethod
    def _function_schema() -> Dict:
        return {
            "name": "analyze_benefit",
            "description": "카드 혜택 설명과 사용자 소비 패턴을 분석하여 실제 절약 금액을 계산합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "monthly_savings": {"type": "number", "description": "월 예상 절약액 (원)"},
                    "annual_savings": {"type": "number", "description": "연 예상 절약액 (원)"},
                    "conditions_met": {"type": "boolean", "description": "전월실적 등 조건 충족 여부"},
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
                    "reasoning": {"type": "string", "description": "계산 근거"},
                },
                "required": ["monthly_savings", "annual_savings", "conditions_met", "warnings"],
            },
        }

    @staticmethod
    def _build_evidence_context(card_context: Dict) -> str:
        parts: List[str] = []
        for chunk in card_context.get("evidence_chunks", []):
            text = (chunk.get("text") or "").strip()
            if not text:
                continue
            doc_type = (chunk.get("metadata", {}) or {}).get("doc_type", "")
            header = f"[{doc_type}]\n" if doc_type else ""
            parts.append(f"{header}{text}")
        return "\n\n".join(parts).strip()

    @staticmethod
    def _build_user_summary(user_pattern: Dict) -> str:
        spending = user_pattern.get("spending", {}) or {}
        constraints = user_pattern.get("constraints", {}) or {}
        must_include = constraints.get("must_include_categories", []) or []

        lines: List[str] = []
        for category, data in spending.items():
            if isinstance(data, dict):
                amount = float(data.get("amount", 0) or 0)
            else:
                amount = float(data or 0) if isinstance(
                    data, (int, float)) else 0.0

            if amount > 0:
                lines.append(f"{category}: {int(amount):,}원/월")

        parts: List[str] = []
        if lines:
            parts.append("**구체적인 지출 금액:**\n" + "\n".join(lines))
        if must_include:
            parts.append("**사용자가 관심있는 카테고리:**\n" +
                         ", ".join(map(str, must_include)))

        return "\n\n".join(parts).strip() if parts else "구체적인 소비 금액 정보 없음"

    @measure_time("analyze_one")
    async def analyze_one(self, user_pattern: Dict, card_context: Dict) -> Dict:
        evidence_context = self._build_evidence_context(card_context)
        user_summary = self._build_user_summary(user_pattern)

        prompt = f"""다음은 사용자의 소비 패턴과 카드 혜택 정보입니다.

[사용자 소비 패턴]
{user_summary}

[카드 혜택 정보]
{evidence_context}

위 정보를 바탕으로:
1. 사용자가 관심있는 카테고리에 이 카드의 혜택이 있는지 확인하세요.
2. 구체적인 금액이 없어도 관심 카테고리에 혜택이 있으면 긍정적으로 평가하세요.
3. 전월실적 조건, 최소 구매금액, 월 한도 등 모든 조건을 고려하세요.
4. 제외 항목이 있으면 warnings에 기록하세요.
5. 계산 근거를 reasoning에 상세히 기록하세요.

전월실적 조건 처리 규칙:
- 사용자의 전월실적 정보가 명시적으로 제공되지 않은 경우, 일반적인 소비자 기준으로 충족 가능성을 판단하세요.
- 관심 카테고리를 정기적으로 사용한다면 충족 가능성이 높다고 가정하세요.
- 전월실적 조건이 있으면 항상 warnings에 조건을 명시하세요. 

그외규칙
 - reasoning은 최대 5줄로 작성합니다.
 - optimization_tips는 최대 3개만 작성합니다.
 - category_breakdown은 혜택이 있는 카테고리만 포함하고 최대 5개로 제한합니다.
 - warnings는 최대 6개로 요약합니다.
"""

        schema = self._function_schema()

        try:
            res = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "당신은 신용카드 혜택 분석 전문가입니다. "
                            "사용자의 소비 패턴/관심 카테고리와 카드 혜택을 매칭하여 적합성을 평가하고 "
                            "절약액을 계산합니다. 구체적인 금액이 없어도 카테고리 매칭이 좋으면 긍정적으로 평가합니다."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                tools=[{"type": "function", "function": schema}],
                tool_choice={"type": "function",
                             "function": {"name": "analyze_benefit"}}
            )

            msg = res.choices[0].message
            if not msg.tool_calls:
                raise ValueError("Function call이 반환되지 않았습니다.")

            args = json.loads(msg.tool_calls[0].function.arguments)
            args["card_id"] = card_context.get("card_id")
            return args

        except Exception as e:
            raise ValueError(
                f"혜택 분석 실패 (card_id={card_context.get('card_id')}): {e}") 

    @measure_time("analyze_batch")
    async def analyze_batch(self, user_pattern: Dict, card_contexts: List[Dict]) -> List[Dict]:
        if not card_contexts:
            return [] 
        print(f"Analyzing {len(card_contexts)} cards")
        tasks = [self.analyze_one(user_pattern, c) for c in card_contexts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: List[Dict] = []
        for i, r in enumerate(results):
            card_id = card_contexts[i].get("card_id", "unknown")
            if isinstance(r, Exception):
                out.append(
                    {
                        "card_id": card_id,
                        "monthly_savings": 0,
                        "annual_savings": 0,
                        "conditions_met": False,
                        "warnings": [str(r)],
                        "category_breakdown": {},
                    }
                )
            else:
                out.append(r)
        return out


# 사용 예시
async def main():
    """테스트용 메인 함수"""
    analyzer = BenefitAnalyzer()

    user_pattern = {
        "spending": {
            "grocery": {"amount": 300000},
            "digital_payment": {"amount": 200000},
            "subscription_video": {"amount": 30000}
        }
    }

    card_context = {
        "card_id": 2862,
        "evidence_chunks": [
            {
                "text": "간편결제 10% 청구할인. 건당 1만원 이상 결제 시 적용.",
                "metadata": {"doc_type": "benefit", "category_std": "digital_payment"}
            },
            {
                "text": "유의사항: 통합할인한도 구간별 제한. 제외 항목: 국세, 지방세, 공과금",
                "metadata": {"doc_type": "notes"}
            }
        ]
    }

    result = await analyzer.analyze_one(user_pattern, card_context)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
