import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


def get_session(retries: int = 3, backoff_factor: float = 0.5):
    """Return a requests.Session configured with retry/backoff for common transient errors."""
    session = requests.Session()
    # urllib3 older versions used `method_whitelist` instead of `allowed_methods`.
    # Try the modern arg first, fall back if it raises TypeError.
    try:
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )
    except TypeError:
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            method_whitelist=("GET", "POST"),
        )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
