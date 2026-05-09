"""Strategy CRUD API (10번 문서 2절)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user_id, get_db_session
from app.core.exceptions import StrategyNotFoundError
from app.schemas.strategy import StrategyCreate, StrategyOut, StrategyUpdate
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
):
    try:
        return strategy_service.get_strategy(session, strategy_id)
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.to_dict()["error"]) from exc


@router.put("/{strategy_id}", response_model=StrategyOut, summary="전략 수정")
def update_strategy(
    strategy_id: int,
    payload: StrategyUpdate,
    session: Session = Depends(get_db_session),
):
    try:
        return strategy_service.update_strategy(
            session,
            strategy_id,
            strategy_json=payload.strategy_json,
            name=payload.name,
            description=payload.description,
            tags=payload.tags,
            favorite=payload.favorite,
            change_note=payload.change_note,
        )
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.to_dict()["error"]) from exc


@router.delete(
    "/{strategy_id}",
    response_model=StrategyOut,
    summary="전략 soft delete",
)
def delete_strategy(
    strategy_id: int,
    session: Session = Depends(get_db_session),
):
    try:
        return strategy_service.soft_delete_strategy(session, strategy_id)
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.to_dict()["error"]) from exc


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
):
    try:
        return strategy_service.duplicate_strategy(session, strategy_id, new_name=new_name)
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.to_dict()["error"]) from exc
