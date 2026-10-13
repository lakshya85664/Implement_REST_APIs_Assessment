
from typing import Any

import httpx
from pydantic import ValidationError

from src.schemas import (
    OrderLookupOutput,
    OrderUpdateOutput,
)


class RestClientError(Exception):
    """Base exception for REST adapter failures."""


class RestTimeout(RestClientError):
    pass


class RestProviderError(RestClientError):
    pass


class RestNotFound(RestClientError):
    pass


class RestResponseError(RestClientError):
    pass


class RestOrderClient:
    """HTTPX adapter that translates HTTP behavior into typed results."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 0.2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            trust_env=False,
        )

    def lookup(self, order_id: str) -> dict[str, Any]:
        try:
            response = self.client.get(f"/orders/{order_id}")
        except httpx.TimeoutException as exc:
            raise RestTimeout("REST request timed out") from exc
        except httpx.HTTPError as exc:
            raise RestProviderError("REST transport failure") from exc

        if response.status_code == 404:
            raise RestNotFound("Order not found")
        if response.status_code >= 500:
            raise RestProviderError("REST provider returned an error")
        if response.status_code != 200:
            raise RestProviderError(
                f"Unexpected REST status: {response.status_code}"
            )

        try:
            payload = response.json()
            result = OrderLookupOutput.model_validate(payload)
        except (ValueError, ValidationError) as exc:
            raise RestResponseError(
                "REST response was malformed or invalid"
            ) from exc

        return result.model_dump()

    def update(
        self,
        order_id: str,
        new_status: str,
    ) -> dict[str, Any]:
        try:
            response = self.client.patch(
                f"/orders/{order_id}",
                json={"status": new_status},
            )
        except httpx.TimeoutException as exc:
            raise RestTimeout("REST request timed out") from exc
        except httpx.HTTPError as exc:
            raise RestProviderError("REST transport failure") from exc

        if response.status_code == 404:
            raise RestNotFound("Order not found")
        if response.status_code >= 500:
            raise RestProviderError("REST provider returned an error")
        if response.status_code != 200:
            raise RestProviderError(
                f"Unexpected REST status: {response.status_code}"
            )

        try:
            payload = response.json()
            result = OrderUpdateOutput.model_validate(payload)
        except (ValueError, ValidationError) as exc:
            raise RestResponseError(
                "REST response was malformed or invalid"
            ) from exc

        return result.model_dump()

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "RestOrderClient":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
