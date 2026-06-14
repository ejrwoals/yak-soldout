#!/usr/bin/env python3
"""
손글씨 주문지 OCR 서비스 (1단계: 로컬 검증)

약국에서 손으로 작성한 주문지 이미지를 멀티모달 LLM(Gemini)으로 읽어
약품명 · 포장단위 · 주문수량 3필드의 배열로 구조화 추출한다.

이 단계에서는 개발 PC에서만 동작하므로 .env 의 GEMINI_API_KEY 로 직접 호출한다.
(배포 단계에서는 키 유출 방지를 위해 호출을 Supabase Edge Function 으로 이전 예정.
 자세한 내용은 docs/손글씨-주문지-OCR-기능-계획.md 참고.)
"""

import json
import os

from dotenv import load_dotenv

# .env 로드 (이미 로드되었으면 무해하게 재호출)
load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash"

# 추출 프롬프트 — 약국 주문지의 도메인 표기 규칙을 학습시켜 3필드로 정규화한다.
_PROMPT = """당신은 한국 약국의 손글씨 주문지를 판독하는 OCR 도우미입니다.
첨부된 이미지는 약사가 손으로 작성한 의약품 주문 목록입니다.
이미지는 보통 2단(왼쪽/오른쪽 열)으로 작성되어 있을 수 있습니다. 각 줄이 한 주문 품목입니다.

각 품목을 다음 4개 필드로 추출하세요:
- drug_name: 약품명. 약품명 뒤에 함량/규격(예: 500mg, 300mg, 60mg, 500/50, 4 등)이
  적혀 있으면 그것까지 약품명에 포함하세요. 예: "리포덱스 600mg", "낙센에스 500/50".
- package_unit: 한 통(병/박스)에 든 포장 단위.
- quantity: 주문할 통(병/박스)의 개수.
- crossed_out: 그 줄에 취소선(글자 위를 가로지르는 줄)이 그어져 있으면 true, 아니면 false.

★ 누락 금지 (가장 중요):
손으로 적힌 모든 줄을 한 줄도 빠뜨리지 말고 추출하세요.
- 왼쪽 열을 맨 위부터 맨 아래까지 전부, 그다음 오른쪽 열을 맨 위부터 맨 아래까지 전부.
- 글씨가 흐리거나, 취소선이 그어졌거나, 동그라미 등 주석이 있어도 모두 포함하세요.
  (취소선이 있는 줄은 빼지 말고 crossed_out=true 로 표시만 하세요.)

★ 주문 수량 표기 규칙 (가장 중요):
주문량은 보통 줄 맨 오른쪽에 "AxB" 형태로 적힙니다 (예: 30X2, 100X3, 14X20).
- X 앞 숫자(A) = 포장 단위 → package_unit 에 "A정" 으로 적으세요. (예: 30X2 → "30정")
- X 뒤 숫자(B) = 주문 수량 → quantity 에 적으세요. (예: 30X2 → "2")
  즉 "30X2"는 '30정짜리 통을 2개 주문'이라는 뜻입니다.

변형 처리:
- "X15", "X5" 처럼 X 앞에 숫자가 없으면: package_unit 은 빈 문자열, quantity 는 X 뒤 숫자.
- "1A X4" 처럼 앰플/형태 표기가 있으면: package_unit="1A", quantity="4".
- "X4BOX" 처럼 박스 단위면: package_unit="BOX", quantity="4".
- 정제가 아닌 형태(앰플 A, 연고/튜브, 흡입제, 시럽 등)는 형태에 맞게 적되, 애매하면
  package_unit 은 X 앞 숫자만(또는 빈 문자열) 두세요. 사용자가 검수에서 고칩니다.

주의:
- 함량/규격(500g 등)은 절대 package_unit 에 넣지 마세요. 그건 약품명의 일부입니다.
- 적힌 순서대로 행을 유지하세요. 왼쪽 열을 모두 적은 뒤 오른쪽 열을 적으세요.
- 판독이 불확실해도 가장 가능성 높은 값을 적되, 전혀 못 읽으면 빈 문자열로 두세요.
- 없는 품목을 지어내지 마세요. 머리글/날짜/메모 등 주문 품목이 아닌 줄은 제외하세요.

예시:
- "레복사신 500mg   30X2"   → drug_name="레복사신 500mg", package_unit="30정", quantity="2"
- "리포덱스 600mg   100X3"  → drug_name="리포덱스 600mg", package_unit="100정", quantity="3"
- "아트로벤트   X15"        → drug_name="아트로벤트", package_unit="", quantity="15"
"""


class OcrConfigError(RuntimeError):
    """API 키 미설정 등 설정 문제."""


def is_configured() -> bool:
    """GEMINI_API_KEY 가 설정되어 있는지 여부."""
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def _build_schema(types):
    """품목 객체의 배열 스키마. quantity 는 OCR 안정성을 위해 문자열로 둔다."""
    return types.Schema(
        type=types.Type.ARRAY,
        items=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "drug_name": types.Schema(type=types.Type.STRING),
                "package_unit": types.Schema(type=types.Type.STRING),
                "quantity": types.Schema(type=types.Type.STRING),
                "crossed_out": types.Schema(type=types.Type.BOOLEAN),
            },
            required=["drug_name", "package_unit", "quantity"],
        ),
    )


def extract_order_items(image_bytes: bytes, mime_type: str) -> list[dict]:
    """주문지 이미지에서 [{drug_name, package_unit, quantity}, ...] 추출.

    Raises:
        OcrConfigError: API 키가 설정되지 않은 경우.
        RuntimeError: SDK 미설치 또는 호출/파싱 실패.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise OcrConfigError(
            "GEMINI_API_KEY 가 설정되지 않았습니다. .env 파일에 키를 입력해주세요. "
            "(.env.example 참고)"
        )

    # SDK 는 지연 임포트 — 미설치 시에도 앱의 나머지 기능은 동작하도록.
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise RuntimeError(
            "google-genai 패키지가 설치되지 않았습니다. "
            "`uv pip install -r requirements.txt` 를 실행해주세요."
        ) from e

    model = os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    client = genai.Client(api_key=api_key)

    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                _PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_build_schema(types),
                temperature=0,
            ),
        )
    except Exception as e:
        raise RuntimeError(f"Gemini 호출 실패: {e}") from e

    raw = (response.text or "").strip()
    if not raw:
        raise RuntimeError("Gemini 응답이 비어 있습니다.")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"응답 JSON 파싱 실패: {e}") from e

    if not isinstance(data, list):
        raise RuntimeError("응답 형식이 배열이 아닙니다.")

    # 필드 정규화 — 누락 키 방어 및 공백 정리
    items = []
    for row in data:
        if not isinstance(row, dict):
            continue
        items.append({
            "drug_name": str(row.get("drug_name", "")).strip(),
            "package_unit": str(row.get("package_unit", "")).strip(),
            "quantity": str(row.get("quantity", "")).strip(),
            "crossed_out": bool(row.get("crossed_out", False)),
        })
    return items
