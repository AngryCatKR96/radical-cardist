"""
자연어 입력 파서 Agent

사용자의 자연어 입력을 구조화된 UserIntent로 변환합니다.
LLM Function Calling을 사용하여 정확한 구조화를 수행합니다.
"""

import json
from typing import Dict, Optional
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()


class InputParser:
    """자연어 입력 파서"""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-5-mini"
    
    def _get_function_schema(self) -> Dict:
        """Function Calling 스키마 반환"""
        return {
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
                                "amount": {
                                    "type": "number",
                                    "description": "월 지출 금액 (원)"
                                },
                                "merchants": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "주로 이용하는 가맹점/서비스 (예: 스타벅스, 넷플릭스)"
                                },
                                "payment_methods": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "주로 사용하는 결제 수단 (예: 네이버페이, 카카오페이)"
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "추가 정보 (예: 주말에만 이용, 평일 점심 시간대)"
                                }
                            },
                            "required": ["amount"]
                        }
                    },
                    "subscriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "구독 중인 서비스 목록 (예: 넷플릭스, 유튜브프리미엄, 쿠팡와우)"
                    },
                    "preferences": {
                        "type": "object",
                        "properties": {
                            "card_count_preference": {
                                "type": "string",
                                "enum": ["1", "2", "3", "2-3"],
                                "description": "원하는 카드 개수"
                            },
                            "max_annual_fee": {
                                "type": "number",
                                "description": "최대 연회비 (원)"
                            },
                            "prefer_types": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": ["credit", "debit", "both"]
                                },
                                "description": "선호하는 카드 유형"
                            },
                            "prefer_brands": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "선호하는 브랜드 (예: Visa, Mastercard)"
                            },
                            "exclude_banks": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "제외하고 싶은 발급사"
                            },
                            "only_online": {
                                "type": "boolean",
                                "description": "온라인 전용 카드만 원하는지 여부"
                            }
                        }
                    },
                    "constraints": {
                        "type": "object",
                        "properties": {
                            "pre_month_spending_estimate": {
                                "type": "number",
                                "description": "예상 전월 실적 (원)"
                            },
                            "must_include_categories": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "반드시 포함되어야 하는 카테고리"
                            },
                            "must_exclude_categories": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "제외해야 하는 카테고리"
                            }
                        }
                    },
                    "confidence": {
                        "type": "number",
                        "description": "추출 신뢰도 (0-1)",
                        "minimum": 0,
                        "maximum": 1
                    },
                    "uncertainties": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "불확실한 부분이나 모호한 정보"
                    },
                    "query_text": {
                        "type": "string",
                        "description": "벡터 검색용 자연어 요약 (예: '마트 30만원, OTT 구독, 간편결제 많이 사용, 연회비 2만원 이하, 체크카드 선호')"
                    },
                    "filters": {
                        "type": "object",
                        "properties": {
                            "annual_fee_max": {
                                "type": "number",
                                "description": "최대 연회비 필터 (원)"
                            },
                            "pre_month_min_max": {
                                "type": "number",
                                "description": "최대 전월실적 조건 (원)"
                            },
                            "type": {
                                "type": "string",
                                "enum": ["credit", "debit", "both"],
                                "description": "카드 유형 필터"
                            },
                            "only_online": {
                                "type": "boolean",
                                "description": "온라인 전용 필터"
                            }
                        }
                    }
                },
                "required": ["spending", "query_text", "filters"]
            }
        }
    
    def parse(self, user_input: str) -> Dict:
        """
        자연어 입력을 구조화된 UserIntent로 변환
        
        Args:
            user_input: 사용자 자연어 입력
        
        Returns:
            UserIntent Dict
        """
        function_schema = self._get_function_schema()
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 사용자의 자연어 소비 패턴 입력을 구조화된 데이터로 변환하는 전문가입니다. 사용자가 언급한 모든 정보를 정확하게 추출하세요. 특히 '연회비 2만원 이하'와 같은 조건이 있을 때, '넘어도 된다', '선호한다' 등의 유연한 표현이 함께 있다면 이를 강제 필터(filters)가 아닌 선호사항(preferences)으로 분류해야 합니다. '절대', '무조건', '이상은 안됨' 등의 강한 표현이 있을 때만 filters에 값을 설정하세요."
                    },
                    {
                        "role": "user",
                        "content": user_input
                    }
                ],
                tools=[{
                    "type": "function",
                    "function": function_schema
                }],
                tool_choice={"type": "function", "function": {"name": "extract_spending_pattern"}},
                temperature=1.0  # gpt-5-mini는 temperature=1만 지원
            )
            
            # Function call 결과 추출
            message = response.choices[0].message
            if message.tool_calls and len(message.tool_calls) > 0:
                tool_call = message.tool_calls[0]
                arguments = json.loads(tool_call.function.arguments)
                return arguments
            else:
                raise ValueError("Function call이 반환되지 않았습니다")
                
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

