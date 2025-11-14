"""
임베딩 생성 모듈

압축 컨텍스트(1.2 JSON)를 문서로 분해하고, OpenAI Embeddings로 벡터화하여 ChromaDB에 저장합니다.
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from openai import OpenAI
import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv

load_dotenv()


def clean_html(html: str) -> str:
    """
    HTML 태그를 제거하고 텍스트만 추출
    
    Args:
        html: HTML 문자열
    
    Returns:
        정제된 텍스트
    """
    if not html:
        return ""
    
    # HTML 태그 제거
    text = re.sub(r'<[^>]+>', '', html)
    
    # HTML 엔티티 디코딩
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&amp;', '&')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    
    # 줄바꿈 정리 (여러 개의 줄바꿈을 하나로)
    text = re.sub(r'\n\s*\n', '\n', text)
    
    # 앞뒤 공백 제거
    text = text.strip()
    
    return text


def create_summary_document(card_data: Dict) -> Optional[Dict]:
    """
    카드 요약 문서 생성
    
    Args:
        card_data: 압축 컨텍스트 Dict
    
    Returns:
        {text: str, metadata: dict} 또는 None
    """
    meta = card_data.get("meta", {})
    conditions = card_data.get("conditions", {})
    fees = card_data.get("fees", {})
    hints = card_data.get("hints", {})
    
    # 요약 텍스트 생성
    parts = []
    
    # 기본 정보
    issuer = meta.get("issuer", "")
    name = meta.get("name", "")
    brand = ", ".join(hints.get("brands", []))
    card_type = meta.get("type", "")
    type_map = {"C": "신용카드", "D": "체크카드", "P": "선불카드"}
    type_kr = type_map.get(card_type, card_type)
    
    parts.append(f"{issuer} '{name}'")
    if brand:
        parts.append(f"({brand}, {type_kr})")
    elif type_kr:
        parts.append(f"({type_kr})")
    
    # 전월실적 및 연회비
    prev_month = conditions.get("prev_month_min", 0)
    if prev_month > 0:
        parts.append(f"전월실적 {prev_month:,}원 이상")
    
    annual_fee_detail = fees.get("annual_detail", "")
    if annual_fee_detail:
        # 숫자 추출 시도
        fee_match = re.search(r'(\d{1,3}(?:,\d{3})*)', annual_fee_detail)
        if fee_match:
            fee_str = fee_match.group(1).replace(',', '')
            parts.append(f"연회비 {fee_str}원")
    
    # 주요 혜택 요약
    top_tags = hints.get("top_tags", [])
    if top_tags:
        parts.append(f"주요 혜택: {', '.join(top_tags[:3])}")
    
    # 유의사항 언급
    benefits_html = card_data.get("benefits_html", [])
    has_notes = any(b.get("category") == "유의사항" for b in benefits_html)
    if has_notes:
        parts.append("유의사항: 통합할인한도 및 제외 항목 확인 필요")
    
    text = ". ".join(parts) + "."
    
    metadata = {
        "card_id": meta.get("id"),
        "name": name,
        "issuer": issuer,
        "brand": brand if brand else "",
        "type": card_type,
        "prev_month_min": prev_month,
        "doc_type": "summary",
        "is_discon": False
    }
    
    # 연회비 숫자 추출 (선택적)
    if fee_match:
        try:
            metadata["annual_fee_total"] = int(fee_str)
        except:
            pass
    
    return {"text": text, "metadata": metadata}


def create_benefit_document(card_data: Dict, benefit_item: Dict) -> Optional[Dict]:
    """
    혜택 문서 생성
    
    Args:
        card_data: 압축 컨텍스트 Dict
        benefit_item: benefits_html의 항목
    
    Returns:
        {text: str, metadata: dict} 또는 None
    """
    category = benefit_item.get("category", "")
    html = benefit_item.get("html", "")
    
    if not category or not html:
        return None
    
    # HTML 정제
    text = clean_html(html)
    if not text:
        return None
    
    # 카테고리 표준화 매핑
    category_map = {
        "간편결제": "digital_payment",
        "디지털구독": "subscription_video",
        "마트": "grocery",
        "편의점": "convenience",
        "카페": "cafe",
        "대중교통": "transit",
        "주유": "fuel",
        "배달앱": "delivery_app",
        "온라인쇼핑": "online_shopping",
    }
    
    category_std = category_map.get(category, category.lower().replace(" ", "_"))
    
    # 혜택 타입 추정 (간단한 휴리스틱)
    benefit_type = "discount"  # 기본값
    if "%" in text or "할인" in text:
        benefit_type = "discount"
    elif "적립" in text or "포인트" in text:
        benefit_type = "cashback"
    elif "포인트" in text:
        benefit_type = "point"
    
    # 결제수단 추출 (간단한 휴리스틱)
    payment_methods = []
    payment_keywords = ["네이버페이", "카카오페이", "토스페이", "SSG페이", "11PAY", "스마일페이"]
    for keyword in payment_keywords:
        if keyword in text:
            payment_methods.append(keyword)
    
    meta = card_data.get("meta", {})
    metadata = {
        "card_id": meta.get("id"),
        "name": meta.get("name", ""),
        "issuer": meta.get("issuer", ""),
        "brand": ", ".join(card_data.get("hints", {}).get("brands", [])),
        "type": meta.get("type", ""),
        "prev_month_min": card_data.get("conditions", {}).get("prev_month_min", 0),
        "doc_type": "benefit",
        "category_std": category_std,
        "benefit_type": benefit_type,
        "payment_methods": payment_methods,
        "exclusions_present": any(b.get("category") == "유의사항" for b in card_data.get("benefits_html", [])),
        "is_discon": False
    }
    
    # 태그 추가
    tags = card_data.get("hints", {}).get("top_tags", [])
    if tags:
        metadata["tags"] = tags[:5]  # 최대 5개만
    
    return {"text": text, "metadata": metadata}


def create_notes_document(card_data: Dict) -> Optional[Dict]:
    """
    유의사항 문서 생성
    
    Args:
        card_data: 압축 컨텍스트 Dict
    
    Returns:
        {text: str, metadata: dict} 또는 None
    """
    benefits_html = card_data.get("benefits_html", [])
    
    # 유의사항 찾기
    notes_item = None
    for benefit in benefits_html:
        if benefit.get("category") == "유의사항":
            notes_item = benefit
            break
    
    if not notes_item:
        return None
    
    html = notes_item.get("html", "")
    if not html:
        return None
    
    text = clean_html(html)
    if not text:
        return None
    
    meta = card_data.get("meta", {})
    metadata = {
        "card_id": meta.get("id"),
        "name": meta.get("name", ""),
        "issuer": meta.get("issuer", ""),
        "brand": ", ".join(card_data.get("hints", {}).get("brands", [])),
        "type": meta.get("type", ""),
        "prev_month_min": card_data.get("conditions", {}).get("prev_month_min", 0),
        "doc_type": "notes",
        "exclusions_present": True,
        "is_discon": False
    }
    
    return {"text": text, "metadata": metadata}


def create_documents(card_data: Dict) -> List[Dict]:
    """
    카드 데이터를 문서 리스트로 변환
    
    Args:
        card_data: 압축 컨텍스트 Dict
    
    Returns:
        문서 리스트 [{text: str, metadata: dict}, ...]
    """
    documents = []
    
    # Summary 문서
    summary_doc = create_summary_document(card_data)
    if summary_doc:
        documents.append(summary_doc)
    
    # Benefit 문서들
    benefits_html = card_data.get("benefits_html", [])
    for benefit_item in benefits_html:
        if benefit_item.get("category") == "유의사항":
            continue  # 유의사항은 별도로 처리
        benefit_doc = create_benefit_document(card_data, benefit_item)
        if benefit_doc:
            documents.append(benefit_doc)
    
    # Notes 문서
    notes_doc = create_notes_document(card_data)
    if notes_doc:
        documents.append(notes_doc)
    
    return documents


class EmbeddingGenerator:
    """임베딩 생성 및 ChromaDB 저장 클래스"""
    
    def __init__(self, chroma_db_path: str = "chroma_db", collection_name: str = "credit_cards"):
        """
        Args:
            chroma_db_path: ChromaDB 저장 경로
            collection_name: 컬렉션 이름
        """
        self.chroma_db_path = Path(chroma_db_path)
        self.collection_name = collection_name
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # ChromaDB 클라이언트 초기화
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.chroma_db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # 컬렉션 가져오기 또는 생성
        try:
            self.collection = self.chroma_client.get_collection(name=collection_name)
            print(f"✅ 기존 컬렉션 로드: {collection_name}")
        except:
            self.collection = self.chroma_client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            print(f"✅ 새 컬렉션 생성: {collection_name}")
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        텍스트 리스트를 임베딩으로 변환
        
        Args:
            texts: 텍스트 리스트
        
        Returns:
            임베딩 벡터 리스트
        """
        if not texts:
            return []
        
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            print(f"❌ 임베딩 생성 실패: {e}")
            return []
    
    def add_card(self, card_data: Dict, overwrite: bool = False):
        """
        카드를 문서로 분해하고 ChromaDB에 추가
        
        Args:
            card_data: 압축 컨텍스트 Dict
            overwrite: 기존 문서 덮어쓰기 여부
        """
        card_id = card_data.get("meta", {}).get("id")
        if not card_id:
            print("⚠️  카드 ID가 없습니다")
            return
        
        # 기존 문서 확인
        if not overwrite:
            existing = self.collection.get(
                where={"card_id": card_id},
                limit=1
            )
            if existing["ids"]:
                print(f"⏭️  이미 존재하는 카드 (card_id={card_id}), 건너뜀")
                return
        
        # 문서 생성
        documents = create_documents(card_data)
        if not documents:
            print(f"⚠️  문서 생성 실패 (card_id={card_id})")
            return
        
        # 텍스트와 메타데이터 분리
        texts = [doc["text"] for doc in documents]
        metadatas = [doc["metadata"] for doc in documents]
        
        # 임베딩 생성
        embeddings = self.generate_embeddings(texts)
        if not embeddings:
            print(f"❌ 임베딩 생성 실패 (card_id={card_id})")
            return
        
        # ID 생성 (card_id + doc_type + index)
        ids = []
        for i, doc in enumerate(documents):
            doc_type = doc["metadata"].get("doc_type", "unknown")
            ids.append(f"{card_id}_{doc_type}_{i}")
        
        # ChromaDB에 추가
        try:
            # 기존 문서 삭제 (덮어쓰기)
            if overwrite:
                self.collection.delete(where={"card_id": card_id})
            
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )
            print(f"✅ 카드 추가 완료 (card_id={card_id}, 문서 {len(documents)}개)")
        except Exception as e:
            print(f"❌ ChromaDB 추가 실패 (card_id={card_id}): {e}")
    
    def add_cards_batch(self, card_data_list: List[Dict], overwrite: bool = False):
        """
        여러 카드를 배치로 추가
        
        Args:
            card_data_list: 압축 컨텍스트 Dict 리스트
            overwrite: 기존 문서 덮어쓰기 여부
        """
        for card_data in card_data_list:
            self.add_card(card_data, overwrite=overwrite)


# 사용 예시
def main():
    """테스트용 메인 함수"""
    from data_collection.data_parser import load_compressed_context
    
    # 임베딩 생성기 초기화
    generator = EmbeddingGenerator()
    
    # 카드 데이터 로드
    card_data = load_compressed_context(2862)
    if card_data:
        # 카드 추가
        generator.add_card(card_data, overwrite=True)
        print("✅ 완료")


if __name__ == "__main__":
    main()

