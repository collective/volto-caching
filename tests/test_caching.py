# Standard Library
from time import sleep

# pytest
import pytest


@pytest.fixture(scope="module", autouse=True)
def caching(auth_client):
    # Enable caching, disable purge
    url = "/++api++/@registry"
    headers = auth_client.headers
    headers["Accept"] = "application/json"
    auth_client.patch(
        url,
        headers=headers,
        json={
            "plone.caching.interfaces.ICacheSettings.enabled": True,
            "plone.cachepurging.interfaces.ICachePurgingSettings.enabled": False,
        },
    )
    yield "Enabled"
    # Disable caching, disable purge
    auth_client.patch(
        url,
        json={
            "plone.caching.interfaces.ICacheSettings.enabled": False,
            "plone.cachepurging.interfaces.ICachePurgingSettings.enabled": False,
        },
    )


@pytest.mark.parametrize(
    "url",
    [
        "/",
        "/page",
        "/page/logo-260x260.png",  # Image content
    ],
)
def test_varnish_in_front_of_express_cache(anon_client, purge_url, url: str):
    # Remove from cache
    purge_url(url)
    sleep(0.5)

    response = anon_client.get(url)
    assert response.status_code == 200
    headers = response.headers
    # Passing via Varnish
    assert headers.get("x-varnish") is not None
    assert headers.get("x-varnish-reqtype") == "express"
    assert headers.get("x-hits") == "0"
    assert headers.get("x-varnish-ttl") == "30.000"

    # Second request will get cached version
    response = anon_client.get(url)
    assert response.status_code == 200
    headers = response.headers
    assert headers.get("x-hits") == "1"
    assert float(headers.get("x-varnish-ttl")) < 30000


@pytest.mark.parametrize(
    "url",
    [
        "/page/logo-260x260.png/@@images/image/preview",
        "/page/logo-260x260.png/@@images/image/thumb",
        "/page/logo-260x260.png/@@images/image/icon",
    ],
)
def test_varnish_in_front_of_express_with_cache(anon_client, url: str):
    # First request could or could not be cached (we do not invalidate everything)
    response = anon_client.get(url)
    assert response.status_code == 200
    # Should get a cached version
    response = anon_client.get(url)
    assert response.status_code == 200
    headers = response.headers
    assert int(headers.get("x-hits")) > 0
    assert headers.get("x-varnish-reqtype") == "blob"


@pytest.fixture(scope="module")
def site_root(anon_client) -> dict:
    response = anon_client.get("/++api++/")
    return response.headers


@pytest.mark.parametrize(
    "header,value",
    [
        ("x-cache-operation", "plone.app.caching.terseCaching"),
        ("x-varnish-reqtype", "api"),
    ],
)
def test_root_headers_with_caching(site_root, header: str, value: str):
    assert site_root.get(header) == value


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Vary", "Accept-Encoding"),
        ("Vary", "Accept"),
        ("Via", "1.1 varnish (Varnish/7.1)"),
        ("Via", "waitress"),
    ],
)
def test_root_headers_with_caching_list(site_root, header: str, expected: str):
    value = site_root.get(header)
    assert expected in value, f"{value} does not contain {expected}"
