"""What the HTTP layer promises regardless of input: headers, status codes and who can reach what."""

import re

import pytest
from fastapi.testclient import TestClient

from plumbline.api.app import create_app
from plumbline.graph.client import connect


@pytest.fixture(scope="module")
def client():
    try:
        n = connect().ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty")
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.parametrize("path", ["/", "/check.html", "/api/health", "/api/nope"])
def test_every_response_carries_the_security_headers(client, path):
    h = client.get(path).headers
    csp = h["content-security-policy"]
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split("style-src")[0]
    assert "object-src 'none'" in csp and "base-uri 'none'" in csp
    assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "no-referrer"


def test_no_page_runs_inline_script(client):
    for page in ("/", "/check.html"):
        html = client.get(page).text
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), f"{page} has an inline script"
        assert not re.search(r"\bon[a-z]+\s*=\s*[\"']", html), f"{page} has an inline event handler"


def test_head_on_the_front_page_works_for_link_checkers(client):
    assert client.head("/").status_code == 200


def test_pages_are_revalidated_but_the_api_is_not_cached_by_us(client):
    assert client.get("/check.html").headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/api/health").headers


@pytest.mark.parametrize("path", ["/..%2f..%2fpyproject.toml", "/%2e%2e/%2e%2e/pyproject.toml", "/data/processed/MANIFEST.json"])
def test_files_outside_the_web_folder_are_not_served(client, path):
    assert client.get(path).status_code == 404


def test_the_swagger_page_that_would_need_a_cdn_is_not_exposed(client):
    assert client.get("/api/docs").status_code == 404
