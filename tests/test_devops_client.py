import pytest

import devops_client as dc


def configure(monkeypatch, base):
    monkeypatch.setenv("AZURE_DEVOPS_ORG", "acme")
    monkeypatch.setenv("AZURE_DEVOPS_PROJECT", "widgets")
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "token")
    monkeypatch.setenv("AZURE_DEVOPS_API_BASE_URL", base)
    dc._config.cache_clear()


def test_host_root_base_builds_project_url(monkeypatch):
    configure(monkeypatch, "https://dev.azure.com")
    assert dc.project_url("wit/wiql") == "https://dev.azure.com/acme/widgets/_apis/wit/wiql"


def test_full_project_api_base_is_not_doubled(monkeypatch):
    configure(monkeypatch, "https://dev.azure.com/acme/widgets/_apis")
    assert dc.project_url("wit/wiql") == "https://dev.azure.com/acme/widgets/_apis/wit/wiql"


def test_org_scoped_url(monkeypatch):
    configure(monkeypatch, "https://dev.azure.com")
    assert dc.org_url("projects/widgets") == "https://dev.azure.com/acme/_apis/projects/widgets"


def test_leading_slash_in_path_is_tolerated(monkeypatch):
    configure(monkeypatch, "https://dev.azure.com/")
    assert dc.project_url("/wit/wiql") == "https://dev.azure.com/acme/widgets/_apis/wit/wiql"


def test_missing_pat_raises_config_error(monkeypatch):
    configure(monkeypatch, "https://dev.azure.com")
    monkeypatch.delenv("AZURE_DEVOPS_PAT")
    dc._config.cache_clear()
    with pytest.raises(dc.DevOpsError) as exc:
        dc.project_url("wit/wiql")
    assert "AZURE_DEVOPS_PAT" in str(exc.value)


def test_auth_header_is_basic_base64(monkeypatch):
    import base64

    configure(monkeypatch, "https://dev.azure.com")
    headers = dc._headers()
    scheme, token = headers["Authorization"].split()
    assert scheme == "Basic"
    assert base64.b64decode(token).decode() == ":token"
    assert headers["Accept"] == "application/json"


def test_batching_splits_at_the_endpoint_limit(monkeypatch):
    configure(monkeypatch, "https://dev.azure.com")
    calls = []

    def fake_post(url, body, **params):
        calls.append(body["ids"])
        return {"value": [{"id": i} for i in body["ids"]]}

    monkeypatch.setattr(dc, "_post", fake_post)

    items = dc.get_work_items(list(range(450)))

    assert [len(batch) for batch in calls] == [200, 200, 50]
    assert len(items) == 450


def test_no_batches_for_empty_id_list(monkeypatch):
    configure(monkeypatch, "https://dev.azure.com")
    monkeypatch.setattr(dc, "_post", lambda *a, **k: pytest.fail("should not call"))
    assert dc.get_work_items([]) == []

