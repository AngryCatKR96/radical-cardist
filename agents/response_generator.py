"""
응답 생성 Agent

추천 결과를 사용자 친화적인 자연어로 변환합니다.
"""

import json
from typing import Dict, Optional
from openai import OpenAI
import os
from dotenv import load_dotenv
from data_collection.data_parser import load_compressed_context

load_dotenv()


class ResponseGenerator:
    """응답 생성 Agent"""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-5-mini"
    
    def generate(
        self,
        recommendation_result: Dict,
        user_pattern: Optional[Dict] = None
    ) -> str:
        """
        추천 결과를 자연어로 변환
        
        Args:
            recommendation_result: 추천 결과 Dict
            user_pattern: 사용자 소비 패턴 (선택적)
        
        Returns:
            자연어 추천 텍스트
        """
        card_id = recommendation_result.get("selected_card")
        if not card_id:
            return "추천할 카드를 찾을 수 없습니다."
        
        # 카드 정보 로드
        card_data = load_compressed_context(card_id)
        if not card_data:
            return f"카드 정보를 불러올 수 없습니다 (card_id={card_id})"
        
        meta = card_data.get("meta", {})
        conditions = card_data.get("conditions", {})
        fees = card_data.get("fees", {})
        
        # 사용자 패턴 요약
        user_summary = ""
        if user_pattern:
            spending = user_pattern.get("spending", {})
            spending_list = []
            for category, data in spending.items():
                if isinstance(data, dict):
                    amount = data.get("amount", 0)
                    if amount > 0:
                        spending_list.append(f"{category} {amount:,}원/월")
            if spending_list:
                user_summary = "\n".join(spending_list)
        
        # LLM 호출
        prompt = f"""다음은 신용카드 추천 결과입니다.

[추천 카드]
- 이름: {meta.get('name', '')}
- 발급사: {meta.get('issuer', '')}
- 전월실적 조건: {conditions.get('prev_month_min', 0):,}원 이상
- 연회비: {fees.get('annual_detail', '')}

[예상 절약액]
- 연 절약액: {recommendation_result.get('annual_savings', 0):,}원
- 연회비: {recommendation_result.get('annual_fee', 0):,}원
- 순 혜택: {recommendation_result.get('score_breakdown', {}).get('net_benefit', 0):,}원

[카테고리별 절약액]
{json.dumps(recommendation_result.get('category_breakdown', {}), ensure_ascii=False, indent=2)}

[주의사항]
{chr(10).join(recommendation_result.get('warnings', []))}

[사용자 소비 패턴]
{user_summary if user_summary else '정보 없음'}

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
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 신용카드 추천 전문가입니다. 사용자에게 친절하고 이해하기 쉬운 추천 설명을 작성합니다."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=1.0  # gpt-5-mini는 temperature=1만 지원
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            # LLM 실패 시 기본 템플릿 사용
            return self._generate_fallback_response(recommendation_result, card_data)
    
    def _generate_fallback_response(self, recommendation_result: Dict, card_data: Dict) -> str:
        """
        LLM 실패 시 기본 템플릿 응답 생성
        
        Args:
            recommendation_result: 추천 결과
            card_data: 카드 데이터
        
        Returns:
            기본 템플릿 응답
        """
        meta = card_data.get("meta", {})
        name = meta.get("name", "")
        annual_savings = recommendation_result.get("annual_savings", 0)
        annual_fee = recommendation_result.get("annual_fee", 0)
        net_benefit = recommendation_result.get("score_breakdown", {}).get("net_benefit", 0)
        
        response = f"""추천 카드: {name}

예상 절약액:
- 연 절약액: {annual_savings:,}원
- 연회비: {annual_fee:,}원
- 순 혜택: {net_benefit:,}원

주의사항:
{chr(10).join('- ' + w for w in recommendation_result.get('warnings', []))}
"""
        
        return response


# 사용 예시
def main():
    """테스트용 메인 함수"""
    generator = ResponseGenerator()
    
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


if __name__ == "__main__":
    main()

