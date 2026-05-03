from sqlalchemy import create_engine, inspect
engine = create_engine('sqlite:///test_e2e_onboarding.db')
inspector = inspect(engine)
print(f"Tables: {inspector.get_table_names()}")
