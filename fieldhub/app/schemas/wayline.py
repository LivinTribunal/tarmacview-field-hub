"""wayline module dtos mirroring the demo's GetWaylineListResponse payloads."""

from pydantic import BaseModel

from app.schemas.manage import PaginationData


class WaylineListItem(BaseModel):
    """one route entry as pilot renders it in the route library."""

    id: str
    name: str
    drone_model_key: str | None = None
    payload_model_keys: list[str] = []
    template_types: list[int] = []
    object_key: str
    sign: str | None = None
    favorited: bool = False
    username: str | None = None
    create_time: int
    update_time: int


class WaylineListData(BaseModel):
    """paged wayline list."""

    list: list[WaylineListItem]
    pagination: PaginationData


class FavoritesRequest(BaseModel):
    """wayline ids to (un)mark as favorites."""

    ids: list[str] = []


class WaylineRegisterData(BaseModel):
    """internal register response - what the backend records on its side."""

    wayline_id: str
    mission_id: str
    object_key: str
