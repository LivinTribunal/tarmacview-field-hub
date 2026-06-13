"""pilot webview dtos - connect-page bootstrap config."""

from pydantic import BaseModel


class PilotConfigData(BaseModel):
    """dji app credentials + attach addresses the connect page needs before login."""

    app_id: str
    app_key: str
    app_license: str
    mqtt_addr: str
    platform_name: str
    workspace_name: str
    workspace_desc: str = ""
