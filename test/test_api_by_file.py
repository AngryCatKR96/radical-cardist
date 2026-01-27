#!/usr/bin/env python3
"""
자연어 추천 회귀 테스트 러너 (test 폴더용)

목적:
- 임베딩/청킹/랭킹 로직을 바꿀 때마다, 동일한 자연어 입력들에 대해
  추천 결과가 어떻게 달라졌는지 빠르게 확인하기 위한 스크립트입니다.
- 테스트 결과를 Markdown(`test/files/ret.md`)로 저장합니다.

전제:
- 백엔드 서버가 실행 중이어야 합니다. (기본: http://localhost:8000)
- 카드/임베딩 데이터가 준비되어 있어야 합니다.

사용 예:
  python test/files/test_api_by_file.py
  python test/files/test_api_by_file.py --base-url http://localhost:8000
  python test/files/test_api_by_file.py --inputs-file test/files/test_inputs_nl.txt --out test/files/ret.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


DEFAULT_TEST_INPUTS: List[str] = [
    "마트 30만원, 간편결제 자주 씀. OTT(넷플릭스/유튜브) 구독 중. 연회비 2만원 이하.",
    "온라인쇼핑 월 50만원 정도. 배달도 종종 써요. 연회비는 낮으면 좋겠어요.",
    "카페 주 3~4회, 편의점 자주 이용. 대중교통도 써요. 월 20만원 내외.",
]


def _read_inputs_file(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.read().splitlines()]
    # 빈 줄/주석 제거
    inputs = [ln for ln in lines if ln and not ln.startswith("#")]
    return inputs


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def _extract_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    card = payload.get("card") if isinstance(payload.get("card"), dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    return {
        "card_id": card.get("id"),
        "card_name": card.get("name"),
        "brand": card.get("brand"),
        "annual_fee": card.get("annual_fee"),
        "required_spend": card.get("required_spend"),
        "monthly_savings": card.get("monthly_savings"),
        "annual_savings": card.get("annual_savings"),
        "net_benefit": analysis.get("net_benefit"),
        "warnings": analysis.get("warnings"),
    }


def main() -> int:
    here = Path(__file__).resolve().parent

    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.getenv("BASE_URL", "http://localhost:8000"))
    ap.add_argument("--out", default=str(here / "files/ret.md"))
    ap.add_argument("--inputs-file", default=str(here / "files/test_inputs_nl.txt"))
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--sleep", type=float, default=0.5, help="케이스 간 딜레이(초)")
    args = ap.parse_args()

    inputs = DEFAULT_TEST_INPUTS
    if args.inputs_file and Path(args.inputs_file).exists():
        inputs = _read_inputs_file(args.inputs_file)

    if not inputs:
        print("[FAIL] 테스트 입력이 비어있습니다.", file=sys.stderr)
        return 2

    started_at = dt.datetime.now(dt.timezone.utc)
    out_lines: List[str] = []

    out_lines.append("# 자연어 추천 회귀 테스트 결과")
    out_lines.append("")
    out_lines.append(f"- 실행 시각(UTC): `{started_at.isoformat()}`")
    out_lines.append(f"- BASE_URL: `{args.base_url}`")
    out_lines.append(f"- 케이스 수: **{len(inputs)}**")
    out_lines.append("")
    out_lines.append("> 참고: 결과의 원본 JSON도 함께 포함됩니다. (diff 보기 용도)")
    out_lines.append("")

    ok_count = 0
    for idx, user_input in enumerate(inputs, 1):
        out_lines.append(f"## Case {idx}")
        out_lines.append("")
        out_lines.append("### Input")
        out_lines.append("")
        out_lines.append("```")
        out_lines.append(user_input)
        out_lines.append("```")
        out_lines.append("")

        url = f"{args.base_url}/recommend/natural-language"
        t0 = time.time()
        try:
            res = requests.post(
                url,
                json={"user_input": user_input},
                headers={"Content-Type": "application/json"},
                timeout=args.timeout,
            )
            elapsed_ms = int((time.time() - t0) * 1000)

            out_lines.append("### Result")
            out_lines.append("")
            out_lines.append(f"- HTTP: **{res.status_code}**")
            out_lines.append(f"- Elapsed: **{elapsed_ms}ms**")

            payload: Optional[Dict[str, Any]] = None
            try:
                payload = res.json()
            except Exception:
                payload = None

            if res.ok and isinstance(payload, dict):
                ok_count += 1
                summary = _extract_summary(payload)
                out_lines.append(f"- Summary: `{_safe_json(summary)}`")
            else:
                detail = None
                if isinstance(payload, dict):
                    detail = payload.get("detail") or payload.get("error")
                out_lines.append(f"- Error: `{detail or (res.text[:400] if res.text else 'unknown')}`")

            out_lines.append("")
            out_lines.append("### Raw JSON")
            out_lines.append("")
            out_lines.append("```json")
            if payload is None:
                out_lines.append(_safe_json({"raw": res.text}))
            else:
                out_lines.append(_safe_json(payload))
            out_lines.append("```")
            out_lines.append("")

        except requests.exceptions.ConnectionError:
            out_lines.append("### Result")
            out_lines.append("")
            out_lines.append("- HTTP: **(connection error)**")
            out_lines.append(
                "- Error: `서버에 연결할 수 없습니다. python main.py로 백엔드를 먼저 실행하세요.`"
            )
            out_lines.append("")
            break
        except Exception as e:
            out_lines.append("### Result")
            out_lines.append("")
            out_lines.append(f"- HTTP: **(exception)**")
            out_lines.append(f"- Error: `{type(e).__name__}: {e}`")
            out_lines.append("")

        if idx < len(inputs) and args.sleep > 0:
            time.sleep(args.sleep)

    finished_at = dt.datetime.now(dt.timezone.utc)
    out_lines.append("---")
    out_lines.append("")
    out_lines.append("## Summary")
    out_lines.append("")
    out_lines.append(f"- OK: **{ok_count}/{len(inputs)}**")
    out_lines.append(f"- Finished(UTC): `{finished_at.isoformat()}`")
    out_lines.append("")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out_lines).rstrip() + "\n", encoding="utf-8")

    print(f"[OK] wrote {out_path} (ok={ok_count}/{len(inputs)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

