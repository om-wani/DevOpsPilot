import pytest
import requests

import auth


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content_type="application/json", text=""):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self._payload = payload
        self.text = text

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


PROFILE = {"id": "user-123", "displayName": "Om Wani"}


@pytest.fixture(autouse=True)
def clear():
    auth.clear_cache()
    yield
    auth.clear_cache()


def test_valid_token_returns_identity(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload=PROFILE))
    assert auth.verify_token("good") == {"id": "user-123", "name": "Om Wani"}


def test_signin_page_is_rejected_not_parsed(monkeypatch):
    # Azure DevOps answers a bad token with 203 and an HTML sign-in page, which
    # passes `response.ok`. It must be rejected, not parsed.
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: FakeResponse(status_code=203, content_type="text/html", text="<html>"),
    )
    with pytest.raises(auth.AuthError):
        auth.verify_token("stale")


def test_json_content_type_but_unparseable_is_rejected(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload=None))
    with pytest.raises(auth.AuthError):
        auth.verify_token("weird")


def test_401_is_rejected(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(status_code=401))
    with pytest.raises(auth.AuthError):
        auth.verify_token("expired")


def test_profile_without_id_is_rejected(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload={"displayName": "x"}))
    with pytest.raises(auth.AuthError):
        auth.verify_token("odd")


def test_network_failure_does_not_leak_transport_detail(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("dns exploded at 10.0.0.1")

    monkeypatch.setattr(requests, "get", boom)
    with pytest.raises(auth.AuthError) as exc:
        auth.verify_token("good")
    assert "10.0.0.1" not in str(exc.value)


def test_empty_token_never_reaches_the_network(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("should not call"))
    for value in ("", "   ", None):
        with pytest.raises(auth.AuthError):
            auth.verify_token(value)


def test_second_call_is_served_from_cache(monkeypatch):
    calls = []

    def counted(*a, **k):
        calls.append(1)
        return FakeResponse(payload=PROFILE)

    monkeypatch.setattr(requests, "get", counted)

    auth.verify_token("good")
    auth.verify_token("good")

    assert len(calls) == 1


def test_expired_cache_entry_revalidates(monkeypatch):
    calls = []

    def counted(*a, **k):
        calls.append(1)
        return FakeResponse(payload=PROFILE)

    monkeypatch.setattr(requests, "get", counted)
    monkeypatch.setattr(auth, "CACHE_TTL_SECONDS", -1)

    auth.verify_token("good")
    auth.verify_token("good")

    assert len(calls) == 2


def test_raw_token_is_not_used_as_a_cache_key(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload=PROFILE))
    auth.verify_token("secret-token")
    assert "secret-token" not in auth._cache


def test_bearer_header_parsing():
    assert auth.bearer_token("Bearer abc123") == "abc123"
    assert auth.bearer_token("bearer abc123") == "abc123"


@pytest.mark.parametrize("header", ["", None, "abc123", "Basic abc123", "Bearer", "Bearer   "])
def test_bad_authorization_headers_rejected(header):
    with pytest.raises(auth.AuthError):
        auth.bearer_token(header)
