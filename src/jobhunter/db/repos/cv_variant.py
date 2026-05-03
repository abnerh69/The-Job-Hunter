import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.db.models import CVVariant, CVVariantExperience
from jobhunter.db.repos.base import BaseRepo


class CVVariantRepo(BaseRepo[CVVariant]):
    """
    Repository for CVVariant model specific operations.
    """

    def __init__(self, session: Session):
        """
        Initializes the CVVariantRepo.

        Args:
            session (Session): The SQLAlchemy session.
        """
        super().__init__(CVVariant, session)

    def list_by_profile(self, profile_id: uuid.UUID) -> Sequence[CVVariant]:
        """
        Lists all CV variants for a given profile.

        Args:
            profile_id (uuid.UUID): The ID of the candidate profile.

        Returns:
            Sequence[CVVariant]: A sequence of CV variants.
        """
        stmt = select(CVVariant).where(CVVariant.profile_id == profile_id)
        return self.session.scalars(stmt).all()

    def get_by_name(self, profile_id: uuid.UUID, name: str) -> CVVariant | None:
        """
        Gets a CV variant by its name and profile ID.

        Args:
            profile_id (uuid.UUID): The ID of the candidate profile.
            name (str): The name of the variant.

        Returns:
            CVVariant | None: The CV variant if found, None otherwise.
        """
        stmt = select(CVVariant).where(CVVariant.profile_id == profile_id, CVVariant.name == name)
        return self.session.scalar(stmt)

    def create_with_experiences(
        self, variant: CVVariant, experiences: list[CVVariantExperience]
    ) -> CVVariant:
        """
        Creates a CV variant with its associated experiences.

        Args:
            variant (CVVariant): The CV variant to create.
            experiences (list[CVVariantExperience]): The list of experiences.

        Returns:
            CVVariant: The created CV variant with experiences.
        """
        self.session.add(variant)
        self.session.flush()

        for exp in experiences:
            exp.cv_variant_id = variant.id
            self.session.add(exp)

        self.session.flush()
        return variant

    def update_markdown(self, variant_id: uuid.UUID, raw_markdown: str) -> CVVariant | None:
        """
        Updates the raw markdown of a CV variant.

        Args:
            variant_id (uuid.UUID): The ID of the CV variant.
            raw_markdown (str): The new raw markdown content.

        Returns:
            CVVariant | None: The updated CV variant if found, None otherwise.
        """
        return self.update(variant_id, raw_markdown=raw_markdown)
