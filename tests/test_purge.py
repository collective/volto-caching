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
        json={
            "plone.caching.interfaces.ICacheSettings.enabled": True,
            "plone.cachepurging.interfaces.ICachePurgingSettings.enabled": True,
            "plone.cachepurging.interfaces.ICachePurgingSettings.cachingProxies": [
                'http://varnish:80'
            ],
            "plone.cachepurging.interfaces.ICachePurgingSettings.domains": [
                'http://plone.localhost',
                'http://plone.localhost/++api++',
            ],
            "plone.cachepurging.interfaces.ICachePurgingSettings.virtualHosting": False,
            "plone.app.caching.interfaces.IPloneCacheSettings.purgedContentTypes": [
                'File', 'Folder', 'Image', 'News Item', 'Document'
            ],
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


def test_auto_purge_works(anon_client, auth_client):
    # Use image
    base_url = "/page/logo-260x260.png"
    url = f"{base_url}/@@images/image/icon"

    # Populate cache
    anon_client.get(url)
    # Check url is in cache
    headers = anon_client.get(url).headers
    assert is_cache_hit(headers) is True

    # Purge URL
    now = datetime.utcnow()
    response = auth_client.patch(
        f"/++api++/{base_url}",
        json={
            'title': f'New Page Document {now}'
        }
    )
    assert response.status_code == 204
    sleep(1.0)

    headers = anon_client.get(url).headers
    assert is_cache_hit(headers) is False
