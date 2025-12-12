"""
데이터 파서

카드고릴라 API 원본 데이터를 압축 컨텍스트 형식으로 변환합니다.
이 모듈은 card_gorilla_client.py에서 이미 구현되어 있지만,
별도로 사용할 수 있도록 독립적인 함수로도 제공합니다.
"""

import json
from pathlib import Path
from typing import Dict, Optional


def parse_card_data(raw_data: Dict) -> Optional[Dict]:
    """
    원본 API 응답을 압축 컨텍스트 형식으로 변환
    
    Args:
        raw_data: 카드고릴라 API 원본 응답
    
    Returns:
        압축 컨텍스트 Dict 또는 None (단종 카드 등)
    
    예시:
        >>> raw = {"idx": 2862, "name": "MG+ S 하나카드", ...}
        >>> compressed = parse_card_data(raw)
        >>> print(compressed["meta"]["name"])
        MG+ S 하나카드
    """
    # 단종 카드 제외
    if raw_data.get("is_discon", False):
        return None
    
    # 화이트리스트 필드만 추출
    corp = raw_data.get("corp", {})
    
    compressed = {
        "meta": {
            "id": raw_data.get("idx"),
            "corpCode": raw_data.get("cid"),
            "name": raw_data.get("name", ""),
            "issuer": corp.get("name", ""),
            "type": raw_data.get("c_type", "")
        },
        "conditions": {
            "prev_month_min": raw_data.get("pre_month_money", 0)
        },
        "fees": {
            "annual_basic": raw_data.get("annual_fee_basic", ""),
            "annual_detail": raw_data.get("annual_fee_detail", "")
        },
        "hints": {
            "top_tags": [],
            "top_titles": [],
            "search_titles": [],
            "search_options": [],
            "brands": []
        },
        "benefits_html": []
    }
    
    # top_benefit 처리
    top_benefits = raw_data.get("top_benefit", [])
    for benefit in top_benefits:
        if benefit.get("tags"):
            compressed["hints"]["top_tags"].extend(benefit["tags"])
        if benefit.get("title"):
            compressed["hints"]["top_titles"].append(benefit["title"])
    
    # search_benefit 처리
    search_benefits = raw_data.get("search_benefit", [])
    for benefit in search_benefits:
        if benefit.get("title"):
            compressed["hints"]["search_titles"].append(benefit["title"])
        if benefit.get("options"):
            for option in benefit["options"]:
                if option.get("label"):
                    compressed["hints"]["search_options"].append(option["label"])
    
    # brand 처리
    brands = raw_data.get("brand", [])
    for brand in brands:
        if brand.get("name"):
            compressed["hints"]["brands"].append(brand["name"])
    
    # key_benefit 처리
    key_benefits = raw_data.get("key_benefit", [])
    for benefit in key_benefits:
        cate = benefit.get("cate", {})
        category_name = cate.get("name", "")
        info_html = benefit.get("info", "")
        
        if category_name and info_html:
            compressed["benefits_html"].append({
                "category": category_name,
                "html": info_html
            })
    
    return compressed


def load_compressed_context(card_id: int, cache_dir: str = "data/cache/ctx") -> Optional[Dict]:
    """
    MongoDB에서 압축 컨텍스트 로드 (MongoDB 전용)

    Args:
        card_id: 카드 ID
        cache_dir: (사용 안 함, 하위 호환성을 위해 유지)

    Returns:
        압축 컨텍스트 Dict 또는 None
    """
    try:
        from database.mongodb_client import MongoDBClient

        mongo_client = MongoDBClient()
        collection = mongo_client.get_collection("cards")

        # MongoDB에서 카드 조회 (embeddings 제외)
        card_doc = collection.find_one(
            {"card_id": card_id},
            {
                "_id": 0,
                "meta": 1,
                "conditions": 1,
                "fees": 1,
                "hints": 1,
                "benefits_html": 1
            }
        )

        if card_doc:
            # 필요한 필드만 추출
            compressed_context = {
                "meta": card_doc.get("meta", {}),
                "conditions": card_doc.get("conditions", {}),
                "fees": card_doc.get("fees", {}),
                "hints": card_doc.get("hints", {}),
                "benefits_html": card_doc.get("benefits_html", [])
            }
            return compressed_context
        else:
            print(f"⚠️  MongoDB에서 카드를 찾을 수 없음 (card_id={card_id})")
            return None

    except Exception as e:
        print(f"⚠️  MongoDB 로드 실패 (card_id={card_id}): {e}")
        return None


def save_compressed_context(card_id: int, compressed_data: Dict, cache_dir: str = "data/cache/ctx"):
    """
    압축 컨텍스트 저장
    
    Args:
        card_id: 카드 ID
        compressed_data: 압축 컨텍스트 Dict
        cache_dir: 캐시 디렉터리
    """
    cache_dir_path = Path(cache_dir)
    cache_dir_path.mkdir(parents=True, exist_ok=True)
    
    cache_file = cache_dir_path / f"{card_id}.json"
    
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(compressed_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 컨텍스트 저장 완료 (card_id={card_id})")
    except Exception as e:
        print(f"❌ 컨텍스트 저장 실패 (card_id={card_id}): {e}")

