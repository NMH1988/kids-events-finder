"""Shared fixtures: no test may reach the network or use a real API key."""

import pytest
import requests

from src import config


class NetworkBlocked(requests.ConnectionError):
    """Raised when a test tries to make a real HTTP request."""


@pytest.fixture(autouse=True)
def _no_network_no_keys(monkeypatch):
    """Block real HTTP requests and remove API keys from the environment for every test."""

    def blocked(*args, **kwargs):
        """Fail any request a test did not mock."""
        raise NetworkBlocked("A test tried to reach the network.")

    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(requests, "post", blocked)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("TICKETMASTER_API_KEY", raising=False)
    # A developer's .streamlit/secrets.toml must not reach the tests either.
    monkeypatch.setattr(config, "get_secret", lambda name: None)


@pytest.fixture(autouse=True)
def _memory_in_tmp(monkeypatch, tmp_path):
    """Keep every test's long-term memory in its own temporary file, never in data/memory/."""
    monkeypatch.setattr(config, "MEMORY_FILE", tmp_path / "memory" / "preferences.json")


class FakeResponse:
    """A minimal requests.Response stand-in with a JSON body."""

    def __init__(self, payload: dict, status: int = 200) -> None:
        """Keep the body and status code."""
        self.payload = payload
        self.status_code = status

    def json(self) -> dict:
        """Return the JSON body."""
        return self.payload

    def raise_for_status(self) -> None:
        """Raise like requests does for an error status."""
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")
