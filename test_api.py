#!/usr/bin/env python3
"""
신용카드 추천 API 테스트 스크립트 (RAG + Agentic 구조)
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"


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


def test_natural_language_recommendation():
    """자연어 입력 기반 카드 추천 테스트"""
    print("\n[TEST] 자연어 입력 기반 카드 추천 테스트 중...")
    
    test_inputs = [
        "마트 30만원, 넷플릭스/유튜브 구독, 간편결제 자주 씀. 연회비 2만원 이하, 체크카드 선호.",
        "온라인쇼핑 많이 해요. 월 50만원 정도. 연회비 없으면 좋겠어요.",
        "카페에서 일주일에 3-4번 가고, 편의점도 자주 이용해요. 월 10만원 정도."
    ]
    
    for i, user_input in enumerate(test_inputs, 1):
        print(f"\n  테스트 케이스 {i}: {user_input[:50]}...")
        try:
            response = requests.post(
                f"{BASE_URL}/recommend/natural-language",
                json=user_input,  # FastAPI는 문자열을 JSON으로 받음
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if "error" in data:
                    print(f"    [WARN] {data.get('error', '알 수 없는 오류')}")
                    if "recommendation_text" in data:
                        print(f"    메시지: {data['recommendation_text']}")
                else:
                    print(f"    [OK] 추천 성공!")
                    print(f"    추천 카드: {data.get('selected_card', {}).get('name', 'N/A')} (ID: {data.get('selected_card', {}).get('card_id', 'N/A')})")
                    print(f"    연 절약액: {data.get('annual_savings', 0):,}원")
                    print(f"    월 절약액: {data.get('monthly_savings', 0):,}원")
                    print(f"    연회비: {data.get('annual_fee', 0):,}원")
                    print(f"    순 혜택: {data.get('net_benefit', 0):,}원")
                    
                    analysis = data.get('analysis_details', {})
                    if analysis.get('warnings'):
                        print(f"    주의사항: {', '.join(analysis['warnings'])}")
                    
                    if analysis.get('category_breakdown'):
                        print(f"    카테고리별 절약:")
                        for cat, amount in analysis['category_breakdown'].items():
                            print(f"      - {cat}: {amount:,}원/월")
                    
                    # 추천 텍스트 일부만 표시
                    rec_text = data.get('recommendation_text', '')
                    if rec_text:
                        lines = rec_text.split('\n')[:3]
                        print(f"    추천 요약:")
                        for line in lines:
                            if line.strip():
                                print(f"      {line.strip()}")
            elif response.status_code == 503:
                print(f"    [WARN] 서비스 초기화 필요: {response.json().get('detail', 'RAG + Agentic 서비스가 준비되지 않았습니다.')}")
                print(f"    힌트: 벡터 DB에 데이터가 있는지 확인하세요.")
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


def test_structured_recommendation():
    """구조화된 입력 기반 카드 추천 테스트"""
    print("\n[TEST] 구조화된 입력 기반 카드 추천 테스트 중...")
    
    test_cases = [
        {
            "spending": {
                "grocery": {"amount": 300000},
                "digital_payment": {"amount": 200000},
                "subscription_video": {"amount": 30000}
            },
            "preferences": {
                "max_annual_fee": 20000,
                "prefer_types": ["debit"]
            },
            "query_text": "마트 30만원, OTT 구독, 간편결제 많이 사용, 연회비 2만원 이하, 체크카드 선호",
            "filters": {
                "annual_fee_max": 20000,
                "pre_month_min_max": 500000,
                "type": "debit"
            }
        },
        {
            "spending": {
                "online_shopping": {"amount": 500000},
                "cafe": {"amount": 100000}
            },
            "preferences": {
                "max_annual_fee": 0,
                "prefer_types": ["credit"]
            },
            "query_text": "온라인쇼핑 많이 함, 카페 자주 감, 연회비 없음",
            "filters": {
                "annual_fee_max": 0,
                "type": "credit"
            }
        }
    ]
    
    for i, user_intent in enumerate(test_cases, 1):
        print(f"\n  테스트 케이스 {i}:")
        print(f"    소비 패턴: {list(user_intent['spending'].keys())}")
        print(f"    선호사항: 연회비 최대 {user_intent['preferences'].get('max_annual_fee', 0):,}원")
        
        try:
            response = requests.post(
                f"{BASE_URL}/recommend/structured",
                json=user_intent,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if "error" in data:
                    print(f"    [WARN] {data.get('error', '알 수 없는 오류')}")
                else:
                    print(f"    [OK] 추천 성공!")
                    print(f"    추천 카드: {data.get('selected_card', {}).get('name', 'N/A')} (ID: {data.get('selected_card', {}).get('card_id', 'N/A')})")
                    print(f"    연 절약액: {data.get('annual_savings', 0):,}원")
                    print(f"    월 절약액: {data.get('monthly_savings', 0):,}원")
                    print(f"    연회비: {data.get('annual_fee', 0):,}원")
                    print(f"    순 혜택: {data.get('net_benefit', 0):,}원")
                    
                    analysis = data.get('analysis_details', {})
                    if analysis.get('conditions_met') is False:
                        print(f"    [WARN] 전월실적 조건 미충족")
            elif response.status_code == 503:
                print(f"    [WARN] 서비스 초기화 필요")
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
        if i < len(test_cases):
            time.sleep(1)


def test_legacy_recommendation():
    """기존 추천 엔드포인트 테스트 (하위 호환성)"""
    print("\n[TEST] 기존 추천 엔드포인트 테스트 중...")
    
    test_data = {
        "monthly_spending": 1000000,
        "spending_breakdown": {
            "온라인쇼핑": 300000,
            "마트": 200000,
            "편의점": 100000,
            "카페": 50000,
            "대중교통": 100000,
            "주유": 150000,
            "배달앱": 100000
        },
        "subscriptions": ["넷플릭스", "유튜브프리미엄", "스포티파이"]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/recommend",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print("[OK] 기존 엔드포인트 정상 작동")
            print(f"    월 절약: {data.get('monthly_savings', 0):,}원")
            print(f"    연 절약: {data.get('annual_savings', 0):,}원")
            print(f"    추천 카드 수: {len(data.get('selected_cards', []))}개")
        elif response.status_code == 503:
            print("[WARN] LLM 서비스 초기화 필요")
        else:
            print(f"[FAIL] 요청 실패: {response.status_code}")
            print(f"    응답: {response.text[:200]}")
            
    except Exception as e:
        print(f"[FAIL] 오류 발생: {str(e)}")


def test_cards_endpoint():
    """카드 목록 조회 테스트 (기존 엔드포인트)"""
    print("\n[TEST] 카드 목록 조회 테스트 중...")
    try:
        response = requests.get(f"{BASE_URL}/cards")
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] 총 {data.get('total', 0)}개 카드 발견")
            cards = data.get('cards', [])
            for i, card in enumerate(cards[:3], 1):
                print(f"    {i}. {card.get('name', 'N/A')} ({card.get('bank', 'N/A')})")
            if len(cards) > 3:
                print(f"    ... 및 {len(cards) - 3}개 더")
        elif response.status_code == 503:
            print("[WARN] LLM 서비스 초기화 필요")
        else:
            print(f"[FAIL] 카드 목록 조회 실패: {response.status_code}")
    except Exception as e:
        print(f"[FAIL] 오류 발생: {str(e)}")


def main():
    """메인 테스트 함수"""
    print("=" * 60)
    print("신용카드 추천 API 테스트 (RAG + Agentic 구조)")
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
    
    # 새로운 엔드포인트 테스트
    print("\n" + "=" * 60)
    print("새로운 RAG + Agentic 엔드포인트 테스트")
    print("=" * 60)
    
    test_natural_language_recommendation()
    test_structured_recommendation()
    
    # 기존 엔드포인트 테스트 (하위 호환성)
    print("\n" + "=" * 60)
    print("기존 엔드포인트 테스트 (하위 호환성)")
    print("=" * 60)
    
    test_cards_endpoint()
    test_legacy_recommendation()
    
    # 테스트 완료
    print("\n" + "=" * 60)
    print("[OK] 모든 테스트 완료!")
    print("=" * 60)
    print("\n[INFO] 추가 테스트 방법:")
    print("   1. 브라우저에서 http://localhost:8000/docs 방문")
    print("   2. Swagger UI에서 각 엔드포인트를 직접 테스트")
    print("   3. 다양한 소비 패턴으로 자연어 추천 테스트")
    print("   4. 벡터 DB에 데이터가 있어야 정상 작동합니다")
    print("\n[INFO] 데이터 준비:")
    print("   1. 카드 데이터 수집: data_collection/card_gorilla_client.py 사용")
    print("   2. 임베딩 생성: vector_store/embeddings.py 사용")
    print("   3. .env 파일에 OPENAI_API_KEY 설정 필요")


if __name__ == "__main__":
    main()
