"""
임베딩 생성 모듈

압축 컨텍스트(1.2 JSON)를 문서로 분해하고,
OpenAI Embeddings로 벡터화하여 MongoDB(`cards.embeddings`)에 저장합니다.
"""

import os
import re
import html as _html
from typing import Any, Dict, List, Optional, Tuple
from openai import OpenAI
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

    # 1) 구조 태그를 줄바꿈으로 치환 (혜택 1개=1 chunk 품질 개선)
    # - <li>, <br>, <p>, <tr> 등의 경계를 먼저 분리해두면 tag 제거 후에도 경계가 남습니다.
    s = html
    s = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*li\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*p\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*tr\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*div\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*ul\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*ol\s*>", "\n", s)

    # 2) HTML 태그 제거
    text = re.sub(r"<[^>]+>", "", s)

    # 3) HTML 엔티티 디코딩 (표준 라이브러리 사용)
    text = _html.unescape(text).replace("\xa0", " ")
    
    # 줄바꿈 정리 (여러 개의 줄바꿈을 하나로)
    text = re.sub(r'\n\s*\n', '\n', text)
    
    # 앞뒤 공백 제거
    text = text.strip()
    
    return text


def _split_text_for_embedding(
    text: str,
    max_chars: int = 600,
    merge_below_chars: int = 140,
    min_keep_chars: int = 70,
) -> List[str]:
    """
    너무 긴 텍스트를 임베딩용으로 적당히 분할합니다.
    목표: 1 chunk = 1 혜택/조건/규칙에 가깝게, 의미 희석 최소화.

    정책:
    - 정제 텍스트가 짧게 잘리면(기본 140자 미만) 가능한 인접 chunk에 병합
    - 30~70자 수준의 너무 짧은 chunk는 제거(기본 min_keep_chars=70)
    """
    if not text:
        return []

    # 우선 줄 단위로 정리
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text) if ln.strip()]
    if not lines:
        return []

    chunks: List[str] = []
    buf: List[str] = []
    buf_len = 0

    def flush():
        nonlocal buf, buf_len
        if not buf:
            return
        joined = " ".join(buf).strip()
        if joined:
            chunks.append(joined)
        buf = []
        buf_len = 0

    for ln in lines:
        # 단일 라인이 너무 길면, 공백 기준으로 강제 분할
        if len(ln) > max_chars:
            flush()
            start = 0
            while start < len(ln):
                end = min(start + max_chars, len(ln))
                if end < len(ln):
                    # 가능한 한 단어 경계에서 자르기
                    space = ln.rfind(" ", start, end)
                    if space > start + 50:
                        end = space
                part = ln[start:end].strip()
                if part:
                    chunks.append(part)
                start = end
            continue

        # 버퍼에 합쳐서 max_chars 넘기면 flush
        if buf_len + len(ln) + 1 > max_chars and buf:
            flush()

        buf.append(ln)
        buf_len += len(ln) + 1

    flush()

    # 너무 짧은 조각은 인접 chunk에 병합 (노이즈 감소)
    merged: List[str] = []
    pending_short: Optional[str] = None

    def try_merge(prev: str, cur: str) -> Optional[str]:
        if len(prev) + 1 + len(cur) <= max_chars:
            return (prev + " " + cur).strip()
        return None

    for ch in chunks:
        ch = ch.strip()
        if not ch:
            continue

        # 먼저 pending_short가 있으면 현재에 붙이기를 시도
        if pending_short:
            merged_next = try_merge(pending_short, ch)
            if merged_next is not None:
                ch = merged_next
                pending_short = None
            else:
                # pending_short를 어디에도 못 붙이면: 너무 짧으면 버리고, 아니면 그대로 유지
                if len(pending_short) >= min_keep_chars:
                    merged.append(pending_short)
                pending_short = None

        # 현재 chunk가 짧으면 우선 이전에 붙이거나, 다음에 붙이기 위해 보류
        if len(ch) < merge_below_chars:
            if merged:
                merged_prev = try_merge(merged[-1], ch)
                if merged_prev is not None:
                    merged[-1] = merged_prev
                    continue
            pending_short = ch
            continue

        merged.append(ch)

    # 끝에 남은 pending_short 처리
    if pending_short:
        if merged:
            merged_prev = try_merge(merged[-1], pending_short)
            if merged_prev is not None:
                merged[-1] = merged_prev
            elif len(pending_short) >= min_keep_chars:
                merged.append(pending_short)
        elif len(pending_short) >= min_keep_chars:
            merged.append(pending_short)

    # 최종 하한선 적용: 30~70자(기본 70 미만) 제거
    return [c for c in merged if len(c) >= min_keep_chars]


