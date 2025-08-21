from datetime import datetime, time
from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
    ARRAY,
    ForeignKey,
    DateTime,
    CheckConstraint,
    Enum,
    Boolean,
    Time,
)
from sqlalchemy.orm import declarative_base, relationship

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

class PartnerSubscriptions(Base):
    """Tracks subscription details for partners."""
    __tablename__ = "partner_subscriptions"
    subscription_id = Column(String(50), primary_key=True)
    partner_id = Column(String(50), ForeignKey("partners.partner_id", ondelete="CASCADE"), nullable=False)
    subscription_tier = Column(Enum("Basic", "Gold", "Platinum", name="subscription_tier"), nullable=False, default="Basic")
    subscription_status = Column(String(20), nullable=False, default="pending", info={"check_constraint": CheckConstraint("subscription_status IN ('active', 'inactive', 'pending', 'expired')")})
    start_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    end_date = Column(DateTime)
    payment_details = Column(String)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class PartnerContributions(Base):
    """Tracks match funding contributions from partners to mothers."""
    __tablename__ = "partner_contributions"
    id = Column(Integer, primary_key=True)
    partner_id = Column(String(50), ForeignKey("partners.partner_id", ondelete="CASCADE"), nullable=False)
    mother_id = Column(String(50), ForeignKey("mothers.generated_id", ondelete="CASCADE"), nullable=False)
    month_key = Column(String(7), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False, default=0.0, info={"check_constraint": CheckConstraint("amount >= 0")})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class Donors(Base):
    """Represents individual donors contributing to the program."""
    __tablename__ = "donors"
    donor_id = Column(String(50), primary_key=True)
    first_name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    country_of_residence = Column(String(100))
    preferred_activities = Column(ARRAY(String))
    total_contributions = Column(Numeric(15, 2), nullable=False, default=0.0, info={"check_constraint": CheckConstraint("total_contributions >= 0")})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class Businesses(Base):
    """Represents businesses registered for Cariya Nuodge."""
    __tablename__ = "businesses"
    business_id = Column(String(50), primary_key=True)
    business_name = Column(String(100), nullable=False, unique=True)
    contact_email = Column(String(255), nullable=False, unique=True)
    country_of_residence = Column(String(100))
    payment_details = Column(String)
    subscription_status = Column(String(20), nullable=False, default="pending", info={"check_constraint": CheckConstraint("subscription_status IN ('active', 'inactive', 'pending')")})
    total_contributions = Column(Numeric(15, 2), nullable=False, default=0.0, info={"check_constraint": CheckConstraint("total_contributions >= 0")})
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
    donor_id = Column(String(50), ForeignKey("donors.donor_id", ondelete="SET NULL"), unique=True)
    location = Column(String(100))
    education_level = Column(String(50))
    nin = Column(String(50))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    savings_transactions = relationship("SavingsTransaction", back_populates="mother")
    saving_reminders = relationship("SavingReminder", back_populates="mother")

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
    mother_id = Column(String(50), ForeignKey("mothers.generated_id", ondelete="CASCADE"), primary_key=True)
    activity_id = Column(String(50), ForeignKey("mother_activities.activity_id", ondelete="CASCADE"), primary_key=True)
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
    partner_contribution = Column(Numeric(15, 2), nullable=False, default=0.0, info={"check_constraint": CheckConstraint("partner_contribution >= 0")})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class SavingsTransaction(Base):
    """Tracks individual savings transactions with detailed payment information."""
    __tablename__ = "savings_transactions"
    id = Column(Integer, primary_key=True)
    transaction_id = Column(String(100), nullable=False, unique=True)
    mother_id = Column(String(50), ForeignKey("mothers.generated_id", ondelete="CASCADE"), nullable=False)
    month_key = Column(String(7), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False, default=0.0, info={"check_constraint": CheckConstraint("amount >= 0")})
    phone_number = Column(String(13), nullable=False)
    payment_method = Column(String(50), nullable=False)
    transaction_status = Column(String(20), nullable=False, default="completed")
    reference_number = Column(String(100))
    notes = Column(String)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationship
    mother = relationship("Mother", back_populates="savings_transactions")



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

class DonorContributions(Base):
    """Tracks individual donor contributions to mothers."""
    __tablename__ = "donor_contributions"
    id = Column(Integer, primary_key=True)
    donor_id = Column(String(50), ForeignKey("donors.donor_id", ondelete="CASCADE"), nullable=False)
    mother_id = Column(String(50), ForeignKey("mothers.generated_id", ondelete="CASCADE"), nullable=False)
    month_key = Column(String(7), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False, default=0.0, info={"check_constraint": CheckConstraint("amount >= 0")})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class SavingReminder(Base):
    """Tracks saving reminders set by mothers."""
    __tablename__ = "saving_reminders"
    id = Column(Integer, primary_key=True)
    reminder_id = Column(String(50), nullable=False, unique=True)
    mother_id = Column(String(50), ForeignKey("mothers.generated_id", ondelete="CASCADE"), nullable=False)
    reminder_date = Column(Integer, nullable=False, info={"check_constraint": CheckConstraint("reminder_date >= 1 AND reminder_date <= 31")})
    reminder_time = Column(Time, nullable=False, default=time(9, 0))  # Default 9:00 AM
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)