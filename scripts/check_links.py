"""Check that every website in the knowledge base still answers (one request per site).

Run: python -m scripts.check_links
"""

import requests

from src import config
from src.knowledge import load_places


def main() -> None:
    """Request each website once and print the ones that fail."""
    failed = 0
    for place in load_places():
        url = str(place.website)
        try:
            response = requests.get(
                url,
                headers={"User-Agent": config.HTTP_USER_AGENT},
                timeout=config.HTTP_TIMEOUT_SECONDS,
                allow_redirects=True,
            )
            status = response.status_code
        except requests.RequestException as exc:
            status = type(exc).__name__
        ok = isinstance(status, int) and status < 400
        failed += not ok
        print(f"{'OK ' if ok else 'BAD'} {status!s:>5}  {place.id:<34} {url}")
    print(f"\n{failed} of {len(load_places())} links failed.")


if __name__ == "__main__":
    main()
