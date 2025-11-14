"""
카드고릴라 API 클라이언트

카드고릴라 API에서 카드 데이터를 수집하고, 압축 컨텍스트 형식으로 저장합니다.
단종 카드(is_discon: true)는 자동으로 제외합니다.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

# 카드고릴라 API 기본 URL
BASE_URL = "https://api.card-gorilla.com:8080/v1"


class RateLimiter:
    """Rate limiting을 위한 클래스"""
    
    def __init__(self, max_requests: int = 5, time_window: int = 1):
        """
        Args:
            max_requests: time_window 내 최대 요청 수
            time_window: 시간 윈도우 (초)
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []  # 요청 시간 기록
    
    async def acquire(self):
        """요청 전에 속도 확인하고 필요시 대기"""
        now = datetime.now()
        
        # 최근 time_window 내 요청만 남기기
        self.requests = [
            req_time for req_time in self.requests 
            if now - req_time < timedelta(seconds=self.time_window)
        ]
        
        # 제한 초과시 대기
        if len(self.requests) >= self.max_requests:
            wait_time = (self.requests[0] + timedelta(seconds=self.time_window) - now).total_seconds()
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                # 대기 후 다시 정리
                now = datetime.now()
                self.requests = [
                    req_time for req_time in self.requests 
                    if now - req_time < timedelta(seconds=self.time_window)
                ]
        
        # 요청 기록
        self.requests.append(datetime.now())


class CardGorillaClient:
    """카드고릴라 API 클라이언트"""
    
    def __init__(self, cache_dir: str = "data/cache/ctx"):
        """
        Args:
            cache_dir: 압축 컨텍스트 저장 디렉터리
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limiter = RateLimiter(max_requests=5, time_window=1)
        self.timeout = httpx.Timeout(30.0, connect=10.0)
    
    async def fetch_card_detail(self, card_id: int, use_cache: bool = True) -> Optional[Dict]:
        """
        카드 상세 정보 조회
        
        Args:
            card_id: 카드 ID
            use_cache: 캐시 사용 여부
        
        Returns:
            카드 데이터 (Dict) 또는 None (404 등)
        """
        cache_file = self.cache_dir / f"{card_id}.json"
        
        # 캐시 확인
        if use_cache and cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️  캐시 로드 실패 (card_id={card_id}): {e}")
        
        # Rate limiting
        await self.rate_limiter.acquire()
        
        # API 호출
        url = f"{BASE_URL}/cards/{card_id}"
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url)
                    
                    if response.status_code == 404:
                        print(f"⚠️  카드를 찾을 수 없음 (card_id={card_id})")
                        return None
                    
                    if response.status_code == 429:
                        wait_time = 60 * (2 ** attempt)  # 지수 백오프
                        print(f"⏳ Rate limit 초과, {wait_time}초 대기...")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # 단종 카드 제외
                    if data.get("is_discon", False):
                        print(f"⏭️  단종 카드 제외 (card_id={card_id})")
                        return None
                    
                    # 압축 컨텍스트로 변환 및 저장
                    compressed = self._compress_context(data)
                    if compressed:
                        with open(cache_file, 'w', encoding='utf-8') as f:
                            json.dump(compressed, f, ensure_ascii=False, indent=2)
                        print(f"✅ 카드 저장 완료 (card_id={card_id})")
                    
                    return compressed
                    
            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"⏳ 타임아웃, {wait_time}초 후 재시도... (card_id={card_id})")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"❌ 타임아웃 (card_id={card_id})")
                    return None
                    
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"⏳ 서버 오류, {wait_time}초 후 재시도... (card_id={card_id})")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"❌ 서버 오류 (card_id={card_id}): {e.response.status_code}")
                        return None
                else:
                    print(f"❌ HTTP 오류 (card_id={card_id}): {e.response.status_code}")
                    return None
                    
            except Exception as e:
                print(f"❌ 예상치 못한 오류 (card_id={card_id}): {e}")
                return None
        
        return None
    
    async def fetch_cards_batch(self, card_ids: List[int], use_cache: bool = True) -> Dict[int, Dict]:
        """
        여러 카드 정보를 배치로 조회
        
        Args:
            card_ids: 카드 ID 리스트
            use_cache: 캐시 사용 여부
        
        Returns:
            {card_id: card_data} 딕셔너리
        """
        results = {}
        errors = []
        
        for card_id in card_ids:
            try:
                data = await self.fetch_card_detail(card_id, use_cache=use_cache)
                if data:
                    results[card_id] = data
                # 너무 빠르게 요청하지 않도록 약간의 딜레이
                await asyncio.sleep(0.2)
            except Exception as e:
                errors.append({"card_id": card_id, "error": str(e)})
        
        if errors:
            print(f"⚠️  {len(errors)}개 카드 조회 실패")
            for err in errors[:5]:  # 처음 5개만 출력
                print(f"   - card_id={err['card_id']}: {err['error']}")
        
        return results
    
    def _compress_context(self, raw_data: Dict) -> Optional[Dict]:
        """
        원본 API 응답을 압축 컨텍스트 형식으로 변환
        
        Args:
            raw_data: 원본 API 응답
        
        Returns:
            압축 컨텍스트 Dict 또는 None (단종 카드 등)
        """
        # 단종 카드 재확인
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
    
    async def clear_cache(self, card_id: Optional[int] = None):
        """
        캐시 삭제
        
        Args:
            card_id: 특정 카드 ID (None이면 전체 삭제)
        """
        if card_id:
            cache_file = self.cache_dir / f"{card_id}.json"
            if cache_file.exists():
                cache_file.unlink()
                print(f"🗑️  캐시 삭제 (card_id={card_id})")
        else:
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
            print(f"🗑️  전체 캐시 삭제 완료")


# 사용 예시
async def main():
    """테스트용 메인 함수"""
    client = CardGorillaClient()
    
    # 단일 카드 조회
    card_data = await client.fetch_card_detail(2862)
    if card_data:
        print(f"카드명: {card_data['meta']['name']}")
        print(f"발급사: {card_data['meta']['issuer']}")
        print(f"전월실적: {card_data['conditions']['prev_month_min']:,}원")
    
    # 배치 조회
    # card_ids = [2862, 1357, 2000]
    # results = await client.fetch_cards_batch(card_ids)
    # print(f"조회 완료: {len(results)}개")


if __name__ == "__main__":
    asyncio.run(main())

