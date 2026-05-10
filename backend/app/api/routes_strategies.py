"""Strategy CRUD API (10번 문서 2절).

모든 단일 자원 엔드포인트(get/update/delete/duplicate)는 user_id 스코프를
강제한다 (10번 9절). 한 줄의 누락이 데이터 격리를 깨뜨리므로 라우트 6개
(list/create/get/update/delete/duplicate) 모두 `Depends(get_current_user_id)`를
받고, 서비스 레이어에 user_id를 전달한다. 미소유 자원은 STRATEGY_NOT_FOUND
(404) — 존재 여부조차 노출하지 않아 enumeration을 방지한다.

에러 응답은 errors.py의 exception_handler가 표준 envelope으로 변환한다.
직접 HTTPException을 던지지 말고 AppError(또는 하위 클래스)를 raise.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user_id, get_db_session
from app.schemas.strategy import StrategyCreate, StrategyOut, StrategyUpdate, StrategyVersionOut
from app.services import strategy_service

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyOut], summary="전략 목록")
def list_strategies(
    include_deleted: bool = False,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    return strategy_service.list_strategies(
        session, user_id=user_id, include_deleted=include_deleted
    )


@router.post(
    "",
    response_model=StrategyOut,
    status_code=status.HTTP_201_CREATED,
    summary="전략 생성",
)
def create_strategy(
    payload: StrategyCreate,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    return strategy_service.create_strategy(
        session,
        user_id=user_id,
        name=payload.name,
        strategy_json=payload.strategy_json,
        description=payload.description,
        tags=payload.tags,
        favorite=payload.favorite,
    )


@router.get("/{strategy_id}", response_model=StrategyOut, summary="전략 상세")
def get_strategy(
    strategy_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    return strategy_service.get_strategy(session, strategy_id, user_id=user_id)


@router.put("/{strategy_id}", response_model=StrategyOut, summary="전략 수정")
def update_strategy(
    strategy_id: int,
    payload: StrategyUpdate,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    return strategy_service.update_strategy(
        session,
        strategy_id,
        user_id=user_id,
        strategy_json=payload.strategy_json,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        favorite=payload.favorite,
        change_note=payload.change_note,
    )


@router.delete(
    "/{strategy_id}",
    response_model=StrategyOut,
    summary="전략 soft delete",
)
def delete_strategy(
    strategy_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    return strategy_service.soft_delete_strategy(session, strategy_id, user_id=user_id)


@router.post(
    "/{strategy_id}/duplicate",
    response_model=StrategyOut,
    status_code=status.HTTP_201_CREATED,
    summary="전략 복사",
)
def duplicate_strategy(
    strategy_id: int,
    new_name: str,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    return strategy_service.duplicate_strategy(
        session, strategy_id, user_id=user_id, new_name=new_name
    )


@router.get(
    "/{strategy_id}/versions",
    response_model=list[StrategyVersionOut],
    summary="전략 버전 이력 (10-m)",
)
def list_strategy_versions(
    strategy_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    """GET /api/strategies/{strategy_id}/versions.

    전략 버전 이력 목록을 version 오름차순으로 반환한다.
    삭제된 전략도 버전 이력은 조회 가능 (allow_deleted=True).
    user_id 스코프 강제: 본인 소유 전략만 (10번 9절).
    존재하지 않거나 미소유 → STRATEGY_NOT_FOUND (404).
    """
    versions = strategy_service.list_strategy_versions(
        session, strategy_id, user_id=user_id
    )
    return [StrategyVersionOut.from_orm_version(v) for v in versions]
