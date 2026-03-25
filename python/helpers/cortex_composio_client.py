import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ComposioApp:
    name: str = ""
    key: str = ""
    description: str = ""
    categories: list = field(default_factory=list)


@dataclass
class ComposioAction:
    name: str = ""
    app_name: str = ""
    display_name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=dict)


@dataclass
class ComposioResult:
    success: bool = False
    data: dict = field(default_factory=dict)
    error: str = ""
    execution_id: str = ""


@dataclass
class ComposioConnection:
    id: str = ""
    app_name: str = ""
    entity_id: str = ""
    status: str = ""
    created_at: str = ""


class CortexComposioClient:

    BASE_URL = "https://backend.composio.dev/api/v1"

    def __init__(self, api_key: str = "", entity_id: str = "default"):
        self.api_key = api_key
        self.entity_id = entity_id
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    async def list_apps(self, category: Optional[str] = None) -> list:
        if not self.is_configured():
            return []
        client = await self._get_client()
        params = {}
        if category:
            params["category"] = category
        resp = await client.get(
            f"{self.BASE_URL}/apps",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        results = []
        for item in items:
            results.append(ComposioApp(
                name=item.get("name", ""),
                key=item.get("key", ""),
                description=item.get("description", ""),
                categories=item.get("categories", []),
            ))
        return results

    async def list_actions(
        self,
        app_name: str,
        limit: int = 20,
        use_case: Optional[str] = None,
    ) -> list:
        if not self.is_configured():
            return []
        client = await self._get_client()
        params = {"apps": app_name, "limit": limit}
        if use_case:
            params["useCase"] = use_case
        resp = await client.get(
            f"{self.BASE_URL}/actions",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        results = []
        for item in items:
            results.append(ComposioAction(
                name=item.get("name", ""),
                app_name=item.get("appName", app_name),
                display_name=item.get("displayName", ""),
                description=item.get("description", ""),
                parameters=item.get("parameters", {}),
            ))
        return results

    async def execute(
        self,
        action_name: str,
        params: dict,
        entity_id: Optional[str] = None,
    ) -> ComposioResult:
        if not self.is_configured():
            return ComposioResult(success=False, error="Composio API key not configured")
        client = await self._get_client()
        payload = {
            "input": params,
            "entityId": entity_id or self.entity_id,
        }
        resp = await client.post(
            f"{self.BASE_URL}/actions/execute/{action_name}",
            headers=self._headers(),
            json=payload,
            timeout=60.0,
        )
        if resp.status_code >= 400:
            try:
                err = resp.json()
            except Exception:
                err = {"message": resp.text}
            return ComposioResult(
                success=False,
                error=err.get("message", str(resp.status_code)),
            )
        data = resp.json()
        return ComposioResult(
            success=data.get("successfull", data.get("success", True)),
            data=data.get("response", data.get("data", data)),
            execution_id=data.get("execution_id", ""),
        )

    async def get_connected_accounts(
        self,
        app_name: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> list:
        if not self.is_configured():
            return []
        client = await self._get_client()
        params = {"entityId": entity_id or self.entity_id}
        if app_name:
            params["appName"] = app_name
        resp = await client.get(
            f"{self.BASE_URL}/connectedAccounts",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        results = []
        for item in items:
            results.append(ComposioConnection(
                id=item.get("id", ""),
                app_name=item.get("appName", ""),
                entity_id=item.get("entityId", ""),
                status=item.get("status", ""),
                created_at=item.get("createdAt", ""),
            ))
        return results

    async def is_app_connected(
        self, app_name: str, entity_id: Optional[str] = None
    ) -> bool:
        try:
            accounts = await self.get_connected_accounts(
                app_name=app_name, entity_id=entity_id
            )
            return any(a.status == "ACTIVE" for a in accounts)
        except Exception:
            return False

    async def initiate_connection(
        self,
        app_name: str,
        redirect_url: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> dict:
        if not self.is_configured():
            return {}
        client = await self._get_client()
        payload = {
            "appName": app_name,
            "entityId": entity_id or self.entity_id,
        }
        if redirect_url:
            payload["redirectUri"] = redirect_url
        resp = await client.post(
            f"{self.BASE_URL}/connectedAccounts",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def session_for_venture(self, venture_name: str) -> "CortexComposioClient":
        return CortexComposioClient(
            api_key=self.api_key,
            entity_id=venture_name,
        )

    @staticmethod
    def from_agent_config(agent) -> "CortexComposioClient":
        api_key = (
            getattr(agent.config, "cortex_composio_api_key", "")
            or os.getenv("COMPOSIO_API_KEY", "")
        )
        entity_id = (
            getattr(agent.config, "cortex_composio_entity_id", "")
            or "cortex_default"
        )
        return CortexComposioClient(api_key=api_key, entity_id=entity_id)
