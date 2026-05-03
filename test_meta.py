from sqlalchemy import create_engine, Column, String
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid
import os

Base = declarative_base()

class TestModel(Base):
    __tablename__ = 'test_table'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String)

db_path = "test_meta.db"
if os.path.exists(db_path): os.remove(db_path)

engine = create_engine(f"sqlite:///{db_path}")
print("Creating tables...")
Base.metadata.create_all(engine)
print("Tables created.")
engine.dispose()

engine2 = create_engine(f"sqlite:///{db_path}")
from sqlalchemy import inspect
inspector = inspect(engine2)
print(f"Tables in DB: {inspector.get_table_names()}")