def _classify_benefit_line(line: str) -> str:
    """
    benefit 텍스트 라인을 core/condition/exclusion으로 분류합니다.
    - core: 벡터 검색 대상(혜택의 핵심)
    - condition: 결과 설명용(전월실적/한도/조건 등)
    - exclusion: 룰 기반 필터용(제외/미적용/불가 등). 벡터 검색 X
    """
    t = (line or "").strip()
    if not t:
        return "skip"

    # exclusion 우선(명시적 제외/미적용/불가)
    exclusion_kw = [
        "제외", "미적용", "적용 제외", "할인 제외", "적립 제외", "혜택 제외",
        "제공하지", "불가", "불가능", "대상 아님", "포함되지",
    ]
    if any(k in t for k in exclusion_kw):
        return "exclusion"

    # condition(전월실적/한도/조건/건당/기간/횟수 등)
    #
    # NOTE:
    # - 기존 구현은 "최대/이상/미만" 같은 범용 토큰만으로도 condition으로 보내 오분류가 잦았습니다.
    # - 오분류가 커지면 benefit_core가 빈약해져 벡터 검색 품질/후속 계산 품질이 함께 떨어질 수 있습니다.
    #
    # 최소 개선안: "숫자 패턴 + 단위 + (조건 키워드)" 조합으로 condition 판단을 좁힙니다.
    # - 예: "전월실적 30만원 이상", "월 통합한도 2만원", "건당 1천원, 월 10회"
    # - 반대로 "10% 할인", "2% 적립" 같은 핵심 혜택은 core로 남기기 쉬워집니다.
    units = ["원", "%", "회", "건", "월", "일", "연"]
    num_unit = bool(re.search(r"\d", t)) and any(u in t for u in units)

    # 조건/제약을 강하게 시사하는 키워드(범용 토큰 단독은 제외)
    condition_kw = [
        "전월", "실적",
        "한도", "통합",
        "건당", "횟수",
        "기간", "조건", "기준",
        "연간", "월 최대", "일 최대",
        "승인", "결제건", "등록", "이용 시",
    ]

    if num_unit and any(k in t for k in condition_kw):
        return "condition"

    return "core"


def _split_benefit_text_sections(text: str) -> Tuple[str, str, str]:
    """
    정제된 benefit 텍스트를 core/condition/exclusion으로 분리합니다.
    Returns: (core_text, condition_text, exclusion_text)
    """
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text) if ln.strip()]
    core_lines: List[str] = []
    cond_lines: List[str] = []
    excl_lines: List[str] = []

    for ln in lines:
        kind = _classify_benefit_line(ln)
        if kind == "skip":
            continue
        if kind == "exclusion":
            excl_lines.append(ln)
        elif kind == "condition":
            cond_lines.append(ln)
        else:
            core_lines.append(ln)

    return ("\n".join(core_lines).strip(), "\n".join(cond_lines).strip(), "\n".join(excl_lines).strip())


