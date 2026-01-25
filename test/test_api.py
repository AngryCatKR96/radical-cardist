#!/usr/bin/env python3
"""
신용카드 추천 API 테스트 스크립트 (RAG + Agentic 구조)

⚠️ 주의: 이 테스트를 실행하기 전에 반드시 카드 데이터를 동기화해야 합니다!

준비 단계:
1. 서버 시작: python main.py
2. 카드 동기화: curl -X POST "http://localhost:8000/admin/cards/sync"
3. 테스트 실행: python test_api.py

💰 OpenAI API 크레딧 사용:
- test_health, test_root, test_admin_stats: 크레딧 사용 안함 ✅
- test_admin_sync_single: 임베딩 생성 (한 번만, 캐시됨) ✅
- test_natural_language_recommendation: 매번 크레딧 사용! ⚠️
  * GPT-4 호출: 테스트 케이스당 약 7회 (파싱, 분석×5, 응답 생성)
  * Embedding 호출: 테스트 케이스당 1회
  * 기본 3개 케이스 = 약 21회 GPT-4 + 3회 Embedding

사용법:
- python test_api.py          # 전체 테스트 (OpenAI 크레딧 사용)
- python test_api.py --lite    # 관리 API만 테스트 (크레딧 절약)
- python test_api.py --single  # 추천 1개만 테스트 (크레딧 최소화)
"""

import requests
import json
import time
import sys
import os

BASE_URL = "http://localhost:8000"


def _admin_headers() -> dict:
    """
    관리자 API 호출용 헤더 생성
    - main.py의 require_admin_auth는 X-API-Key 헤더를 요구합니다.
    """
    key = os.getenv("ADMIN_API_KEY")
    if not key:
        return {}
    return {"X-API-Key": key}

# 테스트 모드 파싱
TEST_MODE = "full"  # full, lite, single
if len(sys.argv) > 1:
    if sys.argv[1] == "--lite":
        TEST_MODE = "lite"
    elif sys.argv[1] == "--single":
        TEST_MODE = "single"


def test_health():
    """서비스 상태 확인"""
    print("[TEST] 서비스 상태 확인 중...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] 서비스 상태: {data['status']}")
            print(f"    LLM 서비스: {data.get('llm_service', 'N/A')}")
            print(f"    OpenAI API: {data.get('openai_api_key', 'N/A')}")
            return True
        else:
            print(f"[FAIL] 서비스 상태 확인 실패: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("[FAIL] 서비스에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.")
        print("       실행 방법: python main.py")
        return False
    except Exception as e:
        print(f"[FAIL] 오류 발생: {str(e)}")
        return False


def test_root():
    """루트 엔드포인트 확인"""
    print("\n[TEST] 루트 엔드포인트 확인 중...")
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] 서비스명: {data.get('service', 'N/A')}")
            print(f"    버전: {data.get('version', 'N/A')}")
            print("    사용 가능한 엔드포인트:")
            endpoints = data.get('endpoints', {})
            for endpoint, desc in endpoints.items():
                print(f"      - {endpoint}: {desc}")
            return True
        else:
            print(f"[FAIL] 루트 엔드포인트 확인 실패: {response.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] 오류 발생: {str(e)}")
        return False


