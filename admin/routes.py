from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from security.admin_auth import require_admin_auth

from .schemas import (
    AdminCardDetailModel,
    AdminCardListResponseModel,
    AdminVectorQueryRequest,
    AdminVectorStoreStatsResponse,
)


router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin_auth)])


@router.get("/cards/stats")
async def get_vector_db_stats():
    """MongoDB 벡터 DB 통계 확인"""
    try:
        from database.mongodb_client import MongoDBClient

        mongo_client = MongoDBClient()
        stats = mongo_client.get_stats()

        return {
            "database": stats.get("database"),
            "collection": stats.get("collection"),
            "total_documents": stats.get("total_documents", 0),
            "documents_with_embeddings": stats.get("documents_with_embeddings", 0),
            "indexes": stats.get("indexes", []),
            "search_indexes": stats.get("search_indexes", []),
            "vector_search_ready": stats.get("vector_search_ready", False),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"통계 조회 중 오류가 발생했습니다: {str(e)}")


@router.get("/mongodb/health")
async def mongodb_health_check():
    """MongoDB Atlas 연결 상태 및 인덱스 확인"""
    try:
        from database.mongodb_client import MongoDBClient

        mongo_client = MongoDBClient()
        is_connected = mongo_client.health_check()

        if not is_connected:
            return {"status": "disconnected", "message": "MongoDB 연결 실패"}

        stats = mongo_client.get_stats()
        return {
            "status": "connected",
            "database": stats.get("database"),
            "collection": stats.get("collection"),
            "total_documents": stats.get("total_documents", 0),
            "documents_with_embeddings": stats.get("documents_with_embeddings", 0),
            "indexes": stats.get("indexes", []),
            "search_indexes": stats.get("search_indexes", []),
            "vector_search_ready": stats.get("vector_search_ready", False),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def _fetch_cards_from_cardgorilla(card_client: Any, card_ids: List[int], overwrite: bool):
    """1단계: 카드고릴라에서 데이터 수집 및 JSON 생성"""
    results = {"success": [], "failed": [], "skipped": []}

    if not card_client:
        raise HTTPException(status_code=503, detail="카드 수집 서비스를 사용할 수 없습니다.")

    for idx, card_id in enumerate(card_ids, 1):
        try:
            if idx % 100 == 0:
                print(f"  진행: {idx}/{len(card_ids)} ({idx*100//len(card_ids)}%)")
            card_data = await card_client.fetch_card_detail(card_id, use_cache=not overwrite)
            if card_data:
                results["success"].append({"card_id": card_id, "name": card_data["meta"]["name"]})
            else:
                results["skipped"].append({"card_id": card_id, "reason": "카드를 찾을 수 없거나 단종됨"})
        except Exception as e:
            results["failed"].append({"card_id": card_id, "error": str(e)})
            continue

    return results


async def _embed_cards_to_mongodb(embedding_generator: Any, card_ids: Optional[List[int]], overwrite: bool):
    """2단계: JSON 파일을 읽어서 임베딩 생성 및 MongoDB 저장"""
    results = {"success": [], "failed": [], "skipped": []}

    if not embedding_generator:
        raise HTTPException(status_code=503, detail="임베딩 서비스를 사용할 수 없습니다.")

    # card_ids가 없으면 data/cache/ctx 폴더의 모든 JSON 파일 처리
    if not card_ids:
        from pathlib import Path
        import json

        ctx_dir = Path("data/cache/ctx")
        if not ctx_dir.exists():
            print("⚠️  data/cache/ctx 폴더가 없습니다. 먼저 1단계(fetch)를 실행하세요.")
            return results

        json_files = list(ctx_dir.glob("*.json"))
        card_ids = [int(f.stem) for f in json_files]
        print(f"📂 {len(card_ids)}개 JSON 파일 발견")

    for idx, card_id in enumerate(card_ids, 1):
        try:
            print(f"  [{idx}/{len(card_ids)}] 카드 ID {card_id} 임베딩 중...")
            from pathlib import Path
            import json

            json_file = Path("data/cache/ctx") / f"{card_id}.json"
            if not json_file.exists():
                results["skipped"].append({"card_id": card_id, "reason": "JSON 파일 없음"})
                continue

            with open(json_file, "r", encoding="utf-8") as f:
                card_data = json.load(f)

            embedding_generator.add_card(card_data, overwrite=overwrite)
            results["success"].append({"card_id": card_id, "name": card_data["meta"]["name"]})
            print(f"  ✅ 카드 ID {card_id} 완료")
        except Exception as e:
            error_msg = str(e)

            # OpenAI 크레딧/할당량 부족 감지
            if "insufficient_quota" in error_msg.lower() or "quota" in error_msg.lower():
                print("\n💰 OpenAI 크레딧 부족 감지!")
                print(f"   처리 완료: {len(results['success'])}개")
                print(f"   미처리: {len(card_ids) - idx}개")
                print(f"   다음 카드부터 재개: card_id={card_id}")
                results["failed"].append({"card_id": card_id, "error": "OpenAI 크레딧 부족으로 중단"})
                break

            # Rate Limit 감지
            if "rate_limit" in error_msg.lower():
                print("  ⏳ Rate Limit 도달, 60초 대기 후 재시도...")
                import asyncio

                await asyncio.sleep(60)
                try:
                    embedding_generator.add_card(card_data, overwrite=overwrite)
                    results["success"].append({"card_id": card_id, "name": card_data["meta"]["name"]})
                    print(f"  ✅ 카드 ID {card_id} 완료 (재시도 성공)")
                except Exception as retry_error:
                    results["failed"].append({"card_id": card_id, "error": f"재시도 실패: {str(retry_error)}"})
                    print(f"  ❌ 카드 ID {card_id} 재시도 실패: {retry_error}")
                continue

            results["failed"].append({"card_id": card_id, "error": error_msg})
            print(f"  ❌ 카드 ID {card_id} 실패: {e}")
            continue

    return results


@router.post("/cards/fetch")
async def fetch_cards_from_cardgorilla(
    request: Request,
    overwrite: bool = Query(False),
    start_id: int = Query(1),
    end_id: int = Query(5000),
    card_ids: Optional[List[int]] = Body(None),
):
    """
    1단계: 카드고릴라에서 데이터 수집 및 JSON 생성

    카드고릴라 API에서 카드 정보를 가져와 압축 컨텍스트 JSON 파일로 저장합니다.
    (data/cache/ctx/{card_id}.json)
    """
    try:
        # card_ids가 없으면 범위 생성
        if not card_ids:
            card_ids = list(range(start_id, end_id + 1))
            print(f"📋 카드 ID 범위: {start_id}~{end_id} ({len(card_ids)}개)")

        card_client = getattr(request.app.state, "card_client", None)
        results = await _fetch_cards_from_cardgorilla(card_client, card_ids, overwrite)
        return {
            "success": True,
            "message": f"1단계 완료: 성공 {len(results['success'])}개, 실패 {len(results['failed'])}개, 건너뜀 {len(results['skipped'])}개",
            "summary": {
                "total_tried": len(card_ids),
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "skipped_count": len(results["skipped"]),
            },
            "details": results,
            "next_step": "POST /admin/cards/embed 를 실행하여 임베딩을 생성하세요",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"카드 수집 중 오류가 발생했습니다: {str(e)}")


@router.post("/cards/embed")
async def embed_cards_to_chromadb(
    request: Request,
    overwrite: bool = Query(False),
    start_id: int = Query(None),
    end_id: int = Query(None),
    card_ids: Optional[List[int]] = Body(None),
):
    """
    2단계: JSON을 임베딩으로 변환하여 MongoDB에 저장

    data/cache/ctx 폴더의 JSON 파일들을 읽어서:
    - 문서로 분해
    - OpenAI Embeddings 생성
    - MongoDB에 저장
    """
    try:
        # card_ids 결정
        if not card_ids:
            if start_id is not None and end_id is not None:
                card_ids = list(range(start_id, end_id + 1))
                print(f"📋 카드 ID 범위: {start_id}~{end_id} ({len(card_ids)}개)")
            else:
                card_ids = None
                print("📂 모든 JSON 파일 처리")

        embedding_generator = getattr(request.app.state, "embedding_generator", None)
        results = await _embed_cards_to_mongodb(embedding_generator, card_ids, overwrite)
        return {
            "success": True,
            "message": f"2단계 완료: 성공 {len(results['success'])}개, 실패 {len(results['failed'])}개, 건너뜀 {len(results['skipped'])}개",
            "summary": {
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "skipped_count": len(results["skipped"]),
            },
            "details": results,
            "next_step": "GET /admin/cards/stats 로 벡터 DB 상태를 확인하세요",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"임베딩 생성 중 오류가 발생했습니다: {str(e)}")


@router.post("/cards/sync")
async def sync_cards_batch(
    request: Request,
    overwrite: bool = Query(False),
    start_id: int = Query(1),
    end_id: int = Query(5000),
    card_ids: Optional[List[int]] = Body(None),
):
    """통합: fetch + embed 한번에 실행"""
    try:
        if not card_ids:
            card_ids = list(range(start_id, end_id + 1))
            print(f"📋 카드 ID 범위: {start_id}~{end_id} ({len(card_ids)}개)")

        card_client = getattr(request.app.state, "card_client", None)
        embedding_generator = getattr(request.app.state, "embedding_generator", None)
        if not all([card_client, embedding_generator]):
            raise HTTPException(status_code=503, detail="동기화 서비스를 사용할 수 없습니다.")

        print("🔄 1/2 단계: 카드 데이터 수집")
        fetch_results = await _fetch_cards_from_cardgorilla(card_client, card_ids, overwrite)

        successful_ids = [item["card_id"] for item in fetch_results["success"]]
        if not successful_ids:
            return {
                "success": True,
                "message": "수집된 카드가 없어 임베딩 단계를 건너뜁니다.",
                "fetch_results": fetch_results,
                "embed_results": {"success": [], "failed": [], "skipped": []},
            }

        print(f"🔄 2/2 단계: 임베딩 생성 ({len(successful_ids)}개)")
        embed_results = await _embed_cards_to_mongodb(embedding_generator, successful_ids, overwrite)

        return {
            "success": True,
            "message": f"전체 완료: 수집 {len(fetch_results['success'])}개, 임베딩 {len(embed_results['success'])}개",
            "summary": {
                "total_tried": len(card_ids),
                "fetch_success": len(fetch_results["success"]),
                "embed_success": len(embed_results["success"]),
            },
            "fetch_results": fetch_results,
            "embed_results": embed_results,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"동기화 중 오류: {str(e)}")


@router.post("/cards/{card_id}")
async def sync_single_card(request: Request, card_id: int, overwrite: bool = False):
    """특정 카드 1개 fetch + embed"""
    try:
        card_client = getattr(request.app.state, "card_client", None)
        embedding_generator = getattr(request.app.state, "embedding_generator", None)

        fetch_results = await _fetch_cards_from_cardgorilla(card_client, [int(card_id)], overwrite)
        if not fetch_results["success"]:
            raise HTTPException(status_code=404, detail="카드를 찾을 수 없거나 단종된 카드")

        embed_results = await _embed_cards_to_mongodb(embedding_generator, [int(card_id)], overwrite)
        return {
            "success": True,
            "card_id": card_id,
            "card_name": fetch_results["success"][0]["name"],
            "fetch_result": fetch_results,
            "embed_result": embed_results,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"단일 카드 동기화 실패: {str(e)}")


@router.delete("/cards/reset")
async def reset_vector_db():
    """MongoDB 벡터 DB 초기화 (모든 임베딩 삭제)"""
    try:
        from database.mongodb_client import MongoDBClient

        mongo_client = MongoDBClient()
        collection = mongo_client.get_collection("cards")
        result = collection.update_many({}, {"$unset": {"embeddings": ""}, "$set": {"embeddings_count": 0}})
        return {
            "success": True,
            "message": f"벡터 DB 초기화 완료: {result.modified_count}개 문서 수정",
            "modified_documents": result.modified_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"초기화 실패: {str(e)}")


# ===== 벡터 스토어(임베딩) 조회용 관리자 API =====


@router.get("/vector-store/stats", response_model=AdminVectorStoreStatsResponse)
async def admin_vector_store_stats():
    """벡터 스토어(임베딩) 통계 조회 (MongoDB 기반)"""
    try:
        from database.mongodb_client import MongoDBClient

        mongo_client = MongoDBClient()
        collection = mongo_client.get_collection("cards")

        total_docs = collection.count_documents({})
        with_embeddings = collection.count_documents({"embeddings.0": {"$exists": True}})

        doc_type_counts: Dict[str, int] = {}
        try:
            pipeline = [
                {"$match": {"embeddings.0": {"$exists": True}}},
                {"$unwind": "$embeddings"},
                {"$group": {"_id": "$embeddings.doc_type", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
            for row in collection.aggregate(pipeline):
                key = row.get("_id") or "unknown"
                doc_type_counts[str(key)] = int(row.get("count", 0))
        except Exception as agg_error:
            print(f"[WARN] doc_type 집계 실패(무시): {agg_error}")

        return {
            "database": mongo_client.db_name,
            "collection": mongo_client.collection_name,
            "total_documents": total_docs,
            "documents_with_embeddings": with_embeddings,
            "doc_type_counts": doc_type_counts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"벡터 스토어 통계 조회 실패: {str(e)}")


@router.get("/vector-store/cards", response_model=AdminCardListResponseModel)
async def admin_vector_store_cards(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None, description="카드명/발급사/card_id 검색"),
    with_embeddings_only: bool = Query(True, description="임베딩 있는 카드만 반환"),
):
    """임베딩이 저장된 카드 목록 조회"""
    try:
        from database.mongodb_client import MongoDBClient

        mongo_client = MongoDBClient()
        collection = mongo_client.get_collection("cards")

        match: Dict[str, Any] = {}
        if with_embeddings_only:
            match["embeddings.0"] = {"$exists": True}

        if q:
            q_str = q.strip()
            or_conditions: List[Dict[str, Any]] = [
                {"meta.name": {"$regex": q_str, "$options": "i"}},
                {"meta.issuer": {"$regex": q_str, "$options": "i"}},
            ]
            if q_str.isdigit():
                try:
                    or_conditions.append({"card_id": int(q_str)})
                except Exception:
                    pass
            match["$or"] = or_conditions

        total = collection.count_documents(match)

        pipeline = [
            {"$match": match},
            {"$addFields": {"embeddings_count": {"$size": {"$ifNull": ["$embeddings", []]}}}},
            {
                "$project": {
                    "_id": 0,
                    "card_id": 1,
                    "meta": 1,
                    "conditions": 1,
                    "fees": 1,
                    "hints": 1,
                    "is_discon": 1,
                    "updated_at": 1,
                    "embeddings_count": 1,
                }
            },
            {"$sort": {"updated_at": -1, "card_id": 1}},
            {"$skip": int(skip)},
            {"$limit": int(limit)},
        ]

        items = list(collection.aggregate(pipeline))
        return {"total": total, "skip": skip, "limit": limit, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"카드 목록 조회 실패: {str(e)}")


@router.get("/vector-store/cards/{card_id}", response_model=AdminCardDetailModel)
async def admin_vector_store_card_detail(
    card_id: int,
    include_embedding: bool = Query(False, description="True면 embedding 벡터를 포함(매우 큼)"),
    text_limit: int = Query(600, ge=50, le=5000, description="청크 텍스트 미리보기 길이"),
):
    """특정 카드의 임베딩 청크 상세 조회"""
    try:
        from database.mongodb_client import MongoDBClient

        mongo_client = MongoDBClient()
        collection = mongo_client.get_collection("cards")

        doc = collection.find_one({"card_id": card_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail=f"카드를 찾을 수 없습니다. (card_id={card_id})")

        embeddings = doc.get("embeddings") or []
        sanitized = []
        for item in embeddings:
            if not isinstance(item, dict):
                continue
            out = dict(item)
            text = out.get("text")
            if isinstance(text, str) and len(text) > text_limit:
                out["text"] = text[:text_limit] + "…"
            if not include_embedding and "embedding" in out:
                out.pop("embedding", None)
            sanitized.append(out)

        doc["embeddings"] = sanitized
        doc["embeddings_count"] = len(sanitized)
        return doc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"카드 상세 조회 실패: {str(e)}")


@router.post("/vector-store/query")
async def admin_vector_store_query(request: Request, payload: AdminVectorQueryRequest):
    """벡터 검색 결과(청크)를 관리자용으로 조회"""
    try:
        vector_store = getattr(request.app.state, "vector_store", None)
        if not vector_store:
            raise HTTPException(status_code=503, detail="벡터 검색 서비스를 사용할 수 없습니다.")

        filters = payload.filters or {}
        filters = {k: v for k, v in filters.items() if v is not None}

        internal_top_k = min(200, max(payload.top_k, payload.top_k * 5))
        raw_results = vector_store.search_chunks(
            query_text=payload.query_text.strip(),
            filters=filters,
            top_k=internal_top_k,
        )

        allowed_doc_types = None
        if payload.doc_types:
            allowed_doc_types = {dt.strip() for dt in payload.doc_types if dt and dt.strip()}
            if not allowed_doc_types:
                allowed_doc_types = None

        default_weights: Dict[str, float] = {
            "summary": 1.15,
            "benefit_core": 1.0,
            "notes": 0.85,
        }
        weights = default_weights
        if payload.doc_type_weights:
            weights = {**default_weights, **{k: float(v) for k, v in payload.doc_type_weights.items()}}

        query_text = payload.query_text.strip()
        keywords: List[str] = []
        try:
            import re

            keywords = [
                t
                for t in re.findall(r"[0-9A-Za-z가-힣]{2,}", query_text)
                if t not in {"전월", "실적", "할인", "적립"}
            ]
        except Exception:
            keywords = []

        processed = []
        for r in raw_results:
            meta = r.get("metadata") or {}
            doc_type = str(meta.get("doc_type") or "")
            if allowed_doc_types is not None and doc_type not in allowed_doc_types:
                continue

            raw_score = r.get("score")
            if raw_score is None:
                dist = float(r.get("distance", 1.0))
                raw_score = 1.0 - dist
            raw_score = float(raw_score)

            w = float(weights.get(doc_type, 1.0))
            adjusted_score = raw_score * w

            text = r.get("text") or ""
            overlap = 0
            if keywords and isinstance(text, str) and text:
                lower = text.lower()
                overlap = sum(1 for k in keywords if k.lower() in lower)

            out = dict(r)
            if payload.explain:
                out["debug"] = {
                    "raw_score": raw_score,
                    "doc_type_weight": w,
                    "adjusted_score": adjusted_score,
                    "keyword_overlap": overlap,
                    "keywords": keywords[:10],
                }
            processed.append(out)

        def sort_key(item: Dict[str, Any]) -> float:
            dbg = item.get("debug") or {}
            return float(dbg.get("adjusted_score", item.get("score", 0.0) or 0.0))

        processed.sort(key=sort_key, reverse=True)
        results = processed[: payload.top_k]

        return {
            "query_text": payload.query_text,
            "filters": filters,
            "top_k": payload.top_k,
            "doc_types": list(allowed_doc_types) if allowed_doc_types is not None else None,
            "doc_type_weights": weights,
            "results": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"벡터 검색 실패: {str(e)}")