def _normalize_card_id(raw_id: Any) -> Optional[int]:
    """
    카드 고유키(card_id)를 일관되게 int로 고정합니다.
    - meta.id가 "2862" 같은 문자열로 들어와도 DB키는 int로 통일
    """
    if raw_id is None:
        return None
    if isinstance(raw_id, int):
        return raw_id
    if isinstance(raw_id, str):
        s = raw_id.strip()
        if s.isdigit():
            try:
                return int(s)
            except Exception:
                return None
    return None


def _extract_annual_fee_total(fees: Dict) -> Optional[int]:
    """
    fees에서 숫자 연회비를 추출합니다(가능한 경우).
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


def _standardize_category(category: str, category_map: Dict[str, str]) -> str:
    """
    카테고리 표준 slug 생성.
    - 매핑에 없는 한글 카테고리는 불안정한 표준화를 피하기 위해 빈값("")으로 둡니다.
    """
    if not isinstance(category, str) or not category.strip():
        return ""
    category = category.strip()
    mapped = category_map.get(category)
    if mapped:
        return mapped
    # 한글/비ASCII 포함 시, 무리한 slug 생성 대신 빈값(필터/랭킹 혼란 방지)
    if re.search(r"[^\x00-\x7F]", category):
        return ""
    return category.lower().replace(" ", "_")


def _classify_benefit_type(text: str) -> str:
    """
    혜택 타입 분류(간단 휴리스틱).
    - dead code 제거 및 우선순위 정리
    """
    if not isinstance(text, str):
        return "unknown"
    t = text

    # 우선순위: 마일 > 캐시백(명시) > 청구할인/할인 > 적립(포인트 포함) > 포인트(단독) > 기타
    if any(k in t for k in ["마일", "마일리지", "항공"]):
        return "miles"
    if any(k in t for k in ["캐시백"]):
        return "cashback"
    if any(k in t for k in ["청구할인", "할인"]) or "%" in t:
        return "discount"
    if any(k in t for k in ["적립"]):
        # 포인트 적립은 cashback/point로 갈 수 있지만, 최소한 discount와는 분리
        return "point"
    if any(k in t for k in ["포인트"]):
        return "point"
    return "unknown"


def _extract_payment_methods(text: str) -> List[str]:
    if not isinstance(text, str):
        return []
    payment_methods: List[str] = []
    payment_keywords = [
        "네이버페이", "카카오페이", "토스페이", "SSG페이", "11PAY", "스마일페이", "삼성페이", "애플페이"
    ]
    for keyword in payment_keywords:
        if keyword in text:
            payment_methods.append(keyword)
    return payment_methods


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
    annual_fee_total = _extract_annual_fee_total(fees)
    if annual_fee_detail:
        # 숫자 추출 시도
        if annual_fee_total is not None:
            parts.append(f"연회비 {annual_fee_total:,}원")
    
    # 주요 혜택 요약
    top_tags = hints.get("top_tags", [])
    if top_tags:
        parts.append(f"주요 혜택: {', '.join(top_tags[:3])}")

    # 대표 카테고리 2~3개 추가 (summary 임베딩 빈약함 완화)
    benefits_html = card_data.get("benefits_html", []) or []
    try:
        cat_counts: Dict[str, int] = {}
        for b in benefits_html:
            if not isinstance(b, dict):
                continue
            cat = b.get("category")
            if not isinstance(cat, str) or not cat or cat == "유의사항":
                continue
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        top_cats = [c for c, _n in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:3]]
        if top_cats:
            parts.append(f"혜택 카테고리: {', '.join(top_cats)}")
    except Exception:
        # summary는 best-effort
        pass
    
    # 유의사항 언급
    has_notes = any(isinstance(b, dict) and b.get("category") == "유의사항" for b in benefits_html)
    if has_notes:
        parts.append("유의사항: 통합할인한도 및 제외 항목 확인 필요")
    
    text = ". ".join(parts) + "."
    
    card_id = _normalize_card_id(meta.get("id"))
    metadata = {
        "card_id": card_id,
        "name": name,
        "issuer": issuer,
        "brand": brand if brand else "",
        "type": card_type,
        "prev_month_min": prev_month,
        "doc_type": "summary",
        "is_discon": False
    }
    
    # 연회비 숫자 추출 (선택적)
    if annual_fee_total is not None:
        metadata["annual_fee_total"] = annual_fee_total
    
    return {"text": text, "metadata": metadata}


def create_benefit_documents(card_data: Dict, benefit_item: Dict) -> Tuple[List[Dict], List[Dict]]:
    """
    혜택 문서 생성 (core/condition/exclusion 분리)
    
    Args:
        card_data: 압축 컨텍스트 Dict
        benefit_item: benefits_html의 항목
    
    Returns:
        (vector_docs, non_vector_docs)
        - vector_docs: benefit_core만 포함 (벡터 검색 대상)
        - non_vector_docs: benefit_condition/benefit_exclusion (벡터 검색 X)
    """
    category = benefit_item.get("category", "")
    html = benefit_item.get("html", "")
    
    if not category or not html:
        return ([], [])
    
    # HTML 정제
    text = clean_html(html)
    if not text:
        return ([], [])
    
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

    category_std = _standardize_category(category, category_map)

    # core/condition/exclusion 분리
    core_text, cond_text, excl_text = _split_benefit_text_sections(text)

    # 혜택 타입/결제수단 추정(휴리스틱) — core 기준
    benefit_type = _classify_benefit_type(core_text or text)
    payment_methods = _extract_payment_methods(core_text or text)
    
    meta = card_data.get("meta", {})
    prev_month_min = card_data.get("conditions", {}).get("prev_month_min", 0) or 0
    fees = card_data.get("fees", {}) or {}
    annual_fee_total = _extract_annual_fee_total(fees)
    card_id = _normalize_card_id(meta.get("id"))
    base_metadata = {
        "card_id": card_id,
        "name": meta.get("name", ""),
        "issuer": meta.get("issuer", ""),
        "brand": ", ".join(card_data.get("hints", {}).get("brands", [])),
        "type": meta.get("type", ""),
        "prev_month_min": prev_month_min,
        "benefit_category": category,
        "category_std": category_std,
        "benefit_type": benefit_type,
        "payment_methods": ", ".join(payment_methods) if payment_methods else "",
        "exclusions_present": any(b.get("category") == "유의사항" for b in card_data.get("benefits_html", [])),
        "requires_spend": bool(prev_month_min and prev_month_min > 0),
        "annual_fee_total": annual_fee_total,
        "is_discon": False
    }
    
    # 태그 추가 (리스트를 문자열로 변환)
    tags = card_data.get("hints", {}).get("top_tags", [])
    if tags:
        base_metadata["tags"] = ", ".join(tags[:5])  # 최대 5개

    vector_docs: List[Dict] = []
    non_vector_docs: List[Dict] = []

    # 1) benefit_core (벡터 검색 대상)
    if core_text:
        parts = _split_text_for_embedding(core_text, max_chars=600, merge_below_chars=140, min_keep_chars=70)
        for i, part in enumerate(parts):
            md = dict(base_metadata)
            md["doc_type"] = "benefit_core"
            md["chunk_part"] = i
            md["chunk_parts"] = len(parts)
            vector_docs.append({"text": part, "metadata": md})

    # 2) benefit_condition (결과 설명용, 벡터 X)
    if cond_text:
        parts = _split_text_for_embedding(cond_text, max_chars=600, merge_below_chars=140, min_keep_chars=70)
        for i, part in enumerate(parts):
            md = dict(base_metadata)
            md["doc_type"] = "benefit_condition"
            md["chunk_part"] = i
            md["chunk_parts"] = len(parts)
            non_vector_docs.append({"text": part, "metadata": md})

    # 3) benefit_exclusion (룰 기반 필터용, 벡터 X)
    if excl_text:
        parts = _split_text_for_embedding(excl_text, max_chars=600, merge_below_chars=140, min_keep_chars=70)
        for i, part in enumerate(parts):
            md = dict(base_metadata)
            md["doc_type"] = "benefit_exclusion"
            md["chunk_part"] = i
            md["chunk_parts"] = len(parts)
            non_vector_docs.append({"text": part, "metadata": md})

    return (vector_docs, non_vector_docs)


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
    fees = card_data.get("fees", {}) or {}
    card_id = _normalize_card_id(meta.get("id"))
    annual_fee_total = _extract_annual_fee_total(fees)
    metadata = {
        "card_id": card_id,
        "name": meta.get("name", ""),
        "issuer": meta.get("issuer", ""),
        "brand": ", ".join(card_data.get("hints", {}).get("brands", [])),
        "type": meta.get("type", ""),
        "prev_month_min": card_data.get("conditions", {}).get("prev_month_min", 0),
        "doc_type": "notes",
        "exclusions_present": True,
        "annual_fee_total": annual_fee_total,
        "is_discon": False
    }
    
    return {"text": text, "metadata": metadata}


def create_documents(card_data: Dict) -> Tuple[List[Dict], List[Dict]]:
    """
    카드 데이터를 문서 리스트로 변환
    
    Args:
        card_data: 압축 컨텍스트 Dict
    
    Returns:
        (vector_docs, non_vector_docs)
    """
    vector_docs: List[Dict] = []
    non_vector_docs: List[Dict] = []
    
    # Summary 문서
    summary_doc = create_summary_document(card_data)
    if summary_doc:
        vector_docs.append(summary_doc)
    
    # Benefit 문서들
    benefits_html = card_data.get("benefits_html", [])
    for benefit_item in benefits_html:
        if benefit_item.get("category") == "유의사항":
            continue  # 유의사항은 별도로 처리
        core_docs, extra_docs = create_benefit_documents(card_data, benefit_item)
        if core_docs:
            vector_docs.extend(core_docs)
        if extra_docs:
            non_vector_docs.extend(extra_docs)
    
    # Notes 문서
    notes_doc = create_notes_document(card_data)
    if notes_doc:
        vector_docs.append(notes_doc)

    return (vector_docs, non_vector_docs)


class EmbeddingGenerator:
    """임베딩 생성 및 저장 클래스 (MongoDB 전용)"""

    def __init__(self):
        """EmbeddingGenerator 초기화 (MongoDB 전용)"""
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # MongoDB 연결 (필수)
        from database.mongodb_client import MongoDBClient
        self.mongo_client = MongoDBClient()
        self.cards_collection = self.mongo_client.get_collection("cards")
        print("✅ EmbeddingGenerator: MongoDB 연결됨")
    
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
        
        # OpenAI API 입력 길이/레이트 제한을 고려해 배치 처리
        try:
            all_embeddings: List[List[float]] = []
            batch_size = 128  # 보수적 기본값
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                response = self.openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=batch
                )
                all_embeddings.extend([item.embedding for item in response.data])
            return all_embeddings
        except Exception as e:
            print(f"❌ 임베딩 생성 실패: {e}")
            return []
    
    def add_card(self, card_data: Dict, overwrite: bool = False):
        """
        카드를 문서로 분해하고 MongoDB에 임베딩 추가

        Args:
            card_data: 압축 컨텍스트 Dict
            overwrite: 기존 문서 덮어쓰기 여부
        """
        raw_card_id = card_data.get("meta", {}).get("id")
        card_id = _normalize_card_id(raw_card_id)
        if not card_id:
            print("⚠️  카드 ID가 없습니다")
            return

        # 기존 임베딩 확인
        if not overwrite:
            existing = self.cards_collection.find_one(
                # embeddings_count는 과거 데이터/부분 업데이트 등으로 누락될 수 있어
                # "실제 embeddings 배열 존재"를 기준으로 스킵합니다.
                {"card_id": card_id, "embeddings.0": {"$exists": True}},
                {"_id": 1}
            )
            if existing:
                print(f"⏭️  이미 임베딩 존재 (card_id={card_id}), 건너뜀")
                return

        # 문서 생성 (vector_docs + non_vector_docs)
        vector_docs, non_vector_docs = create_documents(card_data)
        if not vector_docs and not non_vector_docs:
            print(f"⚠️  문서 생성 실패 (card_id={card_id})")
            return

        # 텍스트와 메타데이터 분리 (벡터 대상만 임베딩 생성)
        texts = [doc["text"] for doc in vector_docs]

        # 임베딩 생성
        embeddings = self.generate_embeddings(texts)
        if not embeddings or len(embeddings) != len(vector_docs):
            print(f"❌ 임베딩 생성 실패 (card_id={card_id})")
            return

        # MongoDB에 저장
        try:
            from datetime import datetime as dt

            # ID 생성 및 임베딩 배열 구성
            embeddings_array = []
            for i, (doc, embedding) in enumerate(zip(vector_docs, embeddings)):
                doc_type = doc["metadata"].get("doc_type", "unknown")
                text_value = doc.get("text", "") or ""

                # embeddings_array.metadata에는 "표시/필터/랭킹에 필요한 핵심필드"를 충분히 담는다.
                # - create_*에서 생성한 metadata를 기본으로 유지 + 파생값만 덧붙임
                md = dict(doc.get("metadata") or {})
                md.update(
                    {
                        "card_id": card_id,  # 최상위 키와 일치 강제
                        "text_len": len(text_value) if isinstance(text_value, str) else 0,
                    }
                )

                embeddings_array.append({
                    "doc_id": f"{card_id}_{doc_type}_{i}",
                    "doc_type": doc_type,
                    "text": text_value,
                    "embedding": embedding,
                    "metadata": md
                })

            # non-vector 문서(설명/필터용) 저장 배열 구성
            non_vector_array = []
            for j, doc in enumerate(non_vector_docs):
                doc_type = (doc.get("metadata") or {}).get("doc_type", "unknown")
                text_value = doc.get("text", "") or ""
                md = dict(doc.get("metadata") or {})
                md.update(
                    {
                        "card_id": card_id,
                        "text_len": len(text_value) if isinstance(text_value, str) else 0,
                    }
                )
                non_vector_array.append(
                    {
                        "doc_id": f"{card_id}_{doc_type}_nv_{j}",
                        "doc_type": doc_type,
                        "text": text_value,
                        "metadata": md,
                    }
                )

            # MongoDB 업데이트 (카드 전체 context + embeddings)
            meta = dict(card_data.get("meta", {}) or {})
            # meta.id도 card_id와 일치시키면 운영에서 키 혼선이 줄어듭니다.
            meta["id"] = card_id

            self.cards_collection.update_one(
                {"card_id": card_id},  # 유일키는 card_id로 고정(권장: unique index)
                {
                    "$set": {
                        "card_id": card_id,
                        "meta": meta,
                        "conditions": card_data.get("conditions", {}),
                        "fees": card_data.get("fees", {}),
                        "hints": card_data.get("hints", {}),
                        "benefits_html": card_data.get("benefits_html", []),
                        "is_discon": False,
                        "embeddings": embeddings_array,
                        "embeddings_count": len(embeddings_array),
                        "non_vector_docs": non_vector_array,
                        "non_vector_docs_count": len(non_vector_array),
                        "updated_at": dt.utcnow()
                    }
                },
                upsert=True  # 문서가 없으면 생성
            )
            print(
                f"✅ 카드 데이터 및 임베딩 추가 완료 (card_id={card_id}, "
                f"vector_docs={len(vector_docs)}개, non_vector_docs={len(non_vector_docs)}개)"
            )
        except Exception as e:
            print(f"❌ MongoDB 임베딩 저장 실패 (card_id={card_id}): {e}")
            raise
    
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

