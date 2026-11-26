"""Long-term memory controls in the sidebar: the opt-in switch, the list and the forget button."""

from pathlib import Path
from urllib.parse import urlsplit

import streamlit as st

from src import config, memory

SWITCH_HELP = (
    "Off: nothing is remembered after this conversation. On: the assistant may remember which "
    "kinds of places your family likes or avoids (for example museums, or indoor places) when you "
    "say so; you approve each one before it is saved. It uses them in later conversations. Only "
    "these fixed choices are kept: no names, "
    "ages, places you visited, budget or messages. While the switch is on they are sent to the AI "
    f"model ({config.AI_PROVIDER_NAME}; providers possibly outside the EU) with each question. "
    "Everyone who uses this app on this computer shares them. Switching off stops their use; "
    '"Forget everything" deletes them. Each one is deleted after '
    f"{config.LONG_TERM_MEMORY_RETENTION_DAYS} days."
)


@st.cache_resource
def _store_for(path: str) -> memory.FileBackedStore:
    """Load the store for one memory file once per app process."""
    return memory.FileBackedStore(Path(path))


def memory_store() -> memory.FileBackedStore:
    """Return the long-term memory store shared by the app process (one local profile)."""
    return _store_for(str(config.MEMORY_FILE))


def _host_name(value: str | None) -> str | None:
    """Return the host name of a URL or of a Host header value ("localhost:8510", "[::1]:8510")."""
    if not value:
        return None
    try:
        return urlsplit(value if "//" in value else f"//{value}").hostname
    except ValueError:  # e.g. a malformed IPv6 address: not local
        return None


def _forwarded(headers) -> bool:
    """Return True when any header shows a proxy or tunnel, whatever its value or letter case."""
    names = [str(name).lower() for name in headers]
    return any(
        name in config.FORWARDING_HEADERS or name.startswith(config.FORWARDING_HEADER_PREFIXES)
        for name in names
    )


def is_local_visit() -> bool:
    """Return True when the page was opened on the computer that runs the app."""
    try:
        ip = st.context.ip_address
        headers = st.context.headers or {}
        hosts = [_host_name(st.context.url), _host_name(headers.get("Host"))]
        origin = headers.get("Origin")
    except Exception:  # noqa: BLE001 - outside a page run there is no visitor
        return False
    # A browser always sends Origin on the WebSocket; without one it is not a browser visit.
    if not origin:
        return False
    # A proxy or tunnel marks forwarded requests: that is a visit from elsewhere, even if it
    # rewrites the Host header to localhost (security review T5.11 rounds 5 and 6).
    if _forwarded(headers):
        return False
    # Same origin only: a page from another local port (another dev server) is not this app.
    try:
        origin_netloc = urlsplit(origin).netloc.lower()
    except ValueError:
        return False
    if origin_netloc != (headers.get("Host") or "").lower():
        return False
    hosts.append(_host_name(origin))
    # Streamlit reports no address for a visitor on the same computer, and also for a proxy there,
    # so the host names must be local too. The page URL comes from the browser; the Host and Origin
    # headers come from the connection, which a web page cannot set (DNS rebinding, security
    # review T5.11 round 2). `server.allowedHosts` in .streamlit/config.toml blocks other hosts.
    local_peer = ip is None or ip in config.MEMORY_LOCAL_ADDRESSES
    return local_peer and all(h in config.MEMORY_LOCAL_ADDRESSES for h in hosts)


def render_memory_settings() -> bool:
    """Draw the memory switch, what is remembered and the forget button; return the switch."""
    if not config.LONG_TERM_MEMORY_ENABLED:
        return False
    st.subheader("🧠 Memory")
    if not is_local_visit():
        # One local profile is shared by everyone who opens the app: never offered from afar.
        st.caption("Long-term memory is only available when the app runs on your own computer.")
        return False
    on = st.toggle(
        "Remember our preferences on this computer", value=False, key="memory_on", help=SWITCH_HELP
    )
    store = memory_store()
    remembered = memory.preferences(store)
    if remembered:
        st.caption("Remembered: " + ", ".join(memory.label(p) for p in remembered))
        if st.button("🗑️ Forget everything", key="memory_forget", use_container_width=True):
            try:
                memory.forget_all(store)
            except OSError:
                st.error("The memory file could not be changed. Please try again.")
                return on
            st.toast("Everything remembered was deleted.")
            st.rerun()
    elif on:
        st.caption("Nothing remembered yet.")
    return on