def test_natural_language_recommendation(limit_cases=None):
    """자연어 입력 기반 카드 추천 테스트"""
    print("\n[TEST] 자연어 입력 기반 카드 추천 테스트 중...")
    
    test_inputs = [
        "마트 30만원, 넷플릭스/유튜브 구독, 간편결제 자주 씀. 연회비 2만원 이하, 체크카드 선호.",
        "온라인쇼핑 많이 해요. 월 50만원 정도. 연회비 없으면 좋겠어요.",
        "카페에서 일주일에 3-4번 가고, 편의점도 자주 이용해요. 월 10만원 정도."
    ]
    
    # limit_cases가 지정되면 테스트 케이스 제한
    if limit_cases:
        test_inputs = test_inputs[:limit_cases]
        print(f"    💰 크레딧 절약 모드: {limit_cases}개 케이스만 테스트")
    
    for i, user_input in enumerate(test_inputs, 1):
        print(f"\n  테스트 케이스 {i}: {user_input[:50]}...")
        try:
            response = requests.post(
                f"{BASE_URL}/recommend/natural-language",
                json={"user_input": user_input},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                card = data.get('card', {})
                analysis = data.get('analysis', {})

                print(f"    [OK] 추천 성공!")
                print(
                    f"    추천 카드: {card.get('name', 'N/A')} ({card.get('brand', '-')})"
                    f" - ID: {card.get('id', 'N/A')}"
                )
                print(f"    연 절약액: {card.get('annual_savings', 0):,}원")
                print(f"    월 절약액: {card.get('monthly_savings', 0):,}원")
                print(f"    연회비: {card.get('annual_fee', '정보 없음')}")
                print(f"    전월 실적: {card.get('required_spend', '정보 없음')}")
                print(f"    순 혜택: {analysis.get('net_benefit', 0):,}원")

                if card.get('benefits'):
                    print("    주요 혜택:")
                    for benefit in card['benefits']:
                        print(f"      - {benefit}")

                if analysis.get('warnings'):
                    print(f"    주의사항: {', '.join(analysis['warnings'])}")

                if analysis.get('category_breakdown'):
                    print(f"    카테고리별 절약:")
                    for cat, amount in analysis['category_breakdown'].items():
                        print(f"      - {cat}: {amount:,}원/월")

                # 추천 텍스트 일부만 표시
                explanation = data.get('explanation', '')
                if explanation:
                    lines = explanation.split('\n')[:3]
                    print(f"    추천 요약:")
                    for line in lines:
                        if line.strip():
                            print(f"      {line.strip()}")
            elif response.status_code == 503:
                print(f"    [WARN] 서비스 초기화 필요: {response.json().get('detail', 'RAG + Agentic 서비스가 준비되지 않았습니다.')}")
                print(f"    힌트: 벡터 DB에 데이터가 있는지 확인하세요.")
                print(f"    데이터 동기화: POST {BASE_URL}/admin/cards/sync")
            elif response.status_code in (400, 404):
                detail = response.json().get('detail', response.text)
                print(f"    [WARN] 추천 실패: {detail}")
            else:
                print(f"    [FAIL] 요청 실패: {response.status_code}")
                try:
                    error_detail = response.json().get('detail', response.text)
                    print(f"    오류 상세: {error_detail}")
                except:
                    print(f"    응답: {response.text[:200]}")
                    
        except Exception as e:
            print(f"    [FAIL] 오류 발생: {str(e)}")
        
        # 요청 간 딜레이
        if i < len(test_inputs):
            time.sleep(1)


def test_admin_stats():
    """관리자 API - 벡터 DB 통계 확인"""
    print("\n[TEST] 벡터 DB 통계 확인 중...")
    try:
        response = requests.get(f"{BASE_URL}/admin/cards/stats", headers=_admin_headers())
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] 벡터 DB 통계:")
            print(f"    총 문서 수: {data.get('total_documents', 0):,}개")
            print(f"    총 카드 수: {data.get('total_cards', 0):,}개")
            print(f"    컬렉션: {data.get('collection_name', 'N/A')}") 
            return data.get('total_cards', 0) > 0
        elif response.status_code == 401:
            print("[FAIL] 통계 조회 실패: 401")
            print("       오류: 관리자 API key가 필요합니다. X-API-Key 헤더를 추가해주세요.")
            print("       해결: .env에 ADMIN_API_KEY를 설정하고, 테스트 실행 시 환경변수로 로드되게 하세요.")
            print("       예) export ADMIN_API_KEY='...'; python test/test_api.py --lite")
            return False
        elif response.status_code == 503:
            print("[WARN] 임베딩 서비스 초기화 필요")
            return False
        else:
            print(f"[FAIL] 통계 조회 실패: {response.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] 오류 발생: {str(e)}")
        return False


