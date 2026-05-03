import uuid
from sqlalchemy import create_engine, Column, String
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.dialects.postgresql import UUID

Base = declarative_base()

class TestModel(Base):
    __tablename__ = 'test'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String)

engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

with Session() as session:
    obj = TestModel(name='test')
    print(f"Before add: {obj.id}")
    session.add(obj)
    print(f"After add: {obj.id}")
    session.flush()
    print(f"After flush: {obj.id}")
