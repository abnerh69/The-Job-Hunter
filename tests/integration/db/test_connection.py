from sqlalchemy import text

from jobhunter.db.session import get_session


def test_db_connection() -> None:
    """
    Test that we can get a session and execute a simple query.
    """
    with get_session() as session:
        # Execute a simple query
        result = session.execute(text("SELECT 1"))
        assert result.scalar() == 1
