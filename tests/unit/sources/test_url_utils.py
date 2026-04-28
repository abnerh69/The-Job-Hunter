import pytest
from jobhunter.sources.url_utils import canonicalize_url, compute_url_hash


@pytest.mark.parametrize(
    "url,expected",
    [
        ("HTTPS://EXAMPLE.COM/path/", "https://example.com/path"),
        (
            "https://example.com/path/?utm_source=twitter&foo=bar",
            "https://example.com/path?foo=bar",
        ),
        ("https://example.com/path#fragment", "https://example.com/path"),
        ("https://example.com/path?b=2&a=1", "https://example.com/path?a=1&b=2"),
        (
            "https://example.com/path?GCLID=123&REF=456&utm_campaign=xyz",
            "https://example.com/path",
        ),
        ("https://example.com/path?mc_eid=789&other=val", "https://example.com/path?other=val"),
        ("https://example.com/", "https://example.com/"),
        ("https://example.com", "https://example.com/"),
    ],
)
def test_canonicalize_url(url: str, expected: str) -> None:
    assert canonicalize_url(url) == expected


def test_compute_url_hash() -> None:
    url1 = "https://example.com/PATH/?UTM_SOURCE=test&A=1"
    url2 = "https://example.com/path?a=1&utm_medium=email"

    hash1 = compute_url_hash(url1)
    hash2 = compute_url_hash(url2)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 length in hex
