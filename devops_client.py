"""Azure DevOps REST access.

All calls authenticate with a Personal Access Token read from the environment.
Import is free of side effects: nothing here talks to the network until a
function is called.
"""

import base64
import os
from functools import lru_cache

import requests
from dotenv import load_dotenv

load_dotenv()

API_VERSION = "7.1"
# The comments endpoint is still preview in 7.1.
COMMENTS_API_VERSION = "7.1-preview.4"

# Max ids the work item batch endpoint accepts in one call.
BATCH_LIMIT = 200

TIMEOUT = 30


class DevOpsError(RuntimeError):
    """An Azure DevOps REST call failed."""


@lru_cache(maxsize=1)
def _config():
    org = os.getenv("AZURE_DEVOPS_ORG")
    project = os.getenv("AZURE_DEVOPS_PROJECT")
    pat = os.getenv("AZURE_DEVOPS_PAT")
    base = os.getenv("AZURE_DEVOPS_API_BASE_URL", "https://dev.azure.com").rstrip("/")

    missing = [
        name
        for name, value in (
            ("AZURE_DEVOPS_ORG", org),
            ("AZURE_DEVOPS_PROJECT", project),
            ("AZURE_DEVOPS_PAT", pat),
        )
        if not value
    ]
    if missing:
        raise DevOpsError(f"Missing environment variables: {', '.join(missing)}")

    return org, project, pat, _host_root(base, org, project)


def _host_root(base, org, project):
    """Reduce a base URL to the host root.

    `.env` may hold either the host (`https://dev.azure.com`) or the full
    project API root (`https://dev.azure.com/<org>/<project>/_apis`). Accept
    both so URL building stays in one place.
    """
    for suffix in (f"/{org}/{project}/_apis", f"/{org}/_apis", f"/{org}"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def project_url(path):
    """Build a project-scoped API URL. `path` is everything after `_apis/`."""
    org, project, _, base = _config()
    return f"{base}/{org}/{project}/_apis/{path.lstrip('/')}"


def org_url(path):
    """Build an organization-scoped API URL."""
    org, _, _, base = _config()
    return f"{base}/{org}/_apis/{path.lstrip('/')}"


def _headers(content_type=None):
    _, _, pat, _ = _config()
    token = base64.b64encode(f":{pat}".encode()).decode()
    headers = {"Authorization": f"Basic {token}", "Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _request(method, url, params=None, json_body=None, content_type=None):
    try:
        response = requests.request(
            method,
            url,
            headers=_headers(content_type),
            params=params,
            json=json_body,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise DevOpsError(f"{method} {url} failed: {type(exc).__name__}") from exc

    if not response.ok:
        raise DevOpsError(
            f"{method} {url} returned {response.status_code}: {response.text[:300]}"
        )

    return response.json()


def _get(url, **params):
    params.setdefault("api-version", API_VERSION)
    return _request("GET", url, params=params)


def _post(url, body, **params):
    params.setdefault("api-version", API_VERSION)
    return _request(
        "POST", url, params=params, json_body=body, content_type="application/json"
    )


def get_project_id():
    """The project GUID. The wiki API needs this, the project name will not do."""
    _, project, _, _ = _config()
    return _get(org_url(f"projects/{project}"))["id"]


def list_work_item_ids():
    """Every work item id in the project, ascending."""
    query = (
        "SELECT [System.Id] FROM WorkItems "
        "WHERE [System.TeamProject] = @project "
        "ORDER BY [System.Id] ASC"
    )
    result = _post(project_url("wit/wiql"), {"query": query})
    return [item["id"] for item in result.get("workItems", [])]


WORK_ITEM_FIELDS = [
    "System.Id",
    "System.Title",
    "System.Description",
    "System.State",
    "System.WorkItemType",
    "System.CreatedDate",
    "System.ChangedDate",
]


def get_work_items(ids, fields=None):
    """Fetch work items by id, batched to the endpoint's 200-id limit."""
    fields = fields or WORK_ITEM_FIELDS
    items = []
    for start in range(0, len(ids), BATCH_LIMIT):
        batch = ids[start : start + BATCH_LIMIT]
        if not batch:
            continue
        result = _post(
            project_url("wit/workitemsbatch"), {"ids": batch, "fields": fields}
        )
        items.extend(result.get("value", []))
    return items


def get_comments(work_item_id):
    """Comment text for one work item, oldest first."""
    url = project_url(f"wit/workItems/{work_item_id}/comments")
    result = _get(url, **{"api-version": COMMENTS_API_VERSION})
    return [c.get("text", "") for c in result.get("comments", []) if c.get("text")]


def get_wiki_name():
    """Name of the project wiki. Raises if the project has no wiki."""
    wikis = _get(project_url("wiki/wikis")).get("value", [])
    if not wikis:
        raise DevOpsError("Project has no wiki")
    return wikis[0]["name"]


def list_wiki_page_paths(wiki_name):
    """Every page path in the wiki, root first, depth-first."""
    root = _get(
        project_url(f"wiki/wikis/{wiki_name}/pages"),
        path="/",
        recursionLevel="full",
    )

    paths = []

    def walk(page):
        path = page.get("path")
        # The root page has no content of its own worth indexing.
        if path and path != "/":
            paths.append(path)
        for sub in page.get("subPages") or []:
            walk(sub)

    walk(root)
    return paths


def get_wiki_page(wiki_name, path):
    """One wiki page with its markdown content."""
    return _get(
        project_url(f"wiki/wikis/{wiki_name}/pages"),
        path=path,
        includeContent="true",
    )
