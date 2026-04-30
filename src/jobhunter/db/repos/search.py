from typing import Dict, List, Any
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from jobhunter.db.models import Job, Application, OutreachContact


class SearchRepo:
    """
    Repository for global full-text search operations.
    """

    def __init__(self, session: Session):
        """
        Initializes the SearchRepo.

        Args:
            session (Session): The SQLAlchemy session.
        """
        self.session = session

    def search(self, query: str, limit: int = 20) -> Dict[str, List[Any]]:
        """
        Performs a full-text search across Jobs, Applications, and OutreachContacts.

        Args:
            query (str): The search query.
            limit (int): Maximum number of records to return per category. Defaults to 20.

        Returns:
            Dict[str, List[Any]]: Results grouped by entity type.
        """
        results: Dict[str, List[Any]] = {"jobs": [], "applications": [], "contacts": []}

        if not query:
            return results

        is_postgres = False
        if self.session.bind:
            is_postgres = self.session.bind.dialect.name == "postgresql"

        if is_postgres:
            # Postgres Full-Text Search
            # Jobs
            jobs_stmt = (
                select(Job)
                .where(text("search_vector @@ plainto_tsquery('english', :query)"))
                .order_by(
                    func.ts_rank(
                        text("search_vector"), func.plainto_tsquery("english", query)
                    ).desc()
                )
                .limit(limit)
                .params(query=query)
            )
            results["jobs"] = list(self.session.scalars(jobs_stmt).all())

            # Applications
            apps_stmt = (
                select(Application)
                .where(text("search_vector @@ plainto_tsquery('english', :query)"))
                .order_by(
                    func.ts_rank(
                        text("search_vector"), func.plainto_tsquery("english", query)
                    ).desc()
                )
                .limit(limit)
                .params(query=query)
            )
            results["applications"] = list(self.session.scalars(apps_stmt).all())

            # Outreach Contacts
            contacts_stmt = (
                select(OutreachContact)
                .where(text("search_vector @@ plainto_tsquery('english', :query)"))
                .order_by(
                    func.ts_rank(
                        text("search_vector"), func.plainto_tsquery("english", query)
                    ).desc()
                )
                .limit(limit)
                .params(query=query)
            )
            results["contacts"] = list(self.session.scalars(contacts_stmt).all())

        else:
            # Fallback for SQLite (LIKE)
            # Jobs: title, company, description
            jobs_stmt = (
                select(Job)
                .where(
                    (Job.title.ilike(f"%{query}%"))
                    | (Job.company.ilike(f"%{query}%"))
                    | (Job.description.ilike(f"%{query}%"))
                )
                .limit(limit)
            )
            results["jobs"] = list(self.session.scalars(jobs_stmt).all())

            # Applications: notes
            apps_stmt = (
                select(Application).where(Application.notes.ilike(f"%{query}%")).limit(limit)
            )
            results["applications"] = list(self.session.scalars(apps_stmt).all())

            # Outreach Contacts: name, company
            contacts_stmt = (
                select(OutreachContact)
                .where(
                    (OutreachContact.name.ilike(f"%{query}%"))
                    | (OutreachContact.company.ilike(f"%{query}%"))
                )
                .limit(limit)
            )
            results["contacts"] = list(self.session.scalars(contacts_stmt).all())

        return results
