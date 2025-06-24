from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
    ARRAY,
    ForeignKey,
    DateTime,
    CheckConstraint,
)
from sqlalchemy.orm import declarative_base

# Initialize SQLAlchemy base class for model definitions
Base = declarative_base()

class Partners(Base):
    """Represents a partner organization that manages mothers and activities."""
    __tablename__ = "partners"
    partner_id = Column(String(50), primary_key=True)
    partner_name = Column(String(100), nullable=False, unique=True)
    description = Column(String)
    location = Column(String(100), nullable=False)
    total_members = Column(Integer, nullable=False, default=0, info={"check_constraint": CheckConstraint("total_members >= 0")})
    tel_number = Column(String(13))
    email = Column(String(255), unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class Mother(Base):
    """Represents a mother participating in the program."""
    __tablename__ = "mothers"
    generated_id = Column(String(50), primary_key=True)
    first_name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    mobile_number = Column(String(13), nullable=False, unique=True)
    num_children = Column(Integer, nullable=False, info={"check_constraint": CheckConstraint("num_children >= 0")})
    ages_of_children = Column(ARRAY(Integer), nullable=False)
    activity_points = Column(Integer, nullable=False, default=0, info={"check_constraint": CheckConstraint("activity_points >= 0")})
    savings = Column(Numeric(15, 2), nullable=False, default=0.0, info={"check_constraint": CheckConstraint("savings >= 0")})
    milestone_score = Column(Integer, nullable=False, default=0, info={"check_constraint": CheckConstraint("milestone_score >= 0")})
    compliance_score = Column(Integer, nullable=False, default=0, info={"check_constraint": CheckConstraint("compliance_score >= 0")})
    donor_contributions = Column(Numeric(15, 2), nullable=False, default=0.0, info={"check_constraint": CheckConstraint("donor_contributions >= 0")})
    partner_id = Column(String(50), ForeignKey("partners.partner_id", ondelete="SET NULL"))
    location = Column(String(100))
    education_level = Column(String(50))
    nin = Column(String(50))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class MotherActivity(Base):
    """Represents an activity offered by a partner for mothers."""
    __tablename__ = "mother_activities"
    activity_id = Column(String(50), primary_key=True)
    partner_id = Column(String(50), ForeignKey("partners.partner_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String)
    num_people = Column(Integer, nullable=False, default=0, info={"check_constraint": CheckConstraint("num_people >= 0")})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class MotherPartnerActivity(Base):
    """Links mothers to activities, enabling many-to-many relationships."""
    __tablename__ = "mother_partner_activities"
    id = Column(Integer, primary_key=True)
    mother_id = Column(String(50), ForeignKey("mothers.generated_id", ondelete="CASCADE"), nullable=False)
    activity_id = Column(String(50), ForeignKey("mother_activities.activity_id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class MonthlySavings(Base):
    """Tracks monthly savings and donor contributions for a mother."""
    __tablename__ = "monthly_savings"
    id = Column(Integer, primary_key=True)
    mother_id = Column(String(50), ForeignKey("mothers.generated_id", ondelete="CASCADE"), nullable=False)
    month_key = Column(String(7), nullable=False)
    savings = Column(Numeric(15, 2), nullable=False, default=0.0, info={"check_constraint": CheckConstraint("savings >= 0")})
    milestone_score = Column(Integer, nullable=False, default=0, info={"check_constraint": CheckConstraint("milestone_score IN (0, 1)")})
    donor_contribution = Column(Numeric(15, 2), nullable=False, default=0.0, info={"check_constraint": CheckConstraint("donor_contribution >= 0")})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class MonthlyActivityModel(Base):
    """Records a mother's participation in activities for a specific month."""
    __tablename__ = "monthly_activities"
    id = Column(Integer, primary_key=True)
    mother_id = Column(String(50), ForeignKey("mothers.generated_id", ondelete="CASCADE"), nullable=False)
    month_key = Column(String(7), nullable=False)
    activity_id = Column(String(50), ForeignKey("mother_activities.activity_id", ondelete="CASCADE"), nullable=False)
    activity_points = Column(Integer, nullable=False, default=1, info={"check_constraint": CheckConstraint("activity_points = 1")})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# from sqlalchemy import create_engine
# from models import Base
# DATABASE_URL = "postgresql://cariyadb_user:hOZPY44VmR4vQv8P9OFzwCOHdShXrGBv@dpg-d1972anfte5s73c2rao0-a.oregon-postgres.render.com/cariyadb"
# engine = create_engine(DATABASE_URL)
# Base.metadata.create_all(bind=engine)
# print("Schema applied successfully")