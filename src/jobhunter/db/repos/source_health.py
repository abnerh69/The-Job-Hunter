from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.db.models import SourceHealth
from jobhunter.db.repos.base import BaseRepo


class SourceHealthRepo(BaseRepo[SourceHealth]):
    """
    Repository for SourceHealth model specific operations.
    """

    def __init__(self, session: Session):
        """
        Initializes the SourceHealthRepo.

        Args:
            session (Session): The SQLAlchemy session.
        """
        super().__init__(SourceHealth, session)

    def get_by_source(self, source_name: str) -> SourceHealth | None:
        """
        Retrieves the health status of a specific job source.

        Args:
            source_name (str): The name of the source.

        Returns:
            SourceHealth | None: The health record if found, None otherwise.
        """
        stmt = select(SourceHealth).where(SourceHealth.source_name == source_name)
        return self.session.scalar(stmt)

    def get_or_create(self, source_name: str) -> SourceHealth:
        """
        Retrieves the health status of a source, creating it if it doesn't exist.

        Args:
            source_name (str): The name of the source.

        Returns:
            SourceHealth: The health record.
        """
        health = self.get_by_source(source_name)
        if not health:
            health = SourceHealth(source_name=source_name)
            self.session.add(health)
            self.session.flush()
        return health
