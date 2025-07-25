from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from helpers import calculate_monthly_scores, segment_mothers_and_analyze_trends
from models import *

DATABASE_URL = "postgresql://cariyadb_user:hOZPY44VmR4vQv8P9OFzwCOHdShXrGBv@dpg-d1972anfte5s73c2rao0-a.oregon-postgres.render.com/cariyadb"
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