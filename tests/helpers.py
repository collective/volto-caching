# Standard Library
import re


PATTERN = r"^/(\+\+api\+\+\/?)+($|/.*)"
VHM = "/VirtualHostBase/http/plone.localhost:80/Plone/++api++/VirtualHostRoot"


def nginx_rewrite(url: str) -> str:
    """Simulate an nginx rewrite."""
    if re.search("\+\+api\+\+", url):
        url = re.sub(pattern=PATTERN, repl=f"{VHM}\\2", string=url)
    return url
