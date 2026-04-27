import jobhunter


def test_imports() -> None:
    """Verify that the package can be imported."""
    assert jobhunter.__version__ is not None
