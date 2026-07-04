"""Cliente HTTP tipado de la Graph API de Meta (WhatsApp Cloud API).

Mapea errores a GraphApiError con clasificación retryable/permanente:
- 429 / 5xx / errores de red → retryable (la cola reintenta con backoff)
- 4xx de negocio (ventana, plantilla no aprobada, token inválido) → permanente
"""

from typing import Any

import httpx

GRAPH_BASE_URL = "https://graph.facebook.com"
_TIMEOUT = httpx.Timeout(10.0, read=30.0)


class GraphApiError(Exception):
    def __init__(self, message: str, *, status: int | None = None,
                 detail: Any = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail
        self.retryable = retryable


class WhatsAppGraphClient:
    def __init__(self, *, access_token: str, phone_number_id: str,
                 api_version: str = "v21.0", base_url: str = GRAPH_BASE_URL) -> None:
        self._token = access_token
        self._phone_number_id = phone_number_id
        self._base = f"{base_url}/{api_version}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.request(method, url, headers=self._headers, **kwargs)
        except httpx.HTTPError as exc:
            raise GraphApiError(f"Error de red hacia Graph API: {exc}", retryable=True) from exc

        if resp.status_code == 429 or resp.status_code >= 500:
            raise GraphApiError(
                f"Graph API {resp.status_code}", status=resp.status_code,
                detail=_safe_json(resp), retryable=True,
            )
        if resp.status_code >= 400:
            raise GraphApiError(
                f"Graph API {resp.status_code}", status=resp.status_code,
                detail=_safe_json(resp), retryable=False,
            )
        return resp

    async def send_message(self, payload: dict) -> str:
        """Envía un mensaje; devuelve el wamid asignado por Meta."""
        resp = await self._request(
            "POST", f"{self._base}/{self._phone_number_id}/messages", json=payload
        )
        data = resp.json()
        return data["messages"][0]["id"]

    async def get_media_info(self, media_id: str) -> dict:
        """Devuelve {url, mime_type, file_size, ...}. La URL expira en ~5 min."""
        resp = await self._request("GET", f"{self._base}/{media_id}")
        return resp.json()

    async def download_media(self, url: str) -> bytes:
        resp = await self._request("GET", url)
        return resp.content

    async def check_connection(self) -> dict:
        """Health check de la cuenta (panel: 'probar conexión')."""
        resp = await self._request("GET", f"{self._base}/{self._phone_number_id}")
        return resp.json()


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text[:1000]
