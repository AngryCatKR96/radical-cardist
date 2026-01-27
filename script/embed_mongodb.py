#!/usr/bin/env python3
"""
cardgorilla JSON 캐시를 읽어 MongoDB(`cards` 컬렉션)에 임베딩을 추가하는 CLI 스크립트.

FastAPI 관리자 엔드포인트(`/admin/cards/embed`)와 동일한 로직을
API 서버 없이 커맨드라인에서 실행할 수 있도록 만들었습니다.

개선사항
- (1) 카드별 순차 처리 → 제한된 동시성(concurrency) 처리
- (2) MongoDB 모드에서 전체 문서 list 로드 제거 → distinct/projection 기반으로 card_id만 조회
- (3) rate_limit / quota 등 재시도/중단 특수 로직 제거 → 예외는 실패로만 기록하고 계속 진행(더 단순)
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# script/ 경로에서 실행 시 루트 경로를 import 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vector_store.embeddings import EmbeddingGenerator  # noqa: E402

CTX_DIR = PROJECT_ROOT / "data/cache/ctx"


def parse_card_ids(raw_ids: Optional[str], start: Optional[int], end: Optional[int]) -> Optional[List[int]]:
    """
    CLI 인자를 토대로 카드 ID 리스트를 생성합니다.
    """
    if raw_ids:
        ids = [int(cid.strip()) for cid in raw_ids.split(",") if cid.strip()]
        if not ids:
            raise ValueError("card_ids 인자에서 유효한 숫자를 찾을 수 없습니다.")
        return sorted(set(ids))

    if start is not None and end is not None:
        if end < start:
            raise ValueError("end 값은 start 이상이어야 합니다.")
        return list(range(start, end + 1))

    return None  # None이면 ctx 폴더 전체 처리


def _safe_get_name(card_data: Optional[Dict]) -> str:
    if not isinstance(card_data, dict):
        return ""
    meta = card_data.get("meta")
    if not isinstance(meta, dict):
        return ""
    name = meta.get("name")
    return name if isinstance(name, str) else ""


def _ensure_meta_id(card_data: Optional[Dict], card_id: int) -> None:
    """
    EmbeddingGenerator는 meta.id를 card_id로 사용하므로 보정합니다.
    """
    if not isinstance(card_data, dict):
        return
    meta = card_data.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        card_data["meta"] = meta
    if meta.get("id") is None:
        meta["id"] = int(card_id)


def _list_json_card_ids(ctx_dir: Path) -> Tuple[List[int], List[int]]:
    """
    ctx_dir 내 *.json 파일에서 card_id를 수집합니다.
    - 숫자 stem만 card_ids로 반환
    - 숫자 변환 실패 stem은 invalid 목록으로 반환
    """
    json_files = sorted(ctx_dir.glob("*.json"))
    card_ids: List[int] = []
    invalid: List[int] = []

    for f in json_files:
        try:
            card_ids.append(int(f.stem))
        except ValueError:
            # 파일명이 숫자가 아닌 경우 무시(필요하면 로그)
            invalid.append(0)

    return sorted(set(card_ids)), invalid


def _fetch_mongo_card_ids(generator: "EmbeddingGenerator") -> List[int]:
    """
    MongoDB에서 임베딩 대상 card_id만 가볍게 가져옵니다.
    - 가능하면 distinct 사용
    - 실패 시 projection cursor 방식으로 폴백
    """
    filter_q = {"is_discon": {"$ne": True}}

    try:
        ids = generator.cards_collection.distinct("card_id", filter_q)
        # distinct 결과에는 None/문자 등이 섞일 수 있어 정제
        out = sorted({int(x) for x in ids if isinstance(x, int)})
        return out
    except Exception:
        # 폴백: find projection으로 스트리밍
        out_set = set()
        cursor = generator.cards_collection.find(filter_q, {"_id": 0, "card_id": 1})
        for d in cursor:
            if isinstance(d, dict) and isinstance(d.get("card_id"), int):
                out_set.add(int(d["card_id"]))
        return sorted(out_set)


async def embed_cards(
    card_ids: Optional[List[int]],
    overwrite: bool,
    concurrency: int,
) -> Dict[str, List[Dict]]:
    """
    JSON 파일을 읽어서 임베딩을 생성하고 MongoDB에 저장합니다.
    (동시성 처리)
    """
    generator = EmbeddingGenerator()

    results: Dict[str, List[Dict]] = {
        "success": [],
        "failed": [],
        "skipped": [],
    }

    # 1) 로컬 JSON 캐시가 있으면 그걸 사용
    # 2) 없으면 MongoDB에 저장된 압축 컨텍스트를 읽어서 임베딩을 생성
    use_json_cache = CTX_DIR.exists()
    if use_json_cache:
        print(f"📂 JSON 캐시 모드: {CTX_DIR}")
    else:
        print("📦 MongoDB 모드: JSON 캐시 없이 cards 컬렉션에서 읽어 임베딩 생성")

    # 대상 card_ids 결정
    if not card_ids:
        if use_json_cache:
            json_files = sorted(CTX_DIR.glob("*.json"))
            if not json_files:
                print("⚠️  처리할 JSON 파일이 없습니다.")
                return results

            all_ids, _invalid = _list_json_card_ids(CTX_DIR)
            if not all_ids:
                print("⚠️  ctx 폴더에 숫자 파일명이 없습니다.")
                return results

            card_ids = all_ids
            print(f"📂 모든 JSON 처리: {len(card_ids)}개")
        else:
            card_ids = _fetch_mongo_card_ids(generator)
            if not card_ids:
                print("⚠️  MongoDB에 임베딩 대상 카드가 없습니다. 먼저 스크래핑(fetch)을 실행하세요.")
                return results
            print(f"🗄️  MongoDB 카드 처리: {len(card_ids)}개")
    else:
        print(f"📋 지정된 카드 처리: {len(card_ids)}개")

    print(f"🔨 임베딩 생성 시작 (overwrite={overwrite}, concurrency={concurrency})")

    sem = asyncio.Semaphore(max(1, int(concurrency)))

    async def _process_one(idx: int, total: int, cid: int) -> None:
        async with sem:
            try:
                print(f"  [{idx}/{total}] 카드 ID {cid} 임베딩 중...")

                card_data: Optional[Dict] = None

                if use_json_cache:
                    json_file = CTX_DIR / f"{cid}.json"
                    if not json_file.exists():
                        results["skipped"].append({"card_id": cid, "reason": "JSON 파일 없음"})
                        print("    ⏭️  JSON 파일 없음, 건너뜀")
                        return

                    with open(json_file, "r", encoding="utf-8") as f:
                        card_data = json.load(f)
                else:
                    doc = generator.cards_collection.find_one(
                        {"card_id": int(cid)},
                        {"_id": 0, "embeddings": 0},
                    )
                    if not doc:
                        results["skipped"].append({"card_id": cid, "reason": "MongoDB 문서 없음"})
                        print("    ⏭️  MongoDB 문서 없음, 건너뜀")
                        return
                    card_data = doc

                _ensure_meta_id(card_data, cid)

                # 동기 함수일 가능성이 높아서 스레드로 넘겨 이벤트 루프 블로킹 최소화
                await asyncio.to_thread(generator.add_card, card_data, overwrite)

                results["success"].append({"card_id": int(cid), "name": _safe_get_name(card_data)})
                print("    ✅ 완료")

            except Exception as e:  # pylint: disable=broad-except
                results["failed"].append({"card_id": int(cid), "error": str(e)})
                print(f"    ❌ 실패: {e}")

    total = len(card_ids)
    tasks = [asyncio.create_task(_process_one(i, total, cid)) for i, cid in enumerate(card_ids, 1)]
    await asyncio.gather(*tasks)

    print(
        f"\n✅ 임베딩 실행 결과 - 성공 {len(results['success'])}개, "
        f"실패 {len(results['failed'])}개, 건너뜀 {len(results['skipped'])}개"
    )
    return results


def main():
    parser = argparse.ArgumentParser(
        description="카드 JSON을 임베딩으로 변환해 MongoDB에 저장하는 CLI",
    )
    parser.add_argument("--start", type=int, help="범위 시작 카드 ID (지정 시 end와 함께 사용)")
    parser.add_argument("--end", type=int, help="범위 종료 카드 ID")
    parser.add_argument("--card-ids", type=str, help="쉼표로 구분한 카드 ID 목록 (지정 시 start/end 무시)")
    parser.add_argument("--overwrite", action="store_true", help="기존 임베딩이 있어도 다시 생성")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="동시 처리 개수 (기본 4, OpenAI/DB 상황에 맞게 조절)",
    )

    args = parser.parse_args()

    try:
        card_ids = parse_card_ids(args.card_ids, args.start, args.end)
    except ValueError as exc:
        parser.error(str(exc))
        return

    asyncio.run(embed_cards(card_ids, overwrite=args.overwrite, concurrency=args.concurrency))


if __name__ == "__main__":
    main()
