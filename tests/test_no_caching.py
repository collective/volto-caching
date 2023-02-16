# Standard Library
from time import sleep

# pytest
import pytest


@pytest.fixture(scope="module", autouse=True)
def purge_varnish(varnish_client):
    sleep(0.5)
    response = varnish_client.request(
        method="BAN", url="/", headers={"x-invalidate-pattern": "obj.status != 0"}
    )
    sleep(0.5)
    yield response.status_code


@pytest.mark.parametrize(
    "url,status_code,mime_type",
    [
        ("/", 200, "text/html"),
    ],
)
def test_get_content_via_express(
    anon_client, url: str, status_code: int, mime_type: str
):
    response = anon_client.get(url)
    assert response.status_code == status_code
    assert mime_type in response.headers["Content-Type"]


@pytest.mark.parametrize(
    "url,status_code,mime_type",
    [
        ("/++api++/", 200, "application/json"),
        ("/++api++/@navigation", 200, "application/json"),
    ],
)
def test_get_content_via_varnish_no_cache(
    anon_client,
    purge_url,
    url: str,
    status_code: int,
    mime_type: str,
):
    purge_url(url)
    response = anon_client.get(url)
    assert response.status_code == status_code
    assert mime_type in response.headers["Content-Type"]
    assert response.headers["X-Cache"] == "MISS"


@pytest.mark.parametrize(
    "url,status_code,mime_type",
    [
        ("/++api++/", 200, "application/json"),
        ("/++api++/@navigation", 200, "application/json"),
    ],
)
def test_get_content_via_varnish_no_cache_auth(
    auth_client, url: str, status_code: int, mime_type: str
):
    response = auth_client.get(url)
    assert response.status_code == status_code
    assert mime_type in response.headers["Content-Type"]
    assert response.headers["X-Cache"] == "MISS"
    assert response.headers["X-Auth"] == "Logged-in"
