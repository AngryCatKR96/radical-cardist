"""
벡터 스토어 검색 모듈

ChromaDB에서 벡터 검색을 수행하고, 카드 단위로 집계하여 Top-M 후보를 선정합니다.
"""

import math
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
import os
import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv

load_dotenv()


class CardVectorStore:
    """벡터 스토어 검색 클래스"""
    
    def __init__(self, chroma_db_path: str = "chroma_db", collection_name: str = "credit_cards"):
        """
        Args:
            chroma_db_path: ChromaDB 저장 경로
            collection_name: 컬렉션 이름
        """
        self.chroma_db_path = chroma_db_path
        self.collection_name = collection_name
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # ChromaDB 클라이언트 초기화
        self.chroma_client = chromadb.PersistentClient(
            path=chroma_db_path,
            settings=Settings(anonymized_telemetry=False)
        )
        
        try:
            self.collection = self.chroma_client.get_collection(name=collection_name)
        except:
            raise ValueError(f"컬렉션 '{collection_name}'을 찾을 수 없습니다. 먼저 embeddings.py로 데이터를 추가하세요.")
    
    def _generate_query_embedding(self, query_text: str) -> List[float]:
        """
        질의 텍스트를 임베딩으로 변환
        
        Args:
            query_text: 검색 질의
        
        Returns:
            임베딩 벡터
        """
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=[query_text]
            )
            return response.data[0].embedding
        except Exception as e:
            raise ValueError(f"임베딩 생성 실패: {e}")
    
    def _apply_metadata_filters(self, filters: Dict) -> Optional[Dict]:
        """
        메타데이터 필터를 ChromaDB 형식으로 변환
        
        Args:
            filters: 필터 딕셔너리
        
        Returns:
            ChromaDB where 절
        """
        conditions = []
        
        # 연회비 필터
        if "annual_fee_max" in filters:
            # ChromaDB는 범위 쿼리를 직접 지원하지 않으므로,
            # 여기서는 필터링을 검색 후에 수행
            pass
        
        # 전월실적 필터
        if "pre_month_min_max" in filters:
            # 마찬가지로 검색 후 필터링
            pass
        
        # 카드 유형 필터
        if "type" in filters:
            card_type = filters["type"]
            if card_type in ["credit", "debit"]:
                type_map = {"credit": "C", "debit": "D"}
                conditions.append({"type": type_map.get(card_type)})
            # "both"인 경우 필터 없음
        
        # 온라인 전용 필터
        if filters.get("only_online"):
            conditions.append({"only_online": True})
        
        # 단종 카드 제외 (항상 적용)
        conditions.append({"is_discon": False})
        
        # 조건이 없으면 None 반환
        if not conditions:
            return None
        
        # 조건이 1개면 그대로, 여러 개면 $and 사용
        if len(conditions) == 1:
            return conditions[0]
        else:
            return {"$and": conditions}
    
    def search_chunks(
        self,
        query_text: str,
        filters: Optional[Dict] = None,
        top_k: int = 50
    ) -> List[Dict]:
        """
        Chunk 단위 검색
        
        Args:
            query_text: 검색 질의
            filters: 메타데이터 필터
            top_k: 반환할 최대 문서 수
        
        Returns:
            검색 결과 리스트 [{id, text, metadata, distance}, ...]
        """
        if filters is None:
            filters = {}
        
        # 질의 임베딩 생성
        query_embedding = self._generate_query_embedding(query_text)
        
        # 메타데이터 필터 적용
        where_clause = self._apply_metadata_filters(filters)
        
        # 검색
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_clause
            )
        except Exception as e:
            raise ValueError(f"검색 실패: {e}")
        
        # 결과 포맷팅
        chunks = []
        if results["ids"] and len(results["ids"][0]) > 0:
            for i in range(len(results["ids"][0])):
                chunk = {
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if "distances" in results else None
                }
                chunks.append(chunk)
        
        return chunks
    
    def search_cards(
        self,
        query_text: str,
        filters: Optional[Dict] = None,
        top_m: int = 5,
        evidence_per_card: int = 3
    ) -> List[Dict]:
        """
        카드 단위 검색 및 집계 (Top-M 선정)
        
        Args:
            query_text: 검색 질의
            filters: 메타데이터 필터
            top_m: 반환할 최대 카드 수
            evidence_per_card: 카드당 최대 증거 문서 수
        
        Returns:
            카드 후보 리스트 [{card_id, name, evidence_chunks, aggregate_score}, ...]
        """
        # 1. Chunk 단위 검색
        chunks = self.search_chunks(query_text, filters, top_k=50)
        
        if not chunks:
            return []
        
        # 2. 카드 단위 그룹화
        cards_dict = {}
        for chunk in chunks:
            card_id = chunk["metadata"].get("card_id")
            if not card_id:
                continue
            
            if card_id not in cards_dict:
                cards_dict[card_id] = {
                    "card_id": card_id,
                    "name": chunk["metadata"].get("name", ""),
                    "chunks": []
                }
            
            # 유사도 점수 계산 (distance를 점수로 변환)
            distance = chunk.get("distance", 1.0)
            score = 1.0 - distance  # 거리가 작을수록 점수 높음
            chunk["score"] = score
            
            cards_dict[card_id]["chunks"].append(chunk)
        
        # 3. 카드별 증거 캡 및 점수 집계
        candidates = []
        user_categories = self._extract_user_categories(query_text, filters)
        
        for card_id, card_data in cards_dict.items():
            chunks = card_data["chunks"]
            
            # 우선순위 정렬: 사용자 카테고리 일치 benefit → notes → summary
            def chunk_priority(chunk):
                doc_type = chunk["metadata"].get("doc_type", "")
                category_std = chunk["metadata"].get("category_std", "")
                
                if doc_type == "benefit" and category_std in user_categories:
                    return 0  # 최우선
                elif doc_type == "notes":
                    return 1
                elif doc_type == "summary":
                    return 2
                else:
                    return 3
            
            chunks_sorted = sorted(chunks, key=lambda c: (chunk_priority(c), -c["score"]))
            
            # 증거 캡
            evidence_chunks = chunks_sorted[:evidence_per_card]
            
            # 점수 집계
            scores = [c["score"] for c in evidence_chunks]
            if not scores:
                continue
            
            # 기본 점수: s1 + 0.6*s2 + 0.3*s3
            base_score = scores[0]
            if len(scores) > 1:
                base_score += 0.6 * scores[1]
            if len(scores) > 2:
                base_score += 0.3 * scores[2]
            
            # 커버리지 보너스
            matched_categories = set()
            for chunk in evidence_chunks:
                category_std = chunk["metadata"].get("category_std")
                if category_std and category_std in user_categories:
                    matched_categories.add(category_std)
            coverage_bonus = len(matched_categories) * 0.1  # 카테고리당 0.1점
            
            # 패널티 계산
            penalties = 0.0
            metadata = evidence_chunks[0]["metadata"]
            
            # 전월실적 미충족
            prev_month_min = metadata.get("prev_month_min", 0)
            pre_month_max = filters.get("pre_month_min_max", float('inf'))
            if prev_month_min > pre_month_max:
                penalties += 0.5
            
            # 연회비 상한 초과
            annual_fee = metadata.get("annual_fee_total")
            annual_fee_max = filters.get("annual_fee_max", float('inf'))
            if annual_fee and annual_fee > annual_fee_max:
                penalties += 0.3
            
            # 최종 점수
            total_score = base_score + coverage_bonus - penalties
            
            # 정규화 (카드의 총 문서 수로 나누기)
            total_chunks = len(chunks)
            if total_chunks > 0:
                normalized_score = total_score / math.sqrt(total_chunks)
            else:
                normalized_score = total_score
            
            candidates.append({
                "card_id": card_id,
                "name": card_data["name"],
                "evidence_chunks": evidence_chunks,
                "aggregate_score": normalized_score,
                "score_breakdown": {
                    "base_score": base_score,
                    "coverage_bonus": coverage_bonus,
                    "penalties": penalties,
                    "total_score": total_score,
                    "normalized_score": normalized_score
                }
            })
        
        # 4. 점수 순 정렬 및 Top-M 선정
        candidates_sorted = sorted(
            candidates,
            key=lambda c: c["aggregate_score"],
            reverse=True
        )
        
        # 추가 필터링 (메타데이터 기반)
        filtered_candidates = []
        for candidate in candidates_sorted:
            metadata = candidate["evidence_chunks"][0]["metadata"]
            
            # 전월실적 필터
            if "pre_month_min_max" in filters:
                prev_month_min = metadata.get("prev_month_min", 0)
                if prev_month_min > filters["pre_month_min_max"]:
                    continue
            
            # 연회비 필터
            if "annual_fee_max" in filters:
                annual_fee = metadata.get("annual_fee_total")
                if annual_fee and annual_fee > filters["annual_fee_max"]:
                    continue
            
            filtered_candidates.append(candidate)
        
        return filtered_candidates[:top_m]
    
    def _extract_user_categories(self, query_text: str, filters: Dict) -> set:
        """
        사용자 카테고리 추출 (간단한 휴리스틱)
        
        Args:
            query_text: 검색 질의
            filters: 필터
        
        Returns:
            카테고리 세트
        """
        categories = set()
        
        # 키워드 매핑
        keyword_map = {
            "마트": "grocery",
            "대형마트": "grocery",
            "편의점": "convenience",
            "카페": "cafe",
            "간편결제": "digital_payment",
            "네이버페이": "digital_payment",
            "카카오페이": "digital_payment",
            "구독": "subscription_video",
            "넷플릭스": "subscription_video",
            "유튜브": "subscription_video",
            "OTT": "subscription_video",
            "주유": "fuel",
            "배달": "delivery_app",
            "대중교통": "transit",
        }
        
        query_lower = query_text.lower()
        for keyword, category in keyword_map.items():
            if keyword in query_lower or keyword in query_text:
                categories.add(category)
        
        return categories


# 사용 예시
def main():
    """테스트용 메인 함수"""
    store = CardVectorStore()
    
    # 검색 테스트
    query = "마트 30만원, OTT 구독, 간편결제 많이 사용, 연회비 2만원 이하, 체크카드 선호"
    filters = {
        "annual_fee_max": 20000,
        "pre_month_min_max": 500000,
        "type": "debit"
    }
    
    candidates = store.search_cards(query, filters, top_m=5)
    
    print(f"검색 결과: {len(candidates)}개 카드")
    for i, candidate in enumerate(candidates, 1):
        print(f"\n{i}. {candidate['name']} (card_id={candidate['card_id']})")
        print(f"   점수: {candidate['aggregate_score']:.3f}")
        print(f"   증거 문서: {len(candidate['evidence_chunks'])}개")


if __name__ == "__main__":
    main()

