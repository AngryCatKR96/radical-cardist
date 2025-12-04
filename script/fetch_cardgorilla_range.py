#!/usr/bin/env python3
"""
카드고릴라 API에서 카드 데이터를 수집해 `data/cache/ctx/{card_id}.json`으로 저장하는 스크립트.

FastAPI 관리자 엔드포인트(`/admin/cards/fetch`)와 동일한 로직을 CLI로 실행하고 싶을 때 사용합니다.
기본 범위는 1~3000이며, 원하는 범위나 카드 ID 목록을 인자로 지정할 수 있습니다.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# script/ 경로에서 실행 시 루트 경로를 import 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_collection.card_gorilla_client import CardGorillaClient

SKIPLIST_FILE = PROJECT_ROOT / "script/skipped_cards.json"
SKIP_REASONS = {"discontinued", "not_found"}


def load_skip_entries() -> Dict[int, Dict[str, str]]:
    """단종/미존재 카드 목록을 로드"""
    if not SKIPLIST_FILE.exists():
        return {}
    try:
        with open(SKIPLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", data)
        return {int(card_id): info for card_id, info in entries.items()}
    except Exception as exc:
        print(f"⚠️  skip 파일 로드 실패: {exc}")
        return {}


def save_skip_entries(entries: Dict[int, Dict[str, str]]) -> None:
    """단종/미존재 카드 목록을 저장"""
    SKIPLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        "entries": {str(card_id): info for card_id, info in entries.items()},
    }
    with open(SKIPLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"📝 단종/미존재 카드 {len(entries)}개 기록 저장: {SKIPLIST_FILE}")


async def fetch_cards(
    card_ids: Iterable[int],
    overwrite: bool,
) -> Dict[int, Dict[str, str]]:
    """
    카드 ID 리스트를 순회하며 카드고릴라 데이터를 수집합니다.

    Args:
        card_ids: 조회할 카드 ID 이터러블
        overwrite: 기존 JSON 캐시 덮어쓰기 여부
    """
    client = CardGorillaClient()
    card_ids = list(card_ids)
    new_skip_entries: Dict[int, Dict[str, str]] = {}

    success, failed, skipped = 0, 0, 0
    print(f"📥 카드 데이터 수집 시작: {card_ids[0]}~{card_ids[-1]} (총 {len(card_ids)}개)")

    for idx, card_id in enumerate(card_ids, 1):
        try:
            if idx % 100 == 0:
                progress = int(idx * 100 / len(card_ids))
                print(f"  진행률 {idx}/{len(card_ids)} ({progress}%)")

            card_data, reason = await client.fetch_card_detail(
                card_id,
                use_cache=not overwrite,
                return_reason=True,
            )

            if card_data:
                success += 1
            elif reason in SKIP_REASONS:
                skipped += 1
                new_skip_entries[card_id] = {
                    "reason": reason,
                    "first_detected": datetime.now(UTC).isoformat(),
                }
            else:
                failed += 1
        except Exception as exc:  # 안전망
            failed += 1
            print(f"  ❌ card_id={card_id} 오류: {exc}")

    print(
        f"✅ 수집 완료: 성공 {success}개, 실패 {failed}개, 건너뜀 {skipped}개 "
        f"(총 {len(card_ids)}개)"
    )
    if new_skip_entries:
        print(f"  ↳ 새로운 단종/미존재 카드 {len(new_skip_entries)}개 기록 예정")

    return new_skip_entries


def parse_card_ids(raw_ids: Optional[str], start: int, end: int) -> List[int]:
    """
    CLI 인자를 토대로 카드 ID 리스트를 생성합니다.
    """
    if raw_ids:
        ids = [int(cid.strip()) for cid in raw_ids.split(",") if cid.strip()]
        if not ids:
            raise ValueError("card_ids 인자에서 유효한 숫자를 찾을 수 없습니다.")
        return sorted(set(ids))

    if end < start:
        raise ValueError("end 값은 start 이상이어야 합니다.")

    return list(range(start, end + 1))


def main():
    parser = argparse.ArgumentParser(
        description="카드고릴라 카드 데이터를 JSON 캐시로 수집하는 CLI"
    )
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="범위 시작 카드 ID (기본값: 1)",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=4000,
        help="범위 종료 카드 ID (기본값: 4000)",
    )
    parser.add_argument(
        "--card-ids",
        type=str,
        help="쉼표로 구분한 카드 ID 목록 (지정 시 start/end 무시)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="기존 JSON 캐시가 있어도 새로 받아 저장",
    )

    args = parser.parse_args()
    card_ids = parse_card_ids(args.card_ids, args.start, args.end)

    skip_entries = load_skip_entries()
    if skip_entries:
        before = len(card_ids)
        card_ids = [card_id for card_id in card_ids if card_id not in skip_entries]
        skipped_known = before - len(card_ids)
        if skipped_known > 0:
            print(f"⏭️  이미 단종/미존재로 기록된 카드 {skipped_known}개 건너뜀")

    if not card_ids:
        print("처리할 카드가 없습니다. skip 파일을 확인하세요.")
        return

    new_skip_entries = asyncio.run(fetch_cards(card_ids, overwrite=args.overwrite))

    if new_skip_entries:
        skip_entries.update(new_skip_entries)
        save_skip_entries(skip_entries)


if __name__ == "__main__":
    main()

