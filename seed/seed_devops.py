"""
Seeds an Azure DevOps project with sample work items and wiki pages.
Run this once against a fresh test project. Do not run it against a project
with real content, it will add data, not overwrite anything, but keep test
and real data separate.

Requires: requests, python-dotenv
Install with: pip install requests python-dotenv

Reads AZURE_DEVOPS_ORG, AZURE_DEVOPS_PROJECT, AZURE_DEVOPS_PAT from .env
"""

import os
import json
import base64
import requests
import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_VERSION = "7.1"


def get_env_or_arg(env_name, arg_value):
    return arg_value if arg_value else os.getenv(env_name)


def build_auth_header(pat):
    return {"Authorization": "Basic " + base64.b64encode(f":{pat}".encode()).decode()}


def create_work_item(item, org, project, headers, dry_run=False):
    # Choose a work item type that exists in the project. If the requested type
    # is not available, fall back to a sensible default (Task) or the first
    # available type.
    type_name = item.get("type", "Task")
    url_base = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems"

    # The caller may pass a resolved type in headers via a special key, but
    # instead we'll detect available types dynamically when needed.
    url = f"{url_base}/${type_name}?api-version={API_VERSION}"

    # Build patch doc without System.State to avoid invalid-state errors in
    # projects that use different process templates. Omitting State lets the
    # server apply the default initial state for that work item type.
    patch_doc = [
        {"op": "add", "path": "/fields/System.Title", "value": item["title"]},
        {"op": "add", "path": "/fields/System.Description", "value": item["description"]},
    ]

    req_headers = {**headers, "Content-Type": "application/json-patch+json"}
    if dry_run:
        print(f"  [DRY RUN] Would POST {url} with body: {json.dumps(patch_doc)[:400]}")
        # Simulate an id for downstream comments in dry-run mode
        return None

    # If the type doesn't exist the server returns 404. Try to detect an
    # available type and retry with a fallback.
    response = requests.post(url, headers=req_headers, data=json.dumps(patch_doc))
    if response.status_code == 404:
        # Query available types and choose a fallback
        types_resp = requests.get(f"https://dev.azure.com/{org}/{project}/_apis/wit/workitemtypes?api-version={API_VERSION}", headers=headers)
        if types_resp.status_code == 200:
            types = [t["name"] for t in types_resp.json().get("value", [])]
            fallback = "Task" if "Task" in types else (types[0] if types else None)
            if fallback:
                print(f"  Work item type '{type_name}' not found; retrying with '{fallback}'")
                url = f"{url_base}/${fallback}?api-version={API_VERSION}"
                response = requests.post(url, headers=req_headers, data=json.dumps(patch_doc))
            else:
                print(f"  No available work item types found for {org}/{project}")
        else:
            print(f"  Could not list work item types: {types_resp.status_code} {types_resp.text}")

    if response.status_code not in (200, 201):
        print(f"  Failed to create work item '{item['title']}': {response.status_code} {response.text}")
        return None

    work_item = response.json()
    work_item_id = work_item["id"]
    print(f"  Created {item['type']} #{work_item_id}: {item['title']}")

    for comment in item.get("comments", []):
        add_comment(work_item_id, comment, org, project, headers, dry_run=dry_run)

    return work_item_id


def add_comment(work_item_id, text, org, project, headers, dry_run=False):
    url = f"https://dev.azure.com/{org}/{project}/_apis/wit/workItems/{work_item_id}/comments?api-version={API_VERSION}-preview.4"
    req_headers = {**headers, "Content-Type": "application/json"}
    body = {"text": text}
    if dry_run:
        print(f"    [DRY RUN] Would POST comment to {work_item_id}: {text}")
        return

    response = requests.post(url, headers=req_headers, data=json.dumps(body))

    if response.status_code not in (200, 201):
        print(f"    Failed to add comment: {response.status_code} {response.text}")


def get_project_id(org, project, headers):
    url = f"https://dev.azure.com/{org}/_apis/projects/{project}?api-version={API_VERSION}"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise SystemExit(f"Could not find project '{project}' in org '{org}': {response.status_code} {response.text}")

    return response.json()["id"]


