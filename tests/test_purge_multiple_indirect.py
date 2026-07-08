from datetime import UTC
from datetime import datetime
from time import sleep

import httpx
import pytest


def is_cache_hit(headers: dict) -> bool:
    """Validate if we have a hit in Varnish."""
    return headers.get("x-cache") == "HIT"


# Since we do not have direct access to all varnish containers we have to infer
# via multiple requests and parsing headers wether a url is cached on both varnish
# containers
# Varnish sets the Header x-hits as a counter how often this cached content has been
# accessed. On the first call to a content that has not been cached it is 0.
# Every call to this (now cached) document will increase the counter by one.
# If the x-hits counter did not increase by one on two successive calls to a content
# we can be sure that those two calls did not go to the same varnish cache
def check_url_against_multiple_varnish(url: str, client: httpx.Client) -> list:
    hits = []
    # First request
    headers = client.get(url).headers
    hits.append(headers.get("x-cache") == "HIT")
    first_request_hits = int(headers.get("x-hits"))
    # Second request: keep polling until a request lands on a different varnish
    # instance (its x-hits counter no longer equals first_request_hits + 1).
    max_attempts = 20
    for _ in range(max_attempts):
        headers = client.get(url).headers
        second_request_hits = int(headers.get("x-hits"))
        if second_request_hits != first_request_hits + 1:
            break
    else:
        raise AssertionError(
            f"Requests to {url} never reached a second varnish instance "
            f"after {max_attempts} attempts"
        )
    hits.append(headers.get("x-cache") == "HIT")

    return hits


@pytest.fixture(scope="module", autouse=True)
def caching(auth_client, varnish_scale):
    # Enable caching
    url = "/++api++/@registry"
    auth_client.patch(
        url,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={
            "plone.caching.interfaces.ICacheSettings.enabled": True,
            "plone.cachepurging.interfaces.ICachePurgingSettings.enabled": True,
            "plone.cachepurging.interfaces.ICachePurgingSettings.cachingProxies": [
                "http://purger:80"
            ],
            "plone.cachepurging.interfaces.ICachePurgingSettings.domains": [],
            "plone.cachepurging.interfaces.ICachePurgingSettings.virtualHosting": False,
            "plone.app.caching.interfaces.IPloneCacheSettings.purgedContentTypes": [
                "File",
                "Folder",
                "Image",
                "News Item",
                "Document",
            ],
        },
    )
    # spawn second varnish container and wait a second for it to start
    varnish_scale(2)
    yield "Enabled"
    # Disable caching, disable purge
    auth_client.patch(
        url,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={
            "plone.caching.interfaces.ICacheSettings.enabled": False,
            "plone.cachepurging.interfaces.ICachePurgingSettings.enabled": False,
        },
    )
    # disable second varnish container
    varnish_scale(0)
    varnish_scale(1)


def test_auto_purge_document(anon_client, auth_client, purge_url):
    prefixes = ("", "/++api++")
    # Document
    base_url = "/page"

    for prefix in prefixes:
        url = f"{prefix}{base_url}"
        # First cleanup
        purge_url(url)
        purge_url(url)
        sleep(2.0)
        # Populate cache with Volto rendered page and restapi cache
        anon_client.get(url)
        anon_client.get(url)

        # Check url is in cache
        for hit in check_url_against_multiple_varnish(url, anon_client):
            assert hit is True

    # Edit page, should trigger purges
    now = datetime.now(UTC)
    response = auth_client.patch(
        f"/++api++{base_url}",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={"title": f"New Page Document {now}"},
    )
    assert response.status_code == 204
    sleep(1.0)

    # Volto should be purged
    url = base_url
    for hit in check_url_against_multiple_varnish(url, anon_client):
        assert hit is False

    # RestAPI should be purged
    url = f"/++api++{base_url}"
    for hit in check_url_against_multiple_varnish(url, anon_client):
        assert hit is False


def test_auto_purge_image(anon_client, auth_client, purge_url):
    # Use image
    base_url = "/page/logo-260x260.png"
    url = f"{base_url}/@@images/image/icon"
    # Cleanup cache
    purge_url(url)
    # Populate cache
    anon_client.get(url)
    anon_client.get(url)
    # Check url is in cache

    for hit in check_url_against_multiple_varnish(url, anon_client):
        assert hit is True
    # Purge URL

    now = datetime.now(UTC)
    response = auth_client.patch(
        f"/++api++{base_url}",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={"title": f"New Page Document {now}"},
    )
    assert response.status_code == 204
    # Sleep a bit longer to allow purger to propagate
    sleep(3.0)
    for hit in check_url_against_multiple_varnish(url, anon_client):
        assert hit is False
