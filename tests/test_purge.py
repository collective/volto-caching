# Standard Library
from datetime import datetime
from time import sleep

# pytest
import pytest


def is_cache_hit(headers: dict) -> bool:
    """Validate if we have a hit in Varnish."""
    return headers.get("x-cache") == "HIT"


@pytest.fixture(scope="module", autouse=True)
def caching(auth_client):
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
            "plone.cachepurging.interfaces.ICachePurgingSettings.domains": [],
        },
    )
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


def test_manual_purge_works(anon_client, purge_url):
    # Use image
    url = "/page/logo-260x260.png/@@images/image/icon"

    # Populate cache
    anon_client.get(url)

    # Check url is in cache
    headers = anon_client.get(url).headers
    assert is_cache_hit(headers) is True

    # Purge URL
    assert purge_url(url) is True
    sleep(0.5)

    headers = anon_client.get(url).headers
    assert is_cache_hit(headers) is False


def test_auto_purge_document(anon_client, auth_client, purge_url):
    prefixes = ("", "/++api++")
    # Document
    base_url = "/page"

    for prefix in prefixes:
        url = f"{prefix}{base_url}"
        # First cleanup
        purge_url(url)
        # Populate cache with Volto rendered page and restapi cache
        anon_client.get(url)

        # Check url is in cache
        headers = anon_client.get(url).headers
        assert is_cache_hit(headers) is True

    # Edit page, should trigger purges
    now = datetime.utcnow()
    response = auth_client.patch(
        f"/++api++{base_url}",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={"title": f"New Page Document {now}"},
    )
    assert response.status_code == 204
    sleep(1.0)

    # Volto should be purged
    url = base_url
    headers = anon_client.get(url).headers
    assert is_cache_hit(headers) is False

    # RestAPI should be purged
    url = f"/++api++{base_url}"
    headers = anon_client.get(url).headers
    assert is_cache_hit(headers) is False


def test_auto_purge_image(anon_client, auth_client, purge_url):
    # Use image
    base_url = "/page/logo-260x260.png"
    url = f"{base_url}/@@images/image/icon"
    # Cleanup cache
    purge_url(url)
    # Populate cache
    anon_client.get(url)
    # Check url is in cache
    headers = anon_client.get(url).headers
    assert is_cache_hit(headers) is True
    # Purge URL
    now = datetime.utcnow()
    response = auth_client.patch(
        f"/++api++/{base_url}",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={"title": f"New Page Document {now}"},
    )
    assert response.status_code == 204
    # Sleep a bit longer to allow purger to propagate
    sleep(3.0)

    headers = anon_client.get(url).headers
    assert is_cache_hit(headers) is False
