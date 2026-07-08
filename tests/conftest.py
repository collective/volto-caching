from collections.abc import Callable
from collections.abc import Generator
from pathlib import Path
from time import sleep

import httpx
import json
import logging
import pytest


logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def hostname() -> str:
    return "plone.localhost"


@pytest.fixture(scope="session")
def is_responsive(hostname: str) -> Callable[[str], bool]:
    headers = {"Host": hostname}

    def _func(url: str) -> bool:
        status = False
        try:
            response = httpx.get(url, headers=headers, timeout=2.0)
            status = response.status_code == 200
        except httpx.RequestError:
            status = False
        return status

    return _func


@pytest.fixture(scope="session")
def tests_dir() -> Path:
    """Return the path to the tests directory."""
    return Path(__file__).parent


@pytest.fixture(scope="session")
def repo_dir(tests_dir: Path) -> Path:
    """Return the path to the root directory."""
    return tests_dir.parent


@pytest.fixture(scope="session")
def contents(tests_dir: Path) -> list[list[str | dict]]:
    """Return the parsed default content payloads from data/content.json."""
    path = tests_dir / "data/content.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def base_url(hostname: str) -> str:
    return f"http://{hostname}"


@pytest.fixture(scope="session")
def api_url(base_url: str) -> str:
    return f"{base_url}/++api++"


@pytest.fixture(scope="session")
def backend_url() -> str:
    return "http://plone.localhost:8080/Plone"


@pytest.fixture(scope="session")
def docker_compose_project_name() -> str:
    """Return the name of the Docker Compose project."""
    return "volto-caching"


@pytest.fixture(scope="session")
def docker_setup():
    """Return the Docker Compose commands to set up the stack."""
    # Stop the stack before starting a new one
    return ["down -v", "up --build -d"]


@pytest.fixture(scope="session")
def docker_compose_file(repo_dir: Path) -> Path:
    """Fixture pointing to the docker-compose file to be used."""
    return repo_dir / "docker-compose.yml"


@pytest.fixture(scope="session")
def varnish_service(docker_ip, docker_services, is_responsive):
    """Ensure that Varnish service is up and responsive."""
    port = docker_services.port_for("varnish", 80)
    url = f"http://{docker_ip}:{port}/"
    sleep(10)  # Wait for Varnish to start
    docker_services.wait_until_responsive(
        timeout=50.0, pause=0.1, check=lambda: is_responsive(url)
    )
    return url


@pytest.fixture(scope="session")
def varnish_scale(docker_services) -> Callable[[int]]:
    """Return a function to scale the Varnish service to a given number of instances."""

    def _func(scale: int) -> None:
        cmd = f"scale varnish={scale}"
        docker_services._docker_compose.execute(cmd)
        sleep(5)  # Wait for the scaling to take effect

    return _func


@pytest.fixture(scope="session")
def varnish_urls(docker_ip) -> list[str]:
    """Return a list of Varnish URLs for testing."""
    return [f"http://{docker_ip}:8000/", f"http://{docker_ip}:8001/"]


@pytest.fixture(scope="session")
def header_accept() -> str:
    """Return the Accept header for HTTP requests."""
    return "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"  # noQA: E501


@pytest.fixture(scope="session")
def varnish_client(varnish_service) -> Generator[httpx.Client]:
    client = httpx.Client(base_url=varnish_service, headers={"Host": "plone.localhost"})
    yield client
    client.close()


@pytest.fixture(scope="session")
def varnish_multiple_clients(varnish_urls) -> Generator[list[httpx.Client]]:
    clients = []
    for v_url in varnish_urls:
        client = httpx.Client(
            base_url=v_url, headers={"Host": "plone.localhost", "x-varnish-debug": "1"}
        )
        clients.append(client)
    yield clients
    for client in clients:
        client.close()


@pytest.fixture(scope="session")
def anon_client(base_url, header_accept) -> Generator[httpx.Client]:
    client = httpx.Client(
        base_url=base_url,
        headers={"Accept": header_accept, "x-varnish-debug": "1"},
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def auth_root_client(base_url) -> Generator[httpx.Client]:
    client = httpx.Client(
        base_url=base_url,
        headers={"Accept": "application/json", "x-varnish-debug": "1"},
        auth=("admin", "admin"),
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def auth_client(base_url, api_url, header_accept) -> Generator[httpx.Client]:
    # Create user
    httpx.post(
        f"{api_url}/@users",
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
    # Get a token
    response = httpx.post(
        f"{api_url}/@login",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={"password": "12345678", "login": "noamchomsky"},
    )
    data = response.json()
    token = data["token"]

    client = httpx.Client(
        base_url=base_url,
        headers={
            "Accept": header_accept,
            "x-varnish-debug": "1",
            "Authorization": f"Bearer {token}",
        },
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def init_data(contents) -> list[tuple[str, str, dict]]:
    data = []
    for container, payload in contents:
        o_id = payload["id"]
        container_url = f"/++api++{container}"
        url = f"{container_url}/{o_id}"
        data.append((url, container_url, payload))

    return data


@pytest.fixture(scope="session", autouse=True)
def site(auth_root_client, init_data, varnish_client) -> Generator[str]:
    """Create content."""
    # Purge cache
    varnish_client.request(
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
        assert response.status_code < 400, (
            f"Failed to create {url}: {response.status_code} {response.text}"
        )
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
def purge_multiple_varnish_url(varnish_multiple_clients: list[httpx.Client]):
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
