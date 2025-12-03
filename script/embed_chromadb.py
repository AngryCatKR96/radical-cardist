#!/usr/bin/env python3
"""
cardgorilla JSON 캐시를 읽어 ChromaDB에 임베딩을 추가하는 CLI 스크립트.

FastAPI 관리자 엔드포인트(`/admin/cards/embed`)와 동일한 로직을
API 서버 없이 커맨드라인에서 실행할 수 있도록 만들었습니다.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# script/ 경로에서 실행 시 루트 경로를 import 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vector_store.embeddings import EmbeddingGenerator

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


async def embed_cards(card_ids: Optional[List[int]], overwrite: bool) -> Dict[str, List[Dict]]:
    """
    JSON 파일을 읽어서 임베딩을 생성하고 ChromaDB에 저장합니다.
    """
    generator = EmbeddingGenerator()

    results: Dict[str, List[Dict]] = {
        "success": [],
        "failed": [],
        "skipped": [],
    }

    if not CTX_DIR.exists():
        print("⚠️  data/cache/ctx 폴더가 없습니다. 먼저 fetch 단계를 실행하세요.")
        return results

    if not card_ids:
        json_files = sorted(CTX_DIR.glob("*.json"))
        if not json_files:
            print("⚠️  처리할 JSON 파일이 없습니다.")
            return results
        card_ids = [int(f.stem) for f in json_files]
        print(f"📂 모든 JSON 처리: {len(card_ids)}개")
    else:
        print(f"📋 지정된 카드 처리: {len(card_ids)}개")

    print(f"🔨 임베딩 생성 시작 (overwrite={overwrite})")

    for idx, card_id in enumerate(card_ids, 1):
        try:
            print(f"  [{idx}/{len(card_ids)}] 카드 ID {card_id} 임베딩 중...")

            json_file = CTX_DIR / f"{card_id}.json"
            if not json_file.exists():
                results["skipped"].append({
                    "card_id": card_id,
                    "reason": "JSON 파일 없음",
                })
                print(f"    ⏭️  JSON 파일 없음, 건너뜀")
                continue

            with open(json_file, "r", encoding="utf-8") as f:
                card_data = json.load(f)

            generator.add_card(card_data, overwrite=overwrite)

            results["success"].append({
                "card_id": card_id,
                "name": card_data["meta"]["name"],
            })
            print(f"    ✅ 완료")

        except Exception as e:  # pylint: disable=broad-except
            error_msg = str(e)
            lower_msg = error_msg.lower()

            if "insufficient_quota" in lower_msg or "quota" in lower_msg:
                print("\n💰 OpenAI 크레딧 부족 감지! 작업을 중단합니다.")
                results["failed"].append({
                    "card_id": card_id,
                    "error": "OpenAI 크레딧 부족",
                })
                break

            if "rate_limit" in lower_msg:
                print("  ⏳ Rate Limit 도달, 60초 대기 후 재시도...")
                await asyncio.sleep(60)
                try:
                    generator.add_card(card_data, overwrite=overwrite)
                    results["success"].append({
                        "card_id": card_id,
                        "name": card_data["meta"]["name"],
                    })
                    print(f"    ✅ 완료 (재시도 성공)")
                    continue
                except Exception as retry_error:  # pylint: disable=broad-except
                    results["failed"].append({
                        "card_id": card_id,
                        "error": f"재시도 실패: {retry_error}",
                    })
                    print(f"    ❌ 재시도 실패: {retry_error}")
                    continue

            results["failed"].append({
                "card_id": card_id,
                "error": error_msg,
            })
            print(f"    ❌ 실패: {error_msg}")

    print(
        f"\n✅ 임베딩 실행 결과 - 성공 {len(results['success'])}개, "
        f"실패 {len(results['failed'])}개, 건너뜀 {len(results['skipped'])}개"
    )
    return results


def main():
    parser = argparse.ArgumentParser(
        description="카드 JSON을 임베딩으로 변환해 ChromaDB에 저장하는 CLI",
    )
    parser.add_argument(
        "--start",
        type=int,
        help="범위 시작 카드 ID (지정 시 end와 함께 사용)",
    )
    parser.add_argument(
        "--end",
        type=int,
        help="범위 종료 카드 ID",
    )
    parser.add_argument(
        "--card-ids",
        type=str,
        help="쉼표로 구분한 카드 ID 목록 (지정 시 start/end 무시)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="기존 임베딩이 있어도 다시 생성",
    )

    args = parser.parse_args()

    try:
        card_ids = parse_card_ids(args.card_ids, args.start, args.end)
    except ValueError as exc:
        parser.error(str(exc))
        return

    asyncio.run(embed_cards(card_ids, overwrite=args.overwrite))


if __name__ == "__main__":
    main()


