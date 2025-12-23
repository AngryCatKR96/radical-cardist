"""
혜택 분석 Agent

후보 카드에 대해 사용자의 실제 소비 패턴을 기반으로 정량적 혜택을 계산합니다.
LLM이 카드 혜택 설명을 해석하고, 사용자 지출과 매칭하여 월/연 절약액을 산출합니다.
"""

import json
from typing import Dict, List, Optional
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()


class BenefitAnalyzer:
    """혜택 분석 Agent"""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "o4-mini"
    
    def _get_function_schema(self) -> Dict:
        """Function Calling 스키마 반환"""
        return {
            "name": "analyze_benefit",
            "description": "카드 혜택 설명과 사용자 소비 패턴을 분석하여 실제 절약 금액을 계산합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "monthly_savings": {
                        "type": "number",
                        "description": "월 예상 절약액 (원)"
                    },
                    "annual_savings": {
                        "type": "number",
                        "description": "연 예상 절약액 (원)"
                    },
                    "conditions_met": {
                        "type": "boolean",
                        "description": "전월실적 등 조건 충족 여부"
                    },
                    "warnings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "주의사항 (전월실적 미충족, 한도 초과, 제외 항목 등)"
                    },
                    "category_breakdown": {
                        "type": "object",
                        "description": "카테고리별 월 절약액 (원)",
                        "additionalProperties": {
                            "type": "number"
                        }
                    },
                    "optimization_tips": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "혜택 최대화를 위한 사용 전략"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "계산 근거 및 가정"
                    }
                },
                "required": ["monthly_savings", "annual_savings", "conditions_met", "warnings"]
            }
        }
    
    def analyze(
        self,
        user_pattern: Dict,
        card_context: Dict
    ) -> Dict:
        """
        카드 혜택 분석
        
        Args:
            user_pattern: 사용자 소비 패턴 (UserIntent의 spending 등)
            card_context: 카드 컨텍스트 {card_id, evidence_chunks}
        
        Returns:
            분석 결과 Dict
        """
        # 증거 문서 텍스트 수집
        evidence_texts = []
        for chunk in card_context.get("evidence_chunks", []):
            doc_type = chunk.get("metadata", {}).get("doc_type", "")
            text = chunk.get("text", "")
            if text:
                evidence_texts.append(f"[{doc_type}]\n{text}")
        
        evidence_context = "\n\n".join(evidence_texts)
        
        # 사용자 패턴 요약
        spending_summary = []
        spending = user_pattern.get("spending", {})
        for category, data in spending.items():
            if isinstance(data, dict):
                amount = data.get("amount", 0)
                if amount > 0:
                    spending_summary.append(f"{category}: {amount:,}원/월")
            elif isinstance(data, (int, float)):
                if data > 0:
                    spending_summary.append(f"{category}: {data:,}원/월")

        # must_include_categories 추가
        constraints = user_pattern.get("constraints", {})
        must_include = constraints.get("must_include_categories", [])

        user_summary_parts = []
        if spending_summary:
            user_summary_parts.append("**구체적인 지출 금액:**\n" + "\n".join(spending_summary))

        if must_include:
            user_summary_parts.append("**사용자가 관심있는 카테고리:**\n" + ", ".join(must_include))

        user_summary = "\n\n".join(user_summary_parts) if user_summary_parts else "구체적인 소비 금액 정보 없음"
        
        # LLM 호출
        function_schema = self._get_function_schema()
        
        prompt = f"""다음은 사용자의 소비 패턴과 카드 혜택 정보입니다.

[사용자 소비 패턴]
{user_summary}

[카드 혜택 정보]
{evidence_context}

위 정보를 바탕으로:
1. **사용자가 관심있는 카테고리**에 이 카드의 혜택이 있는지 확인하세요.
2. 구체적인 금액이 없어도, 사용자가 관심있는 카테고리에 혜택이 있으면 긍정적으로 평가하세요.
3. 예: 사용자가 'online_shopping'에 관심있고, 카드에 쿠팡/네이버쇼핑 할인이 있으면 좋은 매칭입니다.
4. 전월실적 조건, 최소 구매금액, 월 한도 등 모든 조건을 고려하세요.
5. 제외 항목이 있으면 warnings에 기록하세요.
6. 계산 근거를 reasoning에 상세히 기록하세요.

중요:
- **구체적인 금액이 없어도** 카테고리 매칭이 좋으면 이 카드가 적합하다고 판단하세요.
- 할인율이 있으면 실제 사용 금액에 적용하여 절약액을 계산하세요.
- 월 한도가 있으면 그 한도 내에서만 계산하세요.
- 여러 카테고리 혜택이 있으면 각각 계산하고 category_breakdown에 기록하세요.

**전월실적 조건 처리 규칙**:
- 사용자의 전월실적 정보가 명시적으로 제공되지 않은 경우, 일반적인 소비자 기준으로 전월실적 충족 가능성을 판단하세요.
- 사용자가 관심있는 카테고리를 정기적으로 사용한다면 조건을 충족할 가능성이 높다고 가정하세요.
- 전월실적 조건이 있으면 항상 warnings에 조건을 명시하세요.
"""
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 신용카드 혜택 분석 전문가입니다. 사용자의 소비 패턴 및 관심 카테고리와 카드 혜택을 매칭하여 적합성을 평가하고 절약액을 계산합니다. 구체적인 금액이 없어도 카테고리 매칭이 좋으면 긍정적으로 평가하세요."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                tools=[{
                    "type": "function",
                    "function": function_schema
                }],
                tool_choice={"type": "function", "function": {"name": "analyze_benefit"}},
                temperature=1.0  # o4-mini는 temperature=1만 지원
            )
            
            # Function call 결과 추출
            message = response.choices[0].message
            if message.tool_calls and len(message.tool_calls) > 0:
                tool_call = message.tool_calls[0]
                arguments = json.loads(tool_call.function.arguments)
                
                # card_id 추가
                arguments["card_id"] = card_context.get("card_id")
                
                return arguments
            else:
                raise ValueError("Function call이 반환되지 않았습니다")
                
        except Exception as e:
            raise ValueError(f"혜택 분석 실패: {e}")
    
    def analyze_batch(
        self,
        user_pattern: Dict,
        card_contexts: List[Dict]
    ) -> List[Dict]:
        """
        여러 카드에 대해 배치 분석
        
        Args:
            user_pattern: 사용자 소비 패턴
            card_contexts: 카드 컨텍스트 리스트
        
        Returns:
            분석 결과 리스트
        """
        results = []
        for card_context in card_contexts:
            try:
                result = self.analyze(user_pattern, card_context)
                results.append(result)
            except Exception as e:
                print(f"⚠️  분석 실패 (card_id={card_context.get('card_id')}): {e}")
                # 실패한 경우 기본값
                results.append({
                    "card_id": card_context.get("card_id"),
                    "monthly_savings": 0,
                    "annual_savings": 0,
                    "conditions_met": False,
                    "warnings": [f"분석 실패: {str(e)}"],
                    "category_breakdown": {}
                })
        
        return results


# 사용 예시
def main():
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
    
    result = analyzer.analyze(user_pattern, card_context)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

