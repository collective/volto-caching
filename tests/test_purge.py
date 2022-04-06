# Standard Library
from time import sleep

# pytest
import pytest

from .helpers import nginx_rewrite


def is_cache_hit(headers: dict) -> bool:
    """Validate if we have a hit in Varnish."""
    return headers.get("x-cache") == "HIT"


@pytest.fixture(scope="module", autouse=True)
def caching(auth_client):
    # Enable caching, disable purge
    url = "/++api++/@registry"
    auth_client.patch(
        url,
        json={
            "plone.caching.interfaces.ICacheSettings.enabled": True,
            "plone.cachepurging.interfaces.ICachePurgingSettings.enabled": True,
            # "plone.cachepurging.interfaces.ICachePurgingSettings.cachingProxies": ['http://varnish'],
            # "plone.cachepurging.interfaces.ICachePurgingSettings.domains": ['http://volto.localhost:80'],
            # "plone.cachepurging.interfaces.ICachePurgingSettings.virtualHosting": True,
            # "plone.app.caching.interfaces.IPloneCacheSettings.purgedContentTypes": ['File', 'Folder', 'Image', 'News Item', 'Document'],
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
    url = "/++api++/"
    # Populate cache
    anon_client.get(url)

    # Check url is in cache
    headers = anon_client.get(url).headers
    assert is_cache_hit(headers) is True

    # Purge URL
    assert purge_url(nginx_rewrite(url)) is True
    sleep(0.5)

    headers = anon_client.get(url).headers
    assert is_cache_hit(headers) is False
