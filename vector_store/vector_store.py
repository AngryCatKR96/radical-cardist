"""
벡터 스토어 검색 모듈

MongoDB Vector Search에서 벡터 검색을 수행하고,
카드 단위로 집계하여 Top-M 후보를 선정합니다.
"""

import math
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()


class CardVectorStore:
    """벡터 스토어 검색 클래스 (MongoDB 전용)"""

    def __init__(self):
        """CardVectorStore 초기화 (MongoDB 전용)"""
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # MongoDB 연결 (필수)
        from database.mongodb_client import MongoDBClient
        self.mongo_client = MongoDBClient()
        self.cards_collection = self.mongo_client.get_collection("cards")
        print("✅ CardVectorStore: MongoDB 연결됨")
    
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
    
    def _build_mongodb_filter(self, filters: Optional[Dict]) -> Dict:
        """
        메타데이터 필터를 MongoDB 형식으로 변환

        Args:
            filters: 필터 딕셔너리

        Returns:
            MongoDB filter 객체
        """
        # NOTE: 스키마 필드 경로는 여기서만 관리(유지보수성)
        FIELD_IS_DISCON = "is_discon"
        FIELD_META_TYPE = "meta.type"
        FIELD_COND_PREV_MONTH_MIN = "conditions.prev_month_min"

        mongo_filter: Dict[str, Any] = {FIELD_IS_DISCON: False}  # 항상 단종 카드 제외

        if not filters:
            return mongo_filter

        # None 값을 가진 키 제거
        filters = {k: v for k, v in filters.items() if v is not None}

        # 카드 유형 필터
        card_type = filters.get("type")
        if card_type:
            if card_type == "credit":
                mongo_filter[FIELD_META_TYPE] = "C"
            elif card_type == "debit":
                mongo_filter[FIELD_META_TYPE] = "D"
            # "both"인 경우 필터 없음

        # 전월실적 필터
        pre_month_max = filters.get("pre_month_min_max")
        if pre_month_max is not None:
            mongo_filter[FIELD_COND_PREV_MONTH_MIN] = {
                "$lte": pre_month_max
            }

        # 온라인 전용 필터
        if filters.get("only_online") is True:
            # 실제 저장 경로가 다양할 수 있어 OR로 방어적으로 처리
            mongo_filter["$or"] = [
                {"only_online": True},
                {"meta.only_online": True},
                {"conditions.only_online": True},
            ]

        # 연회비 필터는 post-processing에서 처리 (메타데이터에 있음)

        return mongo_filter

    def _cosine_similarity(self, a: Iterable[float], b: Iterable[float]) -> float:
        """
        코사인 유사도 계산 (외부 라이브러리 없이)
        """
        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for x, y in zip(a, b):
            fx = float(x)
            fy = float(y)
            dot += fx * fy
            norm_a += fx * fx
            norm_b += fy * fy
        if norm_a <= 0.0 or norm_b <= 0.0:
            return 0.0
        return dot / math.sqrt(norm_a * norm_b)

    def _extract_annual_fee_total(self, fees: Optional[Dict[str, Any]]) -> Optional[int]:
        """
        fees에서 숫자 연회비(가능한 경우)를 추출합니다.
        - MongoDB Atlas Vector Search score는 metric 보장이 없으므로, 연회비는 별도 파싱으로 하드필터에 사용합니다.
        """
        if not isinstance(fees, dict):
            return None
        text = fees.get("annual_detail") or fees.get("annual_basic") or ""
        if not isinstance(text, str) or not text:
            return None
        m = re.search(r"(\d{1,3}(?:,\d{3})*)", text)
        if not m:
            return None
        try:
            return int(m.group(1).replace(",", ""))
        except Exception:
            return None

    def search_chunks(
        self,
        query_text: str,
        filters: Optional[Dict] = None,
        top_k: int = 50
    ) -> List[Dict]:
        """
        Chunk 단위 검색 (MongoDB Vector Search)

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

        # MongoDB Vector Search (카드 문서 후보만 뽑고, 청크별 유사도는 파이썬에서 재계산)
        mongo_filter = self._build_mongodb_filter(filters)

        # 1차: 카드 후보 오버패치(카드 단위). 이후 카드별 embeddings를 순회하며 chunk evidence를 선정.
        # - 너무 큰 numCandidates는 비용/레이턴시에 직결되므로 보수적으로 설정
        candidate_cards = min(200, max(30, int(top_k)))
        num_candidates = min(1000, max(100, candidate_cards * 3))

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "card_vector_search",
                    "path": "embeddings.embedding",
                    "queryVector": query_embedding,
                    "numCandidates": num_candidates,
                    "limit": candidate_cards,
                    "filter": mongo_filter
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "card_id": 1,
                    "meta": 1,
                    "conditions": 1,
                    "fees": 1,
                    "hints": 1,
                    "is_discon": 1,
                    "embeddings.doc_id": 1,
                    "embeddings.doc_type": 1,
                    "embeddings.text": 1,
                    "embeddings.metadata": 1,
                    "embeddings.embedding": 1,
                    # 카드 후보 점수(카드 문서 단위). 청크 유사도와 동일시하면 안 됨.
                    "vector_score": {"$meta": "vectorSearchScore"},
                }
            }
        ]

        candidates = list(self.cards_collection.aggregate(pipeline))

        # 2차: 후보 카드들의 embeddings를 순회하며 청크별 cosine 유사도 계산
        # - 벡터 검색 대상: summary / benefit_core / notes
        VECTOR_DOC_TYPES = {"summary", "benefit_core", "notes"}
        chunks: List[Dict[str, Any]] = []
        for card in candidates:
            if not isinstance(card, dict):
                continue

            card_id = card.get("card_id")
            if not isinstance(card_id, int):
                continue

            meta = card.get("meta") if isinstance(card.get("meta"), dict) else {}
            conditions = card.get("conditions") if isinstance(card.get("conditions"), dict) else {}
            fees = card.get("fees") if isinstance(card.get("fees"), dict) else {}
            hints = card.get("hints") if isinstance(card.get("hints"), dict) else {}

            card_name = meta.get("name") if isinstance(meta.get("name"), str) else ""
            issuer = meta.get("issuer") if isinstance(meta.get("issuer"), str) else ""
            card_type = meta.get("type") if isinstance(meta.get("type"), str) else ""
            prev_month_min = conditions.get("prev_month_min", 0) or 0
            annual_fee_total = self._extract_annual_fee_total(fees)
            brand = ""
            try:
                brands = hints.get("brands", [])
                if isinstance(brands, list):
                    brand = ", ".join([b for b in brands if isinstance(b, str)])
            except Exception:
                brand = ""

            embeddings = card.get("embeddings") or []
            if not isinstance(embeddings, list) or not embeddings:
                continue

            for emb in embeddings:
                if not isinstance(emb, dict):
                    continue
                emb_vec = emb.get("embedding")
                if not isinstance(emb_vec, list) or not emb_vec:
                    continue

                doc_type = emb.get("doc_type")
                embed_meta = emb.get("metadata") if isinstance(emb.get("metadata"), dict) else {}
                dt_str = str(doc_type) if isinstance(doc_type, str) else str(embed_meta.get("doc_type") or "")
                if dt_str and dt_str not in VECTOR_DOC_TYPES:
                    continue

                score = self._cosine_similarity(query_embedding, emb_vec)

                doc_id = emb.get("doc_id")
                text = emb.get("text")

                # 안전한 metadata 구성 (KeyError 방지)
                md: Dict[str, Any] = {
                    "card_id": card_id,
                    "name": card_name,
                    "issuer": issuer,
                    "brand": brand,
                    "type": card_type,
                    "prev_month_min": int(prev_month_min) if isinstance(prev_month_min, (int, float)) else 0,
                    "annual_fee_total": annual_fee_total,
                    "doc_type": dt_str,
                    "is_discon": bool(card.get("is_discon", False)),
                }
                # embed metadata 우선 병합(단, 위 카드 메타를 덮어쓰지 않도록)
                for k, v in embed_meta.items():
                    if k not in md:
                        md[k] = v

                chunks.append(
                    {
                        "id": str(doc_id) if doc_id is not None else f"{card_id}_unknown",
                        "text": str(text) if isinstance(text, str) else "",
                        "metadata": md,
                        # score는 cosine 기반(클수록 유사). distance로 임의 변환하지 않음.
                        "score": float(score),
                    }
                )

        # 청크 단위 score로 정렬 후 top_k 반환
        chunks.sort(key=lambda x: float(x.get("score", 0.0) or 0.0), reverse=True)
        return chunks[:top_k]
    
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
        # filters 초기화 (None이면 빈 딕셔너리)
        if filters is None:
            filters = {}
        else:
            # None 값을 가진 키 제거
            filters = {k: v for k, v in filters.items() if v is not None}
        
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
            
            # search_chunks에서 이미 청크 단위 score(cosine)를 포함
            score_val = chunk.get("score", 0.0) or 0.0
            chunk["score"] = float(score_val)
            cards_dict[card_id]["chunks"].append(chunk)
        
        # 3. 카드별 증거 캡 및 점수 집계
        candidates = []
        user_categories = self._extract_user_categories(query_text, filters)
        user_keywords = self._extract_user_keywords(query_text)
        
        for card_id, card_data in cards_dict.items():
            chunks = card_data["chunks"]
            
            # 우선순위 정렬: 사용자 카테고리 일치 benefit_core → notes → summary
            def chunk_priority(chunk):
                doc_type = chunk["metadata"].get("doc_type", "")
                category_std = chunk["metadata"].get("category_std", "")
                
                if doc_type == "benefit_core" and category_std in user_categories:
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

            # ===== 카드 점수 (요구사항 반영) =====
            # card_score = max(core_chunk_scores)
            core_scores = sorted(
                [c["score"] for c in chunks if c.get("metadata", {}).get("doc_type") == "benefit_core"],
                reverse=True,
            )
            if not core_scores:
                # core가 없으면 폴백: 전체에서 max
                core_scores = sorted([c["score"] for c in chunks], reverse=True)
            if not core_scores:
                continue

            base_score = core_scores[0]

            # 같은 카드에서 상위 2~3개가 같이 높으면 가중치 보너스
            bonus = 0.0
            if len(core_scores) > 1 and core_scores[1] >= base_score * 0.90:
                bonus += 0.04
            if len(core_scores) > 2 and core_scores[2] >= base_score * 0.85:
                bonus += 0.02
            
            # 커버리지 보너스
            matched_categories = set()
            for chunk in evidence_chunks:
                category_std = chunk["metadata"].get("category_std")
                if category_std and category_std in user_categories:
                    matched_categories.add(category_std)
            coverage_bonus = len(matched_categories) * 0.08  # 카테고리당 보너스(조금 완화)
            
            # 하드 필터(반드시 만족) vs 소프트 점수 요소(coverage 등) 분리
            metadata = evidence_chunks[0].get("metadata") or {}

            pre_month_max = filters.get("pre_month_min_max") if filters else None
            if pre_month_max is not None:
                prev_month_min = metadata.get("prev_month_min", 0) or 0
                try:
                    if int(prev_month_min) > int(pre_month_max):
                        continue
                except Exception:
                    pass

            annual_fee_max = filters.get("annual_fee_max") if filters else None
            if annual_fee_max is not None:
                annual_fee = metadata.get("annual_fee_total")
                if isinstance(annual_fee, (int, float)) and annual_fee is not None:
                    try:
                        if float(annual_fee) > float(annual_fee_max):
                            continue
                    except Exception:
                        pass

            # 최종 점수(소프트 요소만)
            total_score = base_score + bonus + coverage_bonus
            
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
                    "bonus": bonus,
                    "coverage_bonus": coverage_bonus,
                    "total_score": total_score,
                    "normalized_score": normalized_score
                }
            })
        
        # 4. 점수 순 정렬
        candidates_sorted = sorted(
            candidates,
            key=lambda c: c["aggregate_score"],
            reverse=True
        )

        # 5. benefit_exclusion 룰 기반 필터(벡터 X)
        # - non_vector_docs 중 benefit_exclusion 텍스트에 사용자 키워드가 포함되면 후보에서 제외
        filtered: List[Dict[str, Any]] = []
        for cand in candidates_sorted:
            cid = cand.get("card_id")
            if not isinstance(cid, int):
                continue
            try:
                doc = self.cards_collection.find_one({"card_id": cid}, {"non_vector_docs": 1, "_id": 0}) or {}
                nv = doc.get("non_vector_docs") or []
                exclusion_text = " ".join(
                    [
                        (d.get("text") or "")
                        for d in nv
                        if isinstance(d, dict) and d.get("doc_type") == "benefit_exclusion"
                    ]
                )
                if exclusion_text:
                    # 키워드가 exclusion에 명시적으로 등장하면 제외
                    if any(k in exclusion_text for k in user_keywords):
                        continue
            except Exception:
                # 필터링 실패는 fail-open
                pass
            filtered.append(cand)
            if len(filtered) >= top_m:
                break

        return filtered

    def _extract_user_keywords(self, query_text: str) -> List[str]:
        """
        룰 기반 exclusion 필터용 키워드 추출(간단)
        - exclusion 텍스트에 해당 키워드가 포함되면 후보에서 제외할 때 사용
        """
        keywords = []
        keyword_list = [
            "마트", "대형마트", "장보기", "편의점", "카페", "커피", "스타벅스",
            "간편결제", "네이버페이", "카카오페이", "삼성페이", "애플페이",
            "넷플릭스", "유튜브", "OTT", "디즈니", "티빙", "웨이브",
            "배달", "배달앱", "대중교통", "교통", "주유", "온라인쇼핑",
        ]
        for k in keyword_list:
            if k in query_text:
                keywords.append(k)
        return keywords
    
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
            "장보기": "grocery",
            "식료품": "grocery",
            "생필품": "grocery",
            "편의점": "convenience",
            "카페": "cafe",
            "커피": "cafe",
            "스타벅스": "cafe",
            "간편결제": "digital_payment",
            "네이버페이": "digital_payment",
            "카카오페이": "digital_payment",
            "삼성페이": "digital_payment",
            "애플페이": "digital_payment",
            "구독": "subscription_video",
            "넷플릭스": "subscription_video",
            "유튜브": "subscription_video",
            "OTT": "subscription_video",
            "디즈니": "subscription_video",
            "티빙": "subscription_video",
            "웨이브": "subscription_video",
            "주유": "fuel",
            "배달": "delivery_app",
            "배달앱": "delivery_app",
            "대중교통": "transit",
            "교통": "transit",
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

