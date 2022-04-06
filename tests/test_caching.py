# pytest
import pytest


@pytest.fixture(scope="module", autouse=True)
def caching(auth_client):
    # Enable caching, disable purge
    url = "/++api++/@registry"
    auth_client.patch(
        url,
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
        "/page/logo-260x260.png",
        "/page/logo-260x260.png/@@images/image/preview",
    ],
)
def test_express_in_front_of_varnish(anon_client, url: str):
    response = anon_client.get(url)
    assert response.status_code == 200
    headers = response.headers
    assert headers.get("x-varnish") is None


@pytest.fixture(scope="module")
def site_root(anon_client) -> dict:
    response = anon_client.get("/++api++/")
    return response.headers


@pytest.mark.parametrize(
    "header,value",
    [
        ("Vary", "Accept"),
        ("X-cache-operation", "plone.app.caching.terseCaching"),
    ],
)
def test_root_headers_with_caching(site_root, header: str, value: str):
    assert site_root.get(header) == value
