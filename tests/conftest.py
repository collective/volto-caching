# Standard Library
import json
from pathlib import Path
from time import sleep

# HTTP Library
import httpx

# pytest
import pytest

from .helpers import VHM


BASE_URL = "http://volto.localhost"

BACKEND_URL = "http://volto.localhost:8080/Plone"

VARNISH_URL = "http://volto.localhost:8000/"

REPO_DIR = Path(__file__).parent.parent

CONTENTS = Path(REPO_DIR / "tests/data/content.json").resolve()


@pytest.fixture(scope="session")
def repo_dir() -> Path:
    return REPO_DIR


@pytest.fixture(scope="session")
def varnish_client() -> httpx.Client:
    client = httpx.Client(base_url=VARNISH_URL, headers={"Host": "varnish"})
    yield client
    client.close()


@pytest.fixture(scope="session")
def anon_client() -> httpx.Client:
    client = httpx.Client(
        base_url=BASE_URL,
        headers={"Accept": "application/json"},
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def auth_client() -> httpx.Client:
    client = httpx.Client(
        base_url=BASE_URL,
        headers={"Accept": "application/json"},
        auth=("admin", "admin"),
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def init_data() -> list:
    data = []
    with open(CONTENTS, "r") as fp:
        raw_data = json.load(fp)
    for container, payload in raw_data:
        o_id = payload["id"]
        container_url = f"/++api++{container}"
        url = f"{container_url}/{o_id}"
        data.append((url, container_url, payload))
    return data


@pytest.fixture(scope="session", autouse=True)
def site(auth_client, init_data, varnish_client):
    """Create content."""
    # Check if api is up
    while True:
        try:
            response = varnish_client.get(VHM)
            assert response.status_code == 200
        except:
            sleep(5)
        else:
            # API is up
            break

    # Purge cache
    response = varnish_client.request(
        method="BAN", url="/", headers={"x-invalidate-pattern": "obj.status != 0"}
    )
    sleep(0.5)

    # Setup default content
    for url, container_url, payload in init_data:
        # Check if content exists
        response = auth_client.get(url)
        if response.status_code != 404:
            # Content exists
            continue
        transitions = payload.pop("_transitions", [])
        response = auth_client.post(container_url, json=payload)
        if response.status_code >= 400:
            breakpoint()
        for transition in transitions:
            response = auth_client.post(f"{url}/@workflow/{transition}")
    yield "/"
    # Remove default content
    to_delete = reversed(init_data)
    for url, *_ in to_delete:
        response = auth_client.delete(url)


@pytest.fixture
def purge_url(varnish_client: httpx.Client):
    def inner(url: str = "") -> bool:
        response = varnish_client.request(
            method="PURGE",
            url=url,
        )
        return response.status_code == 200

    return inner
