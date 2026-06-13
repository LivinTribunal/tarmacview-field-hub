"""manage module dtos mirroring the demo's login/device/topology payloads."""

from pydantic import BaseModel

# pilot client flag in the demo's login request
USER_TYPE_PILOT = 2

# platform branding pilot renders for the third-party cloud service
PLATFORM_NAME = "TarmacView Field Hub"


class LoginRequest(BaseModel):
    """operator/pilot login body."""

    username: str
    password: str
    flag: int | None = None


class LoginData(BaseModel):
    """demo UserDTO - the contract that attaches pilot to the platform."""

    user_id: str
    username: str
    user_type: int = USER_TYPE_PILOT
    workspace_id: str
    access_token: str
    mqtt_addr: str
    mqtt_username: str = ""
    mqtt_password: str = ""


class WorkspaceData(BaseModel):
    """workspace of the authenticated user."""

    workspace_id: str
    workspace_name: str
    workspace_desc: str = ""
    platform_name: str = PLATFORM_NAME


class DeviceModelData(BaseModel):
    """domain-type-subtype identity of a device."""

    key: str | None = None
    domain: int | None = None
    type: int | None = None
    sub_type: int | None = None
    name: str | None = None


class DeviceData(BaseModel):
    """device entry served to pilot and the web side."""

    device_sn: str
    device_name: str
    nickname: str | None = None
    workspace_id: str
    device_model: DeviceModelData
    status: bool = False
    bound_status: bool = False
    bound_time: str | None = None
    gateway_sn: str | None = None
    domain: int | None = None


class PaginationData(BaseModel):
    """paging block on list payloads."""

    page: int
    page_size: int
    total: int


class BoundDeviceListData(BaseModel):
    """paged bound-device list."""

    list: list[DeviceData]
    pagination: PaginationData


class BindRequest(BaseModel):
    """optional binding body - everything is inferable from the path sn."""

    workspace_id: str | None = None
    nickname: str | None = None


class RenameRequest(BaseModel):
    """device rename body."""

    nickname: str | None = None
    device_name: str | None = None


class TopologyNodeData(BaseModel):
    """one device node in the tsa topology tree."""

    sn: str
    online_status: bool
    device_callsign: str | None = None
    device_model: DeviceModelData
    gateway_sn: str | None = None


class TopologyData(BaseModel):
    """gateway with its attached aircraft."""

    hosts: list[TopologyNodeData]
    parents: list[TopologyNodeData]


class TopologyListData(BaseModel):
    """device tree for pilot's situational awareness module."""

    list: list[TopologyData]
