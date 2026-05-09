"""GET /api/conditions — 조건 카탈로그 (10번 문서 3절).

프론트엔드 BlockPalette / ConditionEditorPanel이 이 응답을 보고
입력 폼과 블록 목록을 자동 생성한다 (메타데이터 기반 자동화).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.strategy.condition_definitions import get_condition_catalog

router = APIRouter(prefix="/api/conditions", tags=["conditions"])


@router.get("", summary="조건 카탈로그", response_model=list[dict])
def list_conditions() -> list[dict]:
    """등록된 모든 조건의 메타데이터.

    각 항목 키:
        type, requires_position, category,
        name, description, sentence_template, parameters, allowed_in
    """
    return get_condition_catalog()
