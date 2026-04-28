import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def canonicalize_url(url: str) -> str:
    """
    Canonicalizes a URL by:
    - Lowercasing the scheme and host.
    - Lowercasing the path.
    - Removing tracking query parameters (utm_*, gclid, fbclid, ref, mc_*).
    - Sorting remaining query parameters.
    - Normalizing trailing slashes (removing them).
    - Removing fragments.

    Args:
        url: The URL to canonicalize.

    Returns:
        The canonicalized URL.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    path = parsed.path.lower()
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    elif not path:
        path = "/"

    query_params = parse_qsl(parsed.query)
    filtered_params = [
        (k.lower(), v)
        for k, v in query_params
        if not (
            k.lower().startswith("utm_")
            or k.lower() in ("gclid", "fbclid", "ref")
            or k.lower().startswith("mc_")
        )
    ]
    # Sort parameters to ensure consistent URL representation
    filtered_params.sort()

    new_query = urlencode(filtered_params)

    # Reconstruct URL without fragments
    return urlunparse((scheme, netloc, path, "", new_query, ""))


def compute_url_hash(url: str) -> str:
    """
    Computes the SHA256 hash of a canonicalized URL.

    Args:
        url: The URL to hash.

    Returns:
        The SHA256 hash string.
    """
    canonical = canonicalize_url(url)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
