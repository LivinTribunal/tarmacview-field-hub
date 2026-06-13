"""wayline module - the route library pilot 2 syncs its route list from."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_pilot_token
from app.models.wayline import Wayline
from app.schemas.envelope import HttpResultResponse, error, ok
from app.schemas.manage import PaginationData
from app.schemas.wayline import FavoritesRequest, WaylineListData, WaylineListItem
from app.services import object_store, wayline_library

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wayline/api/v1", tags=["wayline"])

DEFAULT_PAGE_SIZE = 10


def _millis(value: datetime) -> int:
    """epoch milliseconds - the demo's wire format for create/update times.

    sqlite loses tzinfo on round-trip, so naive values are read back as utc.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1000)


def _expand_keys(values: list[str] | None) -> list[str] | None:
    """accept both repeated params and comma-separated lists for model keys."""
    if not values:
        return None
    expanded = [part.strip() for value in values for part in value.split(",") if part.strip()]
    return expanded or None


def _list_item(wayline: Wayline) -> WaylineListItem:
    """wayline payload from an orm row."""
    return WaylineListItem(
        id=wayline.id,
        name=wayline.name,
        drone_model_key=wayline.drone_model_key,
        payload_model_keys=wayline.payload_model_keys or [],
        template_types=wayline.template_types or [],
        object_key=wayline.object_key,
        sign=wayline.sign,
        favorited=wayline.favorited,
        username=wayline.username,
        create_time=_millis(wayline.create_time),
        update_time=_millis(wayline.update_time),
    )


@router.get("/workspaces/{workspace_id}/waylines")
def list_waylines(
    workspace_id: str,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    key: str | None = None,
    favorited: bool | None = None,
    drone_model_keys: list[str] | None = Query(default=None),
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """paged route list - pilot filters by the connected aircraft's model key."""
    waylines, total = wayline_library.list_waylines(
        db,
        page=page,
        page_size=page_size,
        key=key,
        drone_model_keys=_expand_keys(drone_model_keys),
        favorited=favorited,
    )
    return ok(
        WaylineListData(
            list=[_list_item(w) for w in waylines],
            pagination=PaginationData(page=page, page_size=page_size, total=total),
        )
    )


@router.get("/workspaces/{workspace_id}/waylines/duplicate-names")
def duplicate_names(
    workspace_id: str,
    name: list[str] | None = Query(default=None),
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """name-collision check - returns the subset of names already in the library."""
    return ok(wayline_library.duplicate_names(db, name or []))


@router.get("/workspaces/{workspace_id}/waylines/{wayline_id}/url")
def wayline_download_url(
    workspace_id: str,
    wayline_id: str,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
):
    """redirect to a presigned kmz download on the lan-reachable object store."""
    wayline = wayline_library.get_wayline(db, wayline_id)
    if wayline is None:
        return error("wayline not found")
    return RedirectResponse(url=object_store.presigned_get_url(wayline.object_key))


@router.post("/workspaces/{workspace_id}/favorites")
def add_favorites(
    workspace_id: str,
    body: FavoritesRequest,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """mark waylines as favorites."""
    wayline_library.set_favorited(db, body.ids, True)
    db.commit()
    return ok()


@router.delete("/workspaces/{workspace_id}/favorites")
def remove_favorites(
    workspace_id: str,
    body: FavoritesRequest,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """unmark waylines as favorites."""
    wayline_library.set_favorited(db, body.ids, False)
    db.commit()
    return ok()


@router.delete("/workspaces/{workspace_id}/waylines/{wayline_id}")
def delete_wayline(
    workspace_id: str,
    wayline_id: str,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """remove a wayline and its stored kmz."""
    wayline = wayline_library.delete_wayline(db, wayline_id)
    if wayline is None:
        return error("wayline not found")
    object_key = wayline.object_key
    db.commit()

    # best effort - a stranded object must not fail the library delete
    try:
        object_store.remove_object(object_key)
    except Exception:
        logger.warning("wayline object cleanup failed for %s", object_key, exc_info=True)
    return ok()
