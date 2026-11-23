"""Check that every website in the knowledge base still answers (one request per site).

A site that redirects to another host is reported as MOVED, since a parked or sold domain
also answers 200.

Run: python -m scripts.check_links
"""

from urllib.parse import urlsplit

import requests

from src import config
from src.knowledge import load_places


def same_site(url: str, final_url: str) -> bool:
    """Return True when the final URL stays on the same host (ignoring a leading "www.")."""

    def host(value: str) -> str:
        """Return the lower-case host without "www."."""
        return (urlsplit(value).hostname or "").lower().removeprefix("www.")

    return host(url) == host(final_url)


def main() -> None:
    """Request each website once and print the ones that fail or moved to another host."""
    failed = moved = 0
    places = load_places()
    for place in places:
        url = str(place.website)
        final = url
        try:
            response = requests.get(
                url,
                headers={"User-Agent": config.HTTP_USER_AGENT},
                timeout=config.HTTP_TIMEOUT_SECONDS,
                allow_redirects=True,
            )
            status = response.status_code
            final = response.url
        except requests.RequestException as exc:
            status = type(exc).__name__
        ok = isinstance(status, int) and status < 400
        label = "OK " if ok else "BAD"
        if ok and not same_site(url, final):
            label = "MOVED"
            moved += 1
        failed += not ok
        print(
            f"{label:<5} {status!s:>5}  {place.id:<34} {url}"
            + ("" if final == url else f" -> {final}")
        )
    print(f"\n{failed} of {len(places)} links failed, {moved} moved to another host.")


if __name__ == "__main__":
    main()
