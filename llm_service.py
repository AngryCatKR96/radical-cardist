import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core.tools import FunctionTool
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.storage.storage_context import StorageContext
import chromadb
from models import Card, SpendingBreakdown, RecommendationRequest
from optimizer import CardOptimizer

# 환경 변수 로드
load_dotenv()

class CreditCardLLMService:
    def __init__(self):
        self.llm = OpenAI(
            model="gpt-4",
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.1
        )
        Settings.llm = self.llm
        
        # 카드 데이터 로드
        self.cards = self._load_cards()
        self.optimizer = CardOptimizer(self.cards)
        
        # 벡터 인덱스 생성
        self.index = self._create_vector_index()
        
        # Function tools 정의
        self.tools = self._create_tools()
    
    def _load_cards(self) -> List[Card]:
        """카드 데이터를 JSON 파일에서 로드합니다."""
        try:
            with open("data/cards.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                return [Card(**card_data) for card_data in data["cards"]]
        except FileNotFoundError:
            print("Warning: cards.json 파일을 찾을 수 없습니다. 빈 카드 목록을 사용합니다.")
            return []
    
    def _create_vector_index(self):
        """카드 정보를 벡터 인덱스로 변환합니다."""
        if not self.cards:
            return None
        
        # 카드 정보를 문서로 변환
        documents = []
        for card in self.cards:
            # 카드 정보를 텍스트로 변환
            card_text = f"""
            카드명: {card.name}
            은행: {card.bank}
            연회비: {card.annual_fee:,}원
            전월 실적 조건: {card.conditions.prev_month_min:,}원
            월 혜택 한도: {card.conditions.benefit_cap:,}원
            
            혜택:
            """
            for benefit in card.benefits:
                card_text += f"- {benefit.category}: {benefit.rate}% 적립/할인, 월 한도 {benefit.monthly_limit:,}원, 최소 구매 {benefit.min_purchase:,}원\n"
            
            documents.append(Document(text=card_text, metadata={"card_id": card.id}))
        
        # ChromaDB 벡터 스토어 생성
        try:
            chroma_client = chromadb.PersistentClient(path="./chroma_db")
            chroma_collection = chroma_client.create_collection("credit_cards")
        except chromadb.db.base.UniqueConstraintError:
            # 이미 존재하는 경우 기존 컬렉션 사용
            chroma_client = chromadb.PersistentClient(path="./chroma_db")
            chroma_collection = chroma_client.get_collection("credit_cards")
        except Exception as e:
            print(f"ChromaDB 컬렉션 생성 중 오류 발생: {str(e)}")
            return None
            
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        # 인덱스 생성
        index = VectorStoreIndex.from_documents(
            documents, 
            storage_context=storage_context
        )
        
        return index
    
    def _create_tools(self) -> List[FunctionTool]:
        """Function Calling을 위한 도구들을 생성합니다."""
        
        def analyze_spending_pattern(spending_breakdown: str) -> str:
            """사용자의 소비 패턴을 분석합니다."""
            try:
                breakdown = json.loads(spending_breakdown)
                total = sum(breakdown.values())
                analysis = f"총 월 소비: {total:,}원\n"
                
                # 카테고리별 비중 분석
                for category, amount in breakdown.items():
                    if amount > 0:
                        percentage = (amount / total) * 100
                        analysis += f"- {category}: {amount:,}원 ({percentage:.1f}%)\n"
                
                return analysis
            except:
                return "소비 패턴 분석에 실패했습니다."
        
        def find_best_cards_for_category(category: str, amount: int) -> str:
            """특정 카테고리에 최적의 카드를 찾습니다."""
            suitable_cards = []
            for card in self.cards:
                for benefit in card.benefits:
                    if benefit.category == category and amount >= benefit.min_purchase:
                        monthly_benefit = min(
                            int(amount * benefit.rate / 100),
                            benefit.monthly_limit
                        )
                        suitable_cards.append({
                            "name": card.name,
                            "bank": card.bank,
                            "rate": benefit.rate,
                            "monthly_benefit": monthly_benefit,
                            "annual_fee": card.annual_fee
                        })
            
            if not suitable_cards:
                return f"{category} 카테고리에 적합한 카드가 없습니다."
            
            # 혜택률 순으로 정렬
            suitable_cards.sort(key=lambda x: x["rate"], reverse=True)
            
            result = f"{category} 카테고리 최적 카드 (월 {amount:,}원 기준):\n"
            for i, card in enumerate(suitable_cards[:3], 1):
                result += f"{i}. {card['name']} ({card['bank']}) - {card['rate']}% 적립, 월 {card['monthly_benefit']:,}원\n"
            
            return result
        
        def calculate_roi(annual_benefit: int, annual_fee: int) -> str:
            """연회비 대비 혜택 ROI를 계산합니다."""
            if annual_fee == 0:
                return "연회비가 없어 ROI 계산이 불가능합니다."
            
            roi = (annual_benefit - annual_fee) / annual_fee * 100
            net_benefit = annual_benefit - annual_fee
            
            if roi > 0:
                return f"ROI: {roi:.1f}%, 연 순혜택: {net_benefit:,}원 (수익성 있음)"
            else:
                return f"ROI: {roi:.1f}%, 연 순혜택: {net_benefit:,}원 (수익성 없음)"
        
        tools = [
            FunctionTool.from_defaults(
                fn=analyze_spending_pattern,
                name="analyze_spending_pattern",
                description="사용자의 소비 패턴을 분석하여 카테고리별 비중을 계산합니다."
            ),
            FunctionTool.from_defaults(
                fn=find_best_cards_for_category,
                name="find_best_cards_for_category",
                description="특정 카테고리에 최적의 카드를 찾아 혜택을 계산합니다."
            ),
            FunctionTool.from_defaults(
                fn=calculate_roi,
                name="calculate_roi",
                description="연회비 대비 혜택의 ROI를 계산합니다."
            )
        ]
        
        return tools
    
    def get_recommendation(self, request: RecommendationRequest) -> Dict[str, Any]:
        """사용자 소비 패턴을 분석하여 최적의 카드 조합을 추천합니다."""
        
        try:
            # 1단계: 소비 패턴 분석
            spending_analysis = self._analyze_spending_with_llm(request)
            
            # 2단계: 카드 최적화
            card_recommendations = self.optimizer.optimize_card_combination(
                request.spending_breakdown,
                request.subscriptions,
                request.monthly_spending
            )
            
            # 3단계: 총 혜택 계산
            monthly_savings, annual_savings, total_annual_fee, net_annual_savings = \
                self.optimizer.calculate_total_savings(card_recommendations)
            
            # 4단계: 추천 텍스트 생성
            recommendation_text = self.optimizer.generate_recommendation_text(
                card_recommendations, monthly_savings, annual_savings
            )
            
            # 5단계: 사용 전략 생성
            usage_strategy = self._generate_usage_strategy(card_recommendations)
            
            # 6단계: LLM을 통한 최종 분석 및 조언
            final_analysis = self._get_llm_analysis(
                request, card_recommendations, monthly_savings, annual_savings
            )
            
            return {
                "recommendation_text": final_analysis,
                "selected_cards": card_recommendations,
                "monthly_savings": monthly_savings,
                "annual_savings": annual_savings,
                "usage_strategy": usage_strategy,
                "total_annual_fee": total_annual_fee,
                "net_annual_savings": net_annual_savings,
                "spending_analysis": spending_analysis
            }
            
        except Exception as e:
            return {
                "error": f"추천 생성 중 오류가 발생했습니다: {str(e)}",
                "recommendation_text": "죄송합니다. 추천을 생성할 수 없습니다.",
                "selected_cards": [],
                "monthly_savings": 0,
                "annual_savings": 0,
                "usage_strategy": "",
                "total_annual_fee": 0,
                "net_annual_savings": 0
            }
    
    def _analyze_spending_with_llm(self, request: RecommendationRequest) -> str:
        """LLM을 사용하여 소비 패턴을 분석합니다."""
        if not self.index:
            return "벡터 인덱스를 사용할 수 없습니다."
        
        query_engine = self.index.as_query_engine()
        
        prompt = f"""
        다음 소비 패턴을 분석하고 신용카드 선택에 도움이 되는 인사이트를 제공해주세요:
        
        월 총 소비: {request.monthly_spending:,}원
        카테고리별 소비:
        {json.dumps(request.spending_breakdown.model_dump(), ensure_ascii=False, indent=2)}
        구독 서비스: {', '.join(request.subscriptions)}
        
        다음을 분석해주세요:
        1. 소비 패턴의 특징
        2. 카드 선택 시 고려사항
        3. 절약 가능한 영역
        """
        
        try:
            response = query_engine.query(prompt)
            return str(response)
        except:
            return "LLM 분석을 수행할 수 없습니다."
    
    def _generate_usage_strategy(self, card_recommendations: List[Any]) -> str:
        """카드별 사용 전략을 생성합니다."""
        if not card_recommendations:
            return "추천된 카드가 없습니다."
        
        strategy_parts = []
        for rec in card_recommendations:
            if hasattr(rec, 'usage_strategy'):
                strategy_parts.append(rec.usage_strategy)
            else:
                strategy_parts.append(f"{rec.card.name}: 사용 전략을 생성할 수 없습니다.")
        
        return "\n\n".join(strategy_parts)
    
    def _get_llm_analysis(self, request: RecommendationRequest, 
                          card_recommendations: List[Any], 
                          monthly_savings: int, 
                          annual_savings: int) -> str:
        """LLM을 통한 최종 분석 및 조언을 생성합니다."""
        
        if not self.index:
            return "LLM 분석을 수행할 수 없습니다."
        
        query_engine = self.index.as_query_engine()
        
        # 카드 정보 요약
        cards_summary = []
        for rec in card_recommendations:
            if hasattr(rec, 'card'):
                card = rec.card
                cards_summary.append(f"- {card.name} ({card.bank}): 연회비 {card.annual_fee:,}원")
        
        prompt = f"""
        다음 신용카드 추천 결과를 분석하고 사용자에게 친근하고 실용적인 조언을 제공해주세요:
        
        사용자 소비 패턴:
        - 월 총 소비: {request.monthly_spending:,}원
        - 주요 소비 카테고리: {', '.join([k for k, v in request.spending_breakdown.model_dump().items() if v > 0])}
        - 구독 서비스: {', '.join(request.subscriptions)}
        
        추천된 카드:
        {chr(10).join(cards_summary)}
        
        예상 절약 효과:
        - 월 절약: {monthly_savings:,}원
        - 연 절약: {annual_savings:,}원
        
        다음 형식으로 답변해주세요:
        1. 간단한 인사말과 함께 추천 요약
        2. 각 카드의 핵심 장점
        3. 실제 사용 시 주의사항
        4. 추가 절약 팁
        
        친근하고 실용적인 톤으로 답변해주세요.
        """
        
        try:
            response = query_engine.query(prompt)
            return str(response)
        except:
            # LLM 분석 실패 시 기본 추천 텍스트 반환
            return f"""
            💳 신용카드 추천 결과
            
            월 {request.monthly_spending:,}원 소비 패턴을 분석한 결과, 
            총 {len(card_recommendations)}개 카드 조합을 추천드립니다.
            
            📊 예상 절약 효과
            • 월 절약: {monthly_savings:,}원
            • 연 절약: {annual_savings:,}원
            
            🎯 사용 전략
            각 카드의 혜택을 최대한 활용하여 카테고리별로 최적화된 결제를 진행하시면 됩니다.
            
            💡 추가 팁
            • 전월 실적 조건을 꼭 확인하세요
            • 월 한도를 초과하지 않도록 주의하세요
            • 정기적으로 혜택을 확인하고 활용하세요
            """