def test_admin_reset():
    """관리자 API - 벡터 DB 초기화 테스트"""
    print("\n[TEST] 벡터 DB 초기화 테스트 중...")
    print("    ⚠️  경고: embeddings(임베딩) 데이터가 초기화됩니다!")
    
    try:
        response = requests.delete(f"{BASE_URL}/admin/cards/reset", headers=_admin_headers())
        
        if response.status_code == 200:
            data = response.json()
            print(f"    [OK] 초기화 성공!")
            print(f"    수정된 문서: {data.get('modified_documents', 0):,}개")
            return True
        elif response.status_code == 401:
            print("    [FAIL] 초기화 실패: 401")
            print("    오류: 관리자 API key가 필요합니다. X-API-Key 헤더를 추가해주세요.")
            return False
        elif response.status_code == 503:
            print(f"    [WARN] 임베딩 서비스 초기화 필요")
            return False
        else:
            print(f"    [FAIL] 초기화 실패: {response.status_code}")
            try:
                error_detail = response.json().get('detail', response.text)
                print(f"    오류: {error_detail}")
            except:
                print(f"    응답: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"    [FAIL] 오류 발생: {str(e)}")
        return False


def test_admin_sync_single():
    """관리자 API - 단일 카드 동기화 테스트"""
    print("\n[TEST] 단일 카드 동기화 테스트 중...")
    
    # 테스트할 카드 ID (예시)
    test_card_id = 2862
    
    print(f"    카드 ID {test_card_id} 동기화 시도...")
    try:
        response = requests.post(
            f"{BASE_URL}/admin/cards/{test_card_id}",
            params={"overwrite": True},
            headers=_admin_headers(),
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"    [OK] 동기화 성공!")
            print(f"    카드명: {data.get('card_name', 'N/A')}")
            print(f"    발급사: {data.get('issuer', 'N/A')}")
            return True
        elif response.status_code == 401:
            print(f"    [FAIL] 동기화 실패: 401")
            print("    오류: 관리자 API key가 필요합니다. X-API-Key 헤더를 추가해주세요.")
            return False
        elif response.status_code == 404:
            print(f"    [WARN] 카드를 찾을 수 없거나 단종된 카드")
            return False
        elif response.status_code == 503:
            print(f"    [WARN] 동기화 서비스 초기화 필요")
            return False
        else:
            print(f"    [FAIL] 동기화 실패: {response.status_code}")
            try:
                error_detail = response.json().get('detail', response.text)
                print(f"    오류: {error_detail}")
            except:
                print(f"    응답: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"    [FAIL] 오류 발생: {str(e)}")
        return False


def main():
    """메인 테스트 함수"""
    print("=" * 60)
    print("신용카드 추천 API 테스트 (RAG + Agentic 구조)")
    if TEST_MODE == "lite":
        print("모드: LITE (관리 API만, OpenAI 크레딧 절약) 💰")
    elif TEST_MODE == "single":
        print("모드: SINGLE (추천 1개만, 크레딧 최소화) 💰")
    else:
        print("모드: FULL (전체 테스트, OpenAI 크레딧 사용) ⚠️")
    print("=" * 60)
    
    # 서비스 상태 확인
    if not test_health():
        print("\n[INFO] 서버를 먼저 시작해주세요: python main.py")
        return
    
    # 루트 엔드포인트 확인
    test_root()
    
    # 잠시 대기 (서비스 초기화 시간)
    print("\n[INFO] 서비스 초기화 대기 중...")
    time.sleep(2)
    
    # 관리자 API 테스트
    print("\n" + "=" * 60)
    print("관리자 API 테스트 (벡터 DB 관리)")
    print("=" * 60)
    
    has_data = test_admin_stats()
    
    if not has_data:
        print("\n" + "!" * 60)
        print("⚠️  경고: 벡터 DB에 데이터가 없습니다!")
        print("!" * 60)
        print("\n추천 API를 테스트하려면 먼저 카드 데이터를 동기화해야 합니다.")
        print("\n옵션 1: 자동 동기화 시도 (단일 카드로 빠른 테스트)")
        print("        이 스크립트가 자동으로 시도합니다...")
        print("        💰 OpenAI 크레딧 사용: text-embedding-3-small (카드당 3~5회)")
        
        if test_admin_sync_single():
            print("\n[INFO] 동기화 성공! 잠시 후 통계를 다시 확인합니다...")
            time.sleep(3)
            has_data = test_admin_stats()
        else:
            print("\n[FAIL] 자동 동기화 실패")
            print("\n옵션 2: 수동 동기화 (권장)")
            print("        별도 터미널에서 다음 명령어를 실행하세요:")
            print("        curl -X POST 'http://localhost:8000/admin/cards/sync'")
            print("\n동기화 후 이 테스트를 다시 실행해주세요.")
            return
    
    # LITE 모드는 여기서 종료 (추천 API 테스트 안함)
    if TEST_MODE == "lite":
        print("\n" + "=" * 60)
        print("✅ LITE 모드 테스트 완료 (추천 API 테스트 생략)")
        print("=" * 60)
        print("\n💰 OpenAI 크레딧 사용: 없음 (또는 동기화만)")
        print("\n전체 테스트를 실행하려면: python test_api.py")
        return
    
    # 자연어 추천 테스트
    print("\n" + "=" * 60)
    print("자연어 입력 기반 카드 추천 테스트")
    if TEST_MODE == "single":
        print("(크레딧 절약 모드: 1개 케이스만)")
    print("=" * 60)
    
    if has_data:
        if TEST_MODE == "single":
            test_natural_language_recommendation(limit_cases=1)
            print("\n💰 예상 크레딧 사용: GPT-4 약 7회 + Embedding 1회")
        else:
            test_natural_language_recommendation()
            print("\n💰 예상 크레딧 사용: GPT-4 약 21회 + Embedding 3회")
    else:
        print("[SKIP] 벡터 DB에 데이터가 없어 추천 테스트를 건너뜁니다.")
    
    # 테스트 완료
    print("\n" + "=" * 60)
    print("[OK] 모든 테스트 완료!")
    print("=" * 60)
    print("\n[INFO] 추가 테스트 방법:")
    print("   1. 브라우저에서 http://localhost:8000/docs 방문")
    print("   2. Swagger UI에서 각 엔드포인트를 직접 테스트")
    print("   3. 다양한 소비 패턴으로 자연어 추천 테스트")
    print("\n[INFO] 관리자 API 사용법:")
    print("   1. 벡터 DB 통계: GET http://localhost:8000/admin/cards/stats")
    print("   2. 단일 카드 동기화: POST http://localhost:8000/admin/cards/{card_id}")
    print("   3. 전체 동기화: POST http://localhost:8000/admin/cards/sync")
    print("\n[INFO] 데이터 준비:")
    print("   - OPENAI_API_KEY가 .env 파일에 설정되어 있어야 합니다")
    print("   - 카드 데이터는 관리자 API로 자동 수집/동기화됩니다")


if __name__ == "__main__":
    main()
