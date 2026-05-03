import sys
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from jobhunter.db.models import CandidateProfile, CVVariant

engine = create_engine('sqlite:///test_e2e_onboarding.db')
with Session(engine) as session:
    profiles = session.scalars(select(CandidateProfile)).all()
    print(f"Profiles found: {len(profiles)}")
    for p in profiles:
        print(f"  - {p.id} : {p.name}")

    variants = session.scalars(select(CVVariant)).all()
    print(f"Variants found: {len(variants)}")
