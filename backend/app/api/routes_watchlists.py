"""관심종목(Watchlist) CRUD API (10번 5-t절 / 07번 13절).

엔드포인트:
    POST   /api/watchlists                     — 관심종목 그룹 생성
    GET    /api/watchlists                     — 내 관심종목 그룹 목록
    GET    /api/watchlists/{id}               — 그룹 상세 + 종목 목록
    POST   /api/watchlists/{id}/symbols       — 종목 추가
    DELETE /api/watchlists/{id}/symbols/{sym} — 종목 제거
    DELETE /api/watchlists/{id}               — 그룹 삭제

user_id scope (10.9):
    모든 엔드포인트는 Depends(get_current_user_id) 적용.
    다른 user 소유의 watchlist 접근 → 404 WATCHLIST_NOT_FOUND
    (존재 여부를 노출하지 않음으로써 정보 유출 방지).

에러 코드 (10번 7.1 카탈로그):
    WATCHLIST_NOT_FOUND (404)
    WATCHLIST_ITEM_ALREADY_EXISTS (409)
    INVALID_PARAMETER_VALUE (400)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user_id, get_db_session
from app.core.exceptions import WatchlistItemAlreadyExistsError, WatchlistNotFoundError
from app.models.watchlist import Watchlist, WatchlistItem
from app.schemas.watchlist import (
    SymbolAddRequest,
    WatchlistCreate,
    WatchlistDetailOut,
    WatchlistItemOut,
    WatchlistOut,
)

router = APIRouter(prefix="/api/watchlists", tags=["watchlist"])


def _get_watchlist_or_404(
    watchlist_id: int,
    user_id: int,
    session: Session,
) -> Watchlist:
    """user_id scope 검증 포함 조회. 없거나 다른 user 소유면 404."""
    wl = session.get(Watchlist, watchlist_id)
    if wl is None or wl.user_id != user_id:
        raise WatchlistNotFoundError(
            f"관심종목 그룹 {watchlist_id}를 찾을 수 없습니다.",
            details=[{"field": "watchlist_id", "message": str(watchlist_id)}],
        )
    return wl


def _wl_to_out(wl: Watchlist) -> WatchlistOut:
    return WatchlistOut(
        id=wl.id,
        user_id=wl.user_id,
        name=wl.name,
        description=wl.description,
        created_at=wl.created_at,
        updated_at=wl.updated_at,
        item_count=len(wl.items),
    )


def _item_to_out(item: WatchlistItem) -> WatchlistItemOut:
    return WatchlistItemOut(
        id=item.id,
        watchlist_id=item.watchlist_id,
        symbol=item.symbol,
        added_at=item.added_at,
    )


# ── POST /api/watchlists ──────────────────────────────────────────

@router.post("", response_model=WatchlistOut, status_code=201, summary="관심종목 그룹 생성")
def create_watchlist(
    body: WatchlistCreate,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
):
    """관심종목 그룹을 생성합니다.

    user_id scope: 생성 주체(get_current_user_id)를 자동으로 저장합니다.
    """
    wl = Watchlist(
        user_id=user_id,
        name=body.name,
        description=body.description,
    )
    session.add(wl)
    session.flush()
    session.refresh(wl)
    return _wl_to_out(wl)


# ── GET /api/watchlists ───────────────────────────────────────────

@router.get("", response_model=list[WatchlistOut], summary="관심종목 그룹 목록")
def list_watchlists(
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
):
    """내 관심종목 그룹 목록을 반환합니다.

    user_id scope: 본인 소유 그룹만 반환 (created_at DESC 정렬).
    """
    rows = (
        session.query(Watchlist)
        .filter(Watchlist.user_id == user_id)
        .order_by(Watchlist.created_at.desc())
        .all()
    )
    return [_wl_to_out(wl) for wl in rows]


# ── GET /api/watchlists/{id} ──────────────────────────────────────

@router.get("/{watchlist_id}", response_model=WatchlistDetailOut, summary="관심종목 그룹 상세")
def get_watchlist(
    watchlist_id: int,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
):
    """그룹 상세 정보와 종목 목록을 반환합니다.

    user_id scope: 다른 user 소유 → 404 WATCHLIST_NOT_FOUND.
    """
    wl = _get_watchlist_or_404(watchlist_id, user_id, session)
    return WatchlistDetailOut(
        id=wl.id,
        user_id=wl.user_id,
        name=wl.name,
        description=wl.description,
        created_at=wl.created_at,
        updated_at=wl.updated_at,
        items=[_item_to_out(it) for it in wl.items],
    )


# ── POST /api/watchlists/{id}/symbols ────────────────────────────

@router.post(
    "/{watchlist_id}/symbols",
    response_model=WatchlistItemOut,
    status_code=201,
    summary="관심종목 그룹에 종목 추가",
)
def add_symbol(
    watchlist_id: int,
    body: SymbolAddRequest,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
):
    """관심종목 그룹에 종목을 추가합니다.

    user_id scope: 다른 user 소유 → 404.
    중복 추가 → 409 WATCHLIST_ITEM_ALREADY_EXISTS.
    (symbols 테이블 존재 여부는 검증하지 않음 — 삭제된 종목도 추적 가능하도록)
    """
    wl = _get_watchlist_or_404(watchlist_id, user_id, session)

    # 중복 확인
    existing = (
        session.query(WatchlistItem)
        .filter(
            WatchlistItem.watchlist_id == wl.id,
            WatchlistItem.symbol == body.symbol,
        )
        .first()
    )
    if existing is not None:
        raise WatchlistItemAlreadyExistsError(
            f"종목 {body.symbol!r}은 이미 관심종목 그룹 {watchlist_id}에 추가되어 있습니다.",
            details=[
                {"field": "symbol", "message": body.symbol},
                {"field": "watchlist_id", "message": str(watchlist_id)},
            ],
        )

    item = WatchlistItem(watchlist_id=wl.id, symbol=body.symbol)
    session.add(item)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise WatchlistItemAlreadyExistsError(
            f"종목 {body.symbol!r}은 이미 관심종목 그룹 {watchlist_id}에 추가되어 있습니다.",
            details=[{"field": "symbol", "message": body.symbol}],
        ) from exc
    session.refresh(item)
    return _item_to_out(item)


# ── DELETE /api/watchlists/{id}/symbols/{symbol} ─────────────────

@router.delete(
    "/{watchlist_id}/symbols/{symbol}",
    status_code=204,
    summary="관심종목 그룹에서 종목 제거",
)
def remove_symbol(
    watchlist_id: int,
    symbol: str,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
):
    """관심종목 그룹에서 종목을 제거합니다.

    user_id scope: 다른 user 소유 → 404.
    종목이 없어도 204 반환 (idempotent).
    """
    wl = _get_watchlist_or_404(watchlist_id, user_id, session)

    item = (
        session.query(WatchlistItem)
        .filter(
            WatchlistItem.watchlist_id == wl.id,
            WatchlistItem.symbol == symbol,
        )
        .first()
    )
    if item is not None:
        session.delete(item)

    return Response(status_code=204)


# ── DELETE /api/watchlists/{id} ───────────────────────────────────

@router.delete(
    "/{watchlist_id}",
    status_code=204,
    summary="관심종목 그룹 삭제",
)
def delete_watchlist(
    watchlist_id: int,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
):
    """관심종목 그룹을 삭제합니다 (cascade로 items도 삭제).

    user_id scope: 다른 user 소유 → 404.
    """
    wl = _get_watchlist_or_404(watchlist_id, user_id, session)
    session.delete(wl)
    return Response(status_code=204)
