from sqlalchemy import create_engine
from jobhunter.db.base import Base
import jobhunter.db.models
import os

db_path = "test_meta_2.db"
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
