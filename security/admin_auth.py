"""
Admin API 인증

X-API-Key 헤더를 통한 API key 기반 인증을 제공합니다.
constant-time 비교로 타이밍 공격을 방지합니다.
"""

import os
import secrets
from fastapi import Header, HTTPException, Request
from dotenv import load_dotenv
from .ip_utils import get_client_ip, hash_ip

load_dotenv()


class AdminAuth:
    """Admin API key 인증 관리자"""

    def __init__(self):
        """
        환경변수에서 ADMIN_API_KEY 로드

        Raises:
            ValueError: ADMIN_API_KEY가 설정되지 않았거나 기본값인 경우
        """
        self.admin_api_key = os.getenv("ADMIN_API_KEY")

        if not self.admin_api_key or self.admin_api_key == "your_secure_admin_api_key_here":
            raise ValueError(
                "ADMIN_API_KEY 환경변수가 설정되지 않았습니다. "
                ".env 파일에 다음 명령어로 생성한 키를 추가하세요:\n"
                "python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )

    def verify_api_key(self, provided_key: str) -> bool:
        """
        API key 검증 (constant-time 비교)

        Args:
            provided_key: 클라이언트가 제공한 API key

        Returns:
            키가 일치하면 True, 아니면 False

        Note:
            secrets.compare_digest를 사용하여 타이밍 공격 방지
        """
        return secrets.compare_digest(provided_key, self.admin_api_key)


async def require_admin_auth(
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """
    Admin API 인증 FastAPI dependency

    Args:
        request: FastAPI Request 객체
        x_api_key: X-API-Key 헤더 값

    Returns:
        인증 성공 시 True

    Raises:
        HTTPException: 401 (키 없음) 또는 403 (키 불일치)

    Usage:
        @app.get("/admin/endpoint", dependencies=[Depends(require_admin_auth)])
        async def admin_endpoint():
            return {"message": "authorized"}
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key가 필요합니다. X-API-Key 헤더를 추가해주세요.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    try:
        admin_auth = AdminAuth()
    except ValueError as e:
        # 환경변수 설정 오류 (서버 측 문제)
        print(f"[ERROR] Admin auth 초기화 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail="서버 인증 설정 오류"
        )

    if not admin_auth.verify_api_key(x_api_key):
        # 인증 실패 로그 (보안 모니터링용)
        ip_address = get_client_ip(request)
        try:
            hashed_ip = hash_ip(ip_address)
            print(f"[SECURITY] Admin 인증 실패 from IP: {hashed_ip}")
        except Exception:
            print(f"[SECURITY] Admin 인증 실패 from IP: {ip_address}")

        raise HTTPException(
            status_code=403,
            detail="유효하지 않은 API key입니다."
        )

    return True
