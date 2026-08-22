"""API surface: verified-principal identity, fail-closed S2S, security headers.

The client comes from the shared ``api_client`` fixture, which pins a loopback peer: the
app-object exposure guard refuses the unauthenticated local posture to any other peer, and
TestClient's default peer is the literal host "testclient".
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from account_takeover_investigator.domain.investigation_service import InvestigationService

_TOKEN_ENV = "ATOINVEST_S2S_TOKEN"


def _body(subject_id: str = "acct-takeover", session_id: str = "sess-1") -> dict[str, str]:
    return {"subject_id": subject_id, "session_id": session_id}


def test_investigate_uses_the_verified_principal_as_actor(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/investigate",
        json=_body(),
        headers={"X-Dev-Persona": "auditor"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["band"] == "critical"
    assert body["requires_human_review"] is True
    # Rule R8: the escalation was routed, not merely flagged (see test_review_routing.py).
    assert body["review_ref"]
    assert body["signals"], "a takeover result must expose its per-signal uplift lines"


def test_the_request_schema_offers_no_identity_field(api_client: TestClient) -> None:
    """No route may ADVERTISE a field that names who the caller is or which tenant they act for.

    Ignoring such a field server-side is not enough. A published schema is a claim about what the
    service accepts, and a tenant field on an investigate request tells every reader that
    asserting one is a supported thing to do. The identity comes from the verified principal, so
    the field has no reason to exist and is absent rather than tolerated.
    """
    schema = api_client.get("/openapi.json").json()
    properties = schema["components"]["schemas"]["InvestigateRequest"]["properties"]
    forbidden = {"tenant", "actor", "principal", "maker", "roles", "groups"}
    offered = sorted(forbidden & set(properties))
    assert not offered, f"the request schema advertises client-asserted identity: {offered}"


def test_an_asserted_tenant_cannot_displace_the_verified_principal(
    api_client: TestClient,
) -> None:
    """A tenant in the body must not reach the service; the principal's tenant must.

    The service was given ``request.tenant or principal.tenant``, so any non-empty string the
    caller wrote WON over the identity the adapter verified, and the request still answered 200.
    """
    seen: list[tuple[object, str]] = []
    original = InvestigationService.investigate

    def _tap(self: InvestigationService, request: object, *, actor: str) -> object:
        seen.append((request, actor))
        return original(self, request, actor=actor)  # type: ignore[arg-type]

    InvestigationService.investigate = _tap  # type: ignore[method-assign,assignment]
    try:
        resp = api_client.post(
            "/v1/investigate",
            json={**_body("acct-quiet"), "tenant": "acme-rival-bank"},
            headers={"X-Dev-Persona": "auditor"},
        )
    finally:
        InvestigationService.investigate = original  # type: ignore[method-assign]

    assert resp.status_code == 200
    assert seen, "the route must have reached the service"
    request, actor = seen[-1]
    assert actor == "demo.auditor@bank.example"
    assert request.tenant == "demo-bank", (  # type: ignore[attr-defined]
        f"the asserted tenant displaced the verified principal's: {request.tenant!r}"  # type: ignore[attr-defined]
    )


def test_a_quiet_session_is_not_escalated(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/investigate",
        json=_body("acct-quiet"),
        headers={"X-Dev-Persona": "auditor"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["band"] == "low"
    assert body["requires_human_review"] is False
    assert body["review_ref"] == ""


def test_unknown_persona_is_401(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/investigate",
        json=_body("acct-quiet"),
        headers={"X-Dev-Persona": "ghost"},
    )
    assert resp.status_code == 401


def test_healthz_reports_profile_and_region(api_client: TestClient) -> None:
    body = api_client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["profile"] == "local"
    assert body["region"] == "asia-southeast1"


def test_security_headers_present(api_client: TestClient) -> None:
    headers = api_client.get("/healthz").headers
    assert headers["Content-Security-Policy"] == "frame-ancestors 'self'"
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.fixture()
def token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv(_TOKEN_ENV, "s3cret-service-token")
    yield "s3cret-service-token"


def test_s2s_endpoint_open_when_secret_unset(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_TOKEN_ENV, raising=False)
    assert api_client.post("/v1/audit/ping").status_code == 200


def test_s2s_endpoint_rejects_missing_token_when_enforced(
    api_client: TestClient, token_env: str
) -> None:
    assert api_client.post("/v1/audit/ping").status_code == 401


def test_s2s_endpoint_accepts_correct_token(api_client: TestClient, token_env: str) -> None:
    resp = api_client.post("/v1/audit/ping", headers={"Authorization": f"Bearer {token_env}"})
    assert resp.status_code == 200
