from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from helpers import calculate_monthly_scores, segment_mothers_and_analyze_trends
from models import *

DATABASE_URL = "postgresql://cariyadb_damb_user:LLM87f54JeWhIfyHBDSKJogoPqc93jrW@dpg-d28s0druibrs73dt691g-a.oregon-postgres.render.com/cariyadb_damb"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

try:
    # Calculate scores for April 2025
    result = calculate_monthly_scores(db, target_month=7)
    print(result)
    # Segment mothers
    trends = segment_mothers_and_analyze_trends(db)
    print(trends)
finally:
    db.close()