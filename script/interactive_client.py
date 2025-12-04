# interactive_client.py
import json
import textwrap
from typing import Any, Dict, Optional

import requests

BASE_URL = "http://localhost:8000"  # 필요하면 포트/도메인 바꿔서 사용


def pretty_print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def call_post(
    path: str,
    json_body: Any = None,
) -> Optional[Dict[str, Any]]:
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.post(url, json=json_body, timeout=60)
        print(f"\n[POST] {url}  →  {resp.status_code}")
        if resp.headers.get("content-type", "").startswith("application/json"):
            data = resp.json()
            pretty_print_json(data)
            return data
        else:
            print(resp.text)
            return None
    except requests.RequestException as e:
        print(f"요청 실패: {e}")
        return None


def call_get(path: str) -> Optional[Dict[str, Any]]:
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.get(url, timeout=30)
        print(f"\n[GET] {url}  →  {resp.status_code}")
        if resp.headers.get("content-type", "").startswith("application/json"):
            data = resp.json()
            pretty_print_json(data)
            return data
        else:
            print(resp.text)
            return None
    except requests.RequestException as e:
        print(f"요청 실패: {e}")
        return None


def menu_recommend_natural_language() -> None:
    print("\n=== 자연어 소비 패턴으로 카드 추천 테스트 ===")
    print("예시: 마트 30만원, 넷플릭스/유튜브 구독, 간편결제 자주 씀. 연회비 2만원 이하, 체크카드 선호.")
    query = input("\n소비 패턴을 자연어로 입력하세요:\n> ").strip()
    if not query:
        print("입력이 비어 있습니다.")
        return

    data = call_post(
        "/recommend/natural-language",
        json_body={"user_input": query},
    )
    if not data:
        return

    # 추천 요약만 깔끔하게 한 번 더 보여주기
    print("\n----- 요약 -----")
    rec_text = data.get("recommendation_text")
    if rec_text:
        print(textwrap.fill(rec_text, width=80))
    selected_card = data.get("selected_card") or {}
    if selected_card:
        print("\n[선택된 카드]")
        print(f"- 카드 ID : {selected_card.get('card_id')}")
        print(f"- 이름     : {selected_card.get('name')}")
        print(f"- 발급사   : {selected_card.get('issuer')}")
    print("----------------\n")


def menu_admin_sync() -> None:
    print("\n=== 카드 전체 동기화 (fetch + embed) ===")
    print("주의: OpenAI 임베딩 단계에서 크레딧이 사용될 수 있습니다.")
    confirm = input("진행할까요? (y/N): ").strip().lower()
    if confirm != "y":
        print("취소했습니다.")
        return

    call_post("/admin/cards/sync")


def menu_admin_sync_single() -> None:
    print("\n=== 특정 카드 1장 동기화 (fetch + embed) ===")
    card_id_str = input("카드 ID를 입력하세요 (예: 2862): ").strip()
    if not card_id_str.isdigit():
        print("숫자만 입력해주세요.")
        return

    overwrite = input("기존 데이터 덮어쓸까요? (y/N): ").strip().lower()
    overwrite_flag = "true" if overwrite == "y" else "false"

    path = f"/admin/cards/{card_id_str}?overwrite={overwrite_flag}"
    call_post(path)


def menu_admin_stats() -> None:
    print("\n=== 벡터 DB 상태 조회 ===")
    call_get("/admin/cards/stats")


def menu_reset_vector_db() -> None:
    print("\n=== ⚠️ 벡터 DB 초기화 ===")
    print("정말로 모든 임베딩 데이터를 삭제합니다.")
    confirm = input("진짜로 진행할까요? (delete 입력 시 실행): ").strip().lower()
    if confirm != "delete":
        print("취소했습니다.")
        return

    url = f"{BASE_URL}/admin/cards/reset"
    try:
        resp = requests.delete(url, timeout=30)
        print(f"\n[DELETE] {url}  →  {resp.status_code}")
        if resp.headers.get("content-type", "").startswith("application/json"):
            pretty_print_json(resp.json())
        else:
            print(resp.text)
    except requests.RequestException as e:
        print(f"요청 실패: {e}")


def main():
    print("=== 💳 Radical Cardist 대화형 테스트 클라이언트 ===")
    print(f"현재 BASE_URL: {BASE_URL}")
    print("서버가 먼저 떠 있어야 합니다. (예: python main.py 또는 uvicorn main:app --reload)")

    while True:
        print(
            """
---------------- 메뉴 ----------------
1. 자연어로 카드 추천 받아보기 (/recommend/natural-language)
2. 카드 전체 동기화 (fetch + embed) (/admin/cards/sync)
3. 특정 카드 1장 동기화 (/admin/cards/{card_id})
4. 벡터 DB 상태 조회 (/admin/cards/stats)
5. 벡터 DB 초기화 (/admin/cards/reset)
0. 종료
-------------------------------------
"""
        )
        choice = input("번호를 선택하세요: ").strip()

        if choice == "1":
            menu_recommend_natural_language()
        elif choice == "2":
            menu_admin_sync()
        elif choice == "3":
            menu_admin_sync_single()
        elif choice == "4":
            menu_admin_stats()
        elif choice == "5":
            menu_reset_vector_db()
        elif choice == "0":
            print("종료합니다.")
            break
        else:
            print("잘못된 입력입니다. 0~5 중에서 선택해주세요.")


if __name__ == "__main__":
    main()