def ensure_wiki_exists(org, project, headers, dry_run=False):
    url = f"https://dev.azure.com/{org}/{project}/_apis/wiki/wikis?api-version={API_VERSION}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        wikis = response.json().get("value", [])
        if wikis:
            print(f"  Found existing wiki: {wikis[0]['name']}")
            return wikis[0]["name"]

    project_id = get_project_id(org, project, headers)

    create_url = f"https://dev.azure.com/{org}/{project}/_apis/wiki/wikis?api-version={API_VERSION}"
    req_headers = {**headers, "Content-Type": "application/json"}
    body = {"name": f"{project}.wiki", "projectId": project_id, "type": "projectWiki"}
    if dry_run:
        print(f"  [DRY RUN] Would create wiki with body: {json.dumps(body)}")
        return body["name"]

    response = requests.post(create_url, headers=req_headers, data=json.dumps(body))

    if response.status_code not in (200, 201):
        raise SystemExit(f"  Failed to create wiki: {response.status_code} {response.text}")

    print(f"  Created project wiki")
    return response.json()["name"]


def create_wiki_page(wiki_name, page, org, project, headers, dry_run=False):
    # Use the page title as the path; Azure DevOps encodes the page path as
    # a wiki path (leading slash). We'll URL-encode spaces when checking.
    page_path = page["title"]
    url = f"https://dev.azure.com/{org}/{project}/_apis/wiki/wikis/{wiki_name}/pages?path={page_path}&api-version={API_VERSION}"
    # Check whether the page already exists to avoid 'already exists' errors.
    check_resp = requests.get(url, headers=headers)
    if check_resp.status_code == 200:
        print(f"  Wiki page '{page['title']}' already exists; skipping")
        return
    req_headers = {**headers, "Content-Type": "application/json"}
    body = {"content": page["content"]}
    if dry_run:
        print(f"  [DRY RUN] Would PUT wiki page '{page['title']}' to {url}")
        return

    response = requests.put(url, headers=req_headers, data=json.dumps(body))

    if response.status_code not in (200, 201):
        print(f"  Failed to create wiki page '{page['title']}': {response.status_code} {response.text}")
        return

    print(f"  Created wiki page: {page['title']}")


def main():
    parser = argparse.ArgumentParser(description="Seed an Azure DevOps project with sample work items and wiki pages.")
    parser.add_argument("--org", help="Azure DevOps organization name (overrides .env)")
    parser.add_argument("--project", help="Azure DevOps project name (overrides .env)")
    parser.add_argument("--pat", help="Personal Access Token (overrides .env)")
    parser.add_argument("--data", help="Path to seed JSON file", default=str(Path(__file__).resolve().parent / "seed_data.json"))
    parser.add_argument("--dry-run", action="store_true", help="Show actions without making changes")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    args = parser.parse_args()

    org = get_env_or_arg("AZURE_DEVOPS_ORG", args.org)
    project = get_env_or_arg("AZURE_DEVOPS_PROJECT", args.project)
    pat = get_env_or_arg("AZURE_DEVOPS_PAT", args.pat)

    if not pat:
        raise SystemExit("Missing AZURE_DEVOPS_PAT in .env or via --pat")
    if not org or not project:
        print("You must provide AZURE_DEVOPS_ORG and AZURE_DEVOPS_PROJECT either in .env or via --org/--project")
        sys.exit(2)

    headers = build_auth_header(pat)

    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit(f"Seed data file not found: {data_path}")

    with open(data_path) as f:
        data = json.load(f)

    print(f"Seeding project '{project}' in org '{org}' (dry-run={args.dry_run})\n")

    if not args.yes and not args.dry_run:
        confirm = input(f"Proceed to create {len(data.get('work_items', []))} work items and {len(data.get('wiki_pages', []))} wiki pages in {org}/{project}? [y/N]: ")
        if confirm.lower() not in ("y", "yes"):
            print("Aborted by user.")
            return

    print("Creating work items...")
    for item in data.get("work_items", []):
        create_work_item(item, org, project, headers, dry_run=args.dry_run)

    print("\nSetting up wiki...")
    wiki_name = ensure_wiki_exists(org, project, headers, dry_run=args.dry_run)

    print("\nCreating wiki pages...")
    for page in data.get("wiki_pages", []):
        create_wiki_page(wiki_name, page, org, project, headers, dry_run=args.dry_run)

    print("\nDone. Check your project in the Azure DevOps portal to confirm everything landed.")


if __name__ == "__main__":
    main()