from typing import Any, Generic, Sequence, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.db.base import Base

T = TypeVar("T", bound=Base)


class BaseRepo(Generic[T]):
    """
    Base repository class with common CRUD operations.

    Attributes:
        model (Type[T]): The SQLAlchemy model class.
        session (Session): The SQLAlchemy session.
    """

    def __init__(self, model: Type[T], session: Session):
        """
        Initializes the repository.

        Args:
            model (Type[T]): The SQLAlchemy model class.
            session (Session): The SQLAlchemy session.
        """
        self.model = model
        self.session = session

    def get(self, id: Any) -> T | None:
        """
        Get a record by its primary key.

        Args:
            id (Any): The primary key of the record.

        Returns:
            T | None: The record if found, None otherwise.
        """
        return self.session.get(self.model, id)

    def list(self, **filters: Any) -> Sequence[T]:
        """
        List records with optional filtering.

        Args:
            **filters (Any): Filtering criteria.

        Returns:
            Sequence[T]: A sequence of records matching the filters.
        """
        stmt = select(self.model).filter_by(**filters)
        return self.session.scalars(stmt).all()

    def create(self, obj: T) -> T:
        """
        Create a new record.

        Args:
            obj (T): The model instance to create.

        Returns:
            T: The created model instance.
        """
        self.session.add(obj)
        self.session.flush()
        return obj

    def update(self, id: Any, **fields: Any) -> T | None:
        """
        Update a record by its primary key.

        Args:
            id (Any): The primary key of the record.
            **fields (Any): Fields and their new values to update.

        Returns:
            T | None: The updated record if found, None otherwise.
        """
        obj = self.get(id)
        if obj:
            for key, value in fields.items():
                setattr(obj, key, value)
            self.session.flush()
        return obj

    def delete(self, id: Any) -> bool:
        """
        Delete a record by its primary key.

        Args:
            id (Any): The primary key of the record.

        Returns:
            bool: True if the record was deleted, False otherwise.
        """
        obj = self.get(id)
        if obj:
            self.session.delete(obj)
            self.session.flush()
            return True
        return False
