"""
IP 주소 추출 및 해싱 유틸리티

Cloud Run 환경에서 실제 클라이언트 IP를 추출하고,
프라이버시 보호를 위해 SHA-256으로 해싱합니다.
"""

import os
import hashlib
from datetime import datetime
from fastapi import Request


def get_client_ip(request: Request) -> str:
    """
    Cloud Run 헤더에서 실제 클라이언트 IP 추출

    Args:
        request: FastAPI Request 객체

    Returns:
        클라이언트 IP 주소 문자열

    우선순위:
        1. X-Forwarded-For 헤더 (Cloud Run이 설정)
        2. X-Real-IP 헤더
        3. request.client.host (폴백)
    """
    # Cloud Run은 X-Forwarded-For 헤더를 설정
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # 첫 번째 IP가 실제 클라이언트 IP
        return forwarded_for.split(",")[0].strip()

    # X-Real-IP 헤더 확인
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # 폴백: request.client.host
    if request.client and request.client.host:
        return request.client.host

    # 최후의 폴백
    return "unknown"


def hash_ip(ip_address: str) -> str:
    """
    IP 주소를 SHA-256으로 해싱 (프라이버시 보호)

    Args:
        ip_address: IP 주소 문자열

    Returns:
        SHA-256 해시 (hex string)

    Note:
        - 일일 salt를 사용하여 추가 보안 제공
        - 환경변수 IP_HASH_SALT를 설정해야 함
    """
    # 환경변수에서 salt 로드
    salt = os.getenv("IP_HASH_SALT", "")

    if not salt:
        raise ValueError(
            "IP_HASH_SALT 환경변수가 설정되지 않았습니다. "
            ".env 파일에 다음 명령어로 생성한 salt를 추가하세요:\n"
            "python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )

    # 일일 salt (날짜가 바뀌면 해시도 바뀜)
    date_salt = datetime.utcnow().strftime("%Y-%m-%d")

    # IP + 날짜 + secret salt 조합
    combined = f"{ip_address}:{date_salt}:{salt}"

    # SHA-256 해싱
    return hashlib.sha256(combined.encode()).hexdigest()
