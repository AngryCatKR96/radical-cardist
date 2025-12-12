"""
프롬프트 어택 방어

기본 패턴 매칭으로 악의적인 프롬프트 injection 시도를 탐지합니다.
"""

import re
from typing import Tuple, List
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field


class PromptValidator:
    """
    프롬프트 injection 공격 탐지기

    regex 패턴으로 일반적인 공격 패턴을 차단합니다.
    한글 입력을 고려하여 False positive를 최소화합니다.
    """

    def __init__(self):
        """공격 패턴 regex 컴파일"""

        # 카테고리별 공격 패턴 (영어 + 한국어)
        self.attack_patterns = {
            "system_override": [
                # 영어
                r"ignore\s+(previous|all|above)\s+instructions?",
                r"forget\s+(everything|all|previous)",
                r"disregard\s+(previous|all)\s+",
                r"override\s+system",
                r"reset\s+instructions?",
                # 한국어
                r"(이전|기존|앞의|위의)\s*(지시|명령|instruction)(를|을|가|이|은|는)?",  # 조사 포함
                r"무시하(고|라|세요|어)",
                r"잊어버리(고|라|세요|어)",
                r"시스템\s*(프롬프트|명령|지시)(를|을|가|이)?",  # 조사 포함
                r"초기화\s*해",
            ],
            "role_manipulation": [
                # 영어
                r"you\s+are\s+now\s+",
                r"act\s+as\s+(a|an)\s+",
                r"pretend\s+(you'?re|to\s+be)",
                r"roleplay\s+as",
                r"new\s+instructions?:",
                r"from\s+now\s+on",
                # 한국어
                r"너(는|가)\s*이제\s*",
                r"당신(은|는)\s*이제\s*",
                r"\w+(인|처럼)\s+척\s+(해|하)",  # "해커인 척 해", "관리자처럼 척해"
                r"\w+(이|가)\s+되(어|라|세요)",  # "해커가 되어", "관리자가 되세요"
                r"역할\s*(놀이|극)",  # "역할놀이", "역할극"
                r"새로운\s+(지시|명령|instruction)",
                r"지금부터\s+너(는|가)",  # "지금부터 너는"
            ],
            "command_injection": [
                r"<script[\s\S]*?>",
                r"javascript:",
                r"exec\s*\(",
                r"eval\s*\(",
                r"__import__",
                r"system\s*\(",
            ],
            "encoding_tricks": [
                r"\\x[0-9a-f]{2}",     # Hex encoding
                r"\\u[0-9a-f]{4}",     # Unicode escapes
                r"\\[0-7]{3}",         # Octal encoding
                r"%[0-9a-f]{2}",       # URL encoding
            ],
            "excessive_special_chars": [
                r"[^\w\s가-힣]{20,}",  # 20+ consecutive special chars
                r"(.)\1{50,}",          # Same character 50+ times
            ],
        }

        # 패턴 컴파일 (성능 최적화)
        self.compiled_patterns = {}
        for category, patterns in self.attack_patterns.items():
            self.compiled_patterns[category] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]

    def validate(self, user_input: str) -> Tuple[bool, List[str]]:
        """
        사용자 입력 검증

        Args:
            user_input: 검증할 문자열

        Returns:
            (is_valid, matched_patterns): 유효 여부 및 매칭된 패턴 목록
        """
        if not user_input or len(user_input.strip()) == 0:
            return (True, [])

        matched_patterns = []

        # 각 카테고리별로 검사
        for category, patterns in self.compiled_patterns.items():
            for i, pattern in enumerate(patterns):
                match = pattern.search(user_input)
                if match:
                    # 디버깅용: 어떤 패턴이 매칭되었는지 출력
                    print(f"[DEBUG] Pattern matched - Category: {category}, Pattern #{i}, Matched text: '{match.group()}'")
                    matched_patterns.append(category)
                    break  # 카테고리당 한 번만 기록

        is_valid = len(matched_patterns) == 0
        return (is_valid, matched_patterns)

    def sanitize(self, user_input: str) -> str:
        """
        기본 sanitization (선택적)

        Args:
            user_input: sanitize할 문자열

        Returns:
            정제된 문자열
        """
        # Null byte 제거
        sanitized = user_input.replace("\x00", "")

        # 과도한 공백 정규화
        sanitized = re.sub(r"\s+", " ", sanitized)

        return sanitized.strip()


class PromptAttackException(HTTPException):
    """프롬프트 공격 탐지 예외"""
    def __init__(self, matched_patterns: List[str]):
        self.matched_patterns = matched_patterns
        super().__init__(
            status_code=400,
            detail="입력 형식이 올바르지 않습니다. 자연스러운 문장으로 다시 입력해주세요."
        )


def validate_user_input(user_input: str) -> None:
    """
    사용자 입력에 대한 프롬프트 공격 검증

    Args:
        user_input: 검증할 사용자 입력

    Raises:
        PromptAttackException: 악의적 패턴이 탐지된 경우

    Usage:
        validate_user_input(payload.user_input)
    """
    validator = PromptValidator()
    is_valid, matched_patterns = validator.validate(user_input)

    if not is_valid:
        # 보안 로그 (상세 패턴은 노출하지 않음)
        print(f"[SECURITY] Prompt attack detected: {matched_patterns}")

        # Custom exception으로 패턴 정보 전달
        raise PromptAttackException(matched_patterns)
