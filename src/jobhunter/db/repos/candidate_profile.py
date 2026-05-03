import uuid
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.db.models import CandidateProfile, CandidateProfileHistory
from jobhunter.db.repos.base import BaseRepo


class CandidateProfileRepo(BaseRepo[CandidateProfile]):
    """
    Repository for CandidateProfile model specific operations.
    """

    def __init__(self, session: Session):
        """
        Initializes the CandidateProfileRepo.

        Args:
            session (Session): The SQLAlchemy session.
        """
        super().__init__(CandidateProfile, session)

    def list_active(self) -> Sequence[CandidateProfile]:
        """
        Lists all active candidate profiles.

        Returns:
            Sequence[CandidateProfile]: A sequence of active candidate profiles.
        """
        stmt = select(CandidateProfile).where(CandidateProfile.is_active.is_(True))
        return self.session.scalars(stmt).all()

    def get_active_by_id(self, profile_id: uuid.UUID) -> CandidateProfile | None:
        """
        Gets an active candidate profile by its ID.

        Args:
            profile_id (uuid.UUID): The ID of the profile.

        Returns:
            CandidateProfile | None: The profile if found and active, None otherwise.
        """
        stmt = select(CandidateProfile).where(
            CandidateProfile.id == profile_id, CandidateProfile.is_active.is_(True)
        )
        return self.session.scalar(stmt)

    def update_with_history(
        self,
        profile_id: uuid.UUID,
        changed_by: str = "user",
        change_reason: str | None = None,
        **fields: Any,
    ) -> CandidateProfile | None:
        """
        Updates a candidate profile. The SQL trigger handles history snapshotting.

        Args:
            profile_id (uuid.UUID): The ID of the profile to update.
            changed_by (str): Who is making the change.
            change_reason (str | None): The reason for the change.
            **fields (Any): Fields and their new values to update.

        Returns:
            CandidateProfile | None: The updated profile if found, None otherwise.
        """
        if change_reason:
            fields["notes"] = change_reason

        # Note: 'changed_by' is not directly used by the trigger in this implementation
        # as the trigger hardcodes 'db_trigger'.

        return self.update(profile_id, **fields)

    def deactivate(self, profile_id: uuid.UUID) -> bool:
        """
        Deactivates a candidate profile.

        Args:
            profile_id (uuid.UUID): The ID of the profile to deactivate.

        Returns:
            bool: True if deactivated, False otherwise.
        """
        profile = self.update(profile_id, is_active=False)
        return profile is not None

    def update_compensation(self, profile_id: uuid.UUID, compensation: dict[str, Any]) -> bool:
        """
        Updates the compensation field of a candidate profile.

        Args:
            profile_id (uuid.UUID): The ID of the profile.
            compensation (dict[str, Any]): The compensation data.

        Returns:
            bool: True if updated, False otherwise.
        """
        profile = self.update(profile_id, compensation=compensation)
        return profile is not None

    def list_history(self, profile_id: uuid.UUID) -> Sequence[CandidateProfileHistory]:
        """
        Lists the history of a candidate profile.

        Args:
            profile_id (uuid.UUID): The ID of the profile.

        Returns:
            Sequence[CandidateProfileHistory]: A sequence of history records.
        """
        stmt = (
            select(CandidateProfileHistory)
            .where(CandidateProfileHistory.profile_id == profile_id)
            .order_by(CandidateProfileHistory.changed_at.desc())
        )
        return self.session.scalars(stmt).all()
