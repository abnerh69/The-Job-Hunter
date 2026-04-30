from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.db.models import OAuthToken
from jobhunter.db.repos.base import BaseRepo


class OAuthTokenRepo(BaseRepo[OAuthToken]):
    """
    Repository for OAuthToken model specific operations.
    """

    def __init__(self, session: Session):
        """
        Initializes the OAuthTokenRepo.

        Args:
            session (Session): The SQLAlchemy session.
        """
        super().__init__(OAuthToken, session)

    def get_token(self, provider: str, account_email: str) -> OAuthToken | None:
        """
        Retrieves an OAuthToken by provider and account email.

        Args:
            provider (str): The OAuth provider (e.g., 'gmail').
            account_email (str): The email address associated with the account.

        Returns:
            OAuthToken | None: The token record if found, None otherwise.
        """
        stmt = select(OAuthToken).where(
            OAuthToken.provider == provider, OAuthToken.account_email == account_email
        )
        return self.session.scalar(stmt)
