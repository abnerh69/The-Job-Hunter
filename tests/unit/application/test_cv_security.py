import pytest
from jobhunter.application.cv import load_cv


def test_load_cv_path_traversal() -> None:
    """Verify that load_cv prevents path traversal."""
    with pytest.raises(ValueError, match="Insecure CV variant name"):
        load_cv("../../../etc/passwd")

    with pytest.raises(ValueError, match="Insecure CV variant name"):
        load_cv("subdir/variant")

    with pytest.raises(ValueError, match="Insecure CV variant name"):
        load_cv("..\\variant")
