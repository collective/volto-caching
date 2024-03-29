# Standard Library
import json
import subprocess
from pathlib import Path
from time import sleep

# HTTP Library
import httpx

# pytest
import pytest


BASE_URL = "http://plone.localhost"
API_URL = f"{BASE_URL}/++api++"

BACKEND_URL = "http://plone.localhost:8080/Plone"

VARNISH_PORT = (
    subprocess.run(
        ["docker", "compose", "port", "varnish", "80"], capture_output=True, text=True
    )
    .stdout.strip()
    .split(":")[1]
)

VARNISH_URL = f"http://plone.localhost:{VARNISH_PORT}"

VARNISH_MULTIPLE_URL = ["http://plone.localhost:8000", "http://plone.localhost:8001"]

REPO_DIR = Path(__file__).parent.parent

CONTENTS = Path(REPO_DIR / "tests/data/content.json").resolve()

ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"  # noQA


@pytest.fixture(scope="session")
def repo_dir() -> Path:
    return REPO_DIR


@pytest.fixture(scope="session")
def varnish_client() -> httpx.Client:
    client = httpx.Client(base_url=VARNISH_URL, headers={"Host": "plone.localhost"})
    yield client
    client.close()


@pytest.fixture(scope="session")
def varnish_multiple_clients() -> list:
    clients = []
    for v_url in VARNISH_MULTIPLE_URL:
        client = httpx.Client(
            base_url=v_url, headers={"Host": "plone.localhost", "x-varnish-debug": "1"}
        )
        clients.append(client)
    yield clients
    for client in clients:
        client.close()


@pytest.fixture(scope="session")
def anon_client() -> httpx.Client:
    client = httpx.Client(
        base_url=BASE_URL,
        headers={"Accept": ACCEPT, "x-varnish-debug": "1"},
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def auth_root_client() -> httpx.Client:
    client = httpx.Client(
        base_url=BASE_URL,
        headers={"Accept": "application/json", "x-varnish-debug": "1"},
        auth=("admin", "admin"),
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def auth_client() -> httpx.Client:
    resp = httpx.post(
        f"{API_URL}/@users",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={
            "description": "Professor of Linguistics",
            "email": "noam.chomsky@example.com",
            "fullname": "Noam Avram Chomsky",
            "home_page": "web.mit.edu/chomsky",
            "location": "Cambridge, MA",
            "password": "12345678",
            "roles": ["Manager"],
            "username": "noamchomsky",
        },
        auth=("admin", "admin"),
    )
    response = httpx.post(
        f"{API_URL}/@login",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={"password": "12345678", "login": "noamchomsky"},
    )
    data = response.json()
    token = data["token"]

    client = httpx.Client(
        base_url=BASE_URL,
        headers={
            "Accept": ACCEPT,
            "x-varnish-debug": "1",
            "Authorization": f"Bearer {token}",
        },
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
def site(auth_root_client, init_data, varnish_client):
    """Create content."""
    # Check if api is up
    while True:
        try:
            response = varnish_client.get("/++api++/")
            assert response.status_code == 200
        except Exception as exc:
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
        response = auth_root_client.get(url)
        if response.status_code != 404:
            # Content exists
            continue
        transitions = payload.pop("_transitions", [])
        response = auth_root_client.post(container_url, json=payload)
        if response.status_code >= 400:
            breakpoint()
        for transition in transitions:
            response = auth_root_client.post(f"{url}/@workflow/{transition}")
    yield "/"
    # Remove default content
    to_delete = reversed(init_data)
    for url, *_ in to_delete:
        response = auth_root_client.delete(url)


@pytest.fixture
def purge_url(varnish_client: httpx.Client):
    def inner(url: str = "") -> bool:
        response = varnish_client.request(
            method="PURGE",
            url=url,
        )
        return response.status_code == 200

    return inner


@pytest.fixture
def purge_multiple_varnish_url(varnish_multiple_clients: list):
    def inner(url: str = "") -> bool:
        success = True
        for varnish_client in varnish_multiple_clients:
            response = varnish_client.request(
                method="PURGE",
                url=url,
            )
            if response.status_code != 200:
                success = False
        return success

    return inner
