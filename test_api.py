#!/usr/bin/env python3
"""
신용카드 추천 API 테스트 스크립트
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_health():
    """서비스 상태 확인"""
    print("🔍 서비스 상태 확인 중...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 서비스 상태: {data['status']}")
            print(f"   LLM 서비스: {data['llm_service']}")
            print(f"   OpenAI API: {data['openai_api_key']}")
        else:
            print(f"❌ 서비스 상태 확인 실패: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ 서비스에 연결할 수 없습니다. 서비스가 실행 중인지 확인해주세요.")
        return False
    return True

def test_cards():
    """사용 가능한 카드 목록 조회"""
    print("\n🔍 사용 가능한 카드 목록 조회 중...")
    try:
        response = requests.get(f"{BASE_URL}/cards")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 총 {data['total']}개 카드 발견")
            for i, card in enumerate(data['cards'][:3], 1):  # 처음 3개만 표시
                print(f"   {i}. {card['name']} ({card['bank']})")
            if len(data['cards']) > 3:
                print(f"   ... 및 {len(data['cards']) - 3}개 더")
        else:
            print(f"❌ 카드 목록 조회 실패: {response.status_code}")
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")

def test_recommendation():
    """카드 추천 테스트"""
    print("\n🔍 카드 추천 테스트 중...")
    
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
            print("✅ 추천 결과:")
            print(f"   📊 월 절약: {data['monthly_savings']:,}원")
            print(f"   📊 연 절약: {data['annual_savings']:,}원")
            print(f"   💰 총 연회비: {data['total_annual_fee']:,}원")
            print(f"   💰 순 절약: {data['net_annual_savings']:,}원")
            print(f"   🎯 추천 카드 수: {len(data['selected_cards'])}개")
            
            print("\n📝 상세 추천:")
            print(data['recommendation_text'])
            
        else:
            print(f"❌ 추천 요청 실패: {response.status_code}")
            print(f"   응답: {response.text}")
            
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")

def test_simple_recommendation():
    """간단한 추천 테스트"""
    print("\n🔍 간단한 추천 테스트 중...")
    
    test_data = {
        "monthly_spending": 500000,
        "spending_breakdown": {
            "온라인쇼핑": 150000,
            "마트": 100000,
            "카페": 30000,
            "편의점": 50000
        },
        "subscriptions": ["넷플릭스"]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/recommend",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 간단한 추천 결과:")
            print(f"   📊 월 절약: {data['monthly_savings']:,}원")
            print(f"   📊 연 절약: {data['annual_savings']:,}원")
            print(f"   🎯 추천 카드 수: {len(data['selected_cards'])}개")
            
            for i, card in enumerate(data['selected_cards'], 1):
                print(f"   {i}. {card['card']['name']} ({card['card']['bank']})")
                print(f"      월 혜택: {card['monthly_benefit']:,}원")
                
        else:
            print(f"❌ 간단한 추천 요청 실패: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")

def main():
    """메인 테스트 함수"""
    print("🚀 신용카드 추천 API 테스트 시작")
    print("=" * 50)
    
    # 서비스 상태 확인
    if not test_health():
        return
    
    # 잠시 대기 (서비스 초기화 시간)
    print("\n⏳ 서비스 초기화 대기 중...")
    time.sleep(2)
    
    # 카드 목록 조회
    test_cards()
    
    # 추천 테스트
    test_recommendation()
    
    # 간단한 추천 테스트
    test_simple_recommendation()
    
    print("\n" + "=" * 50)
    print("✅ 모든 테스트 완료!")
    print("\n💡 추가 테스트:")
    print("   - 브라우저에서 http://localhost:8000/docs 방문")
    print("   - 다양한 소비 패턴으로 테스트")
    print("   - 실제 OpenAI API 키로 더 정확한 결과 확인")

if __name__ == "__main__":
    main()
