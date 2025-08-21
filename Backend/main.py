import os
import uuid
import re
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Union, List,Optional
from decimal import Decimal
from datetime import datetime,timedelta,timezone
import hashlib
import string
import random
import uuid
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from utils.unique_identifier_funcs import normalize_mobile_number, parse_children_ages, generate_unique_identifier
from utils.helpers import calculate_expected_savings,update_compliance_score, calculate_monthly_scores, add_donor_contribution, add_partner_contribution, get_mother_transaction_summary, get_payment_method_statistics, calculate_monthly_saving_streak, calculate_credit_score, get_comprehensive_savings_analytics, get_mother_total_savings_ussd, get_mother_months_saved_ussd, get_mother_latest_contributions_ussd
from utils.async_helpers import calculate_monthly_scores_async, get_scoring_progress
from utils.models import Mother, MotherActivity, MotherPartnerActivity, MonthlySavings, MonthlyActivityModel, Partners, Donors,DonorContributions,PartnerSubscriptions, PartnerContributions, SavingsTransaction, SavingReminder, Base
from utils.verification import generate_verification_code, store_verification_code, validate_verification_code, generate_token, send_verification_email

DATABASE_URL = "postgresql://cariyadb_damb_user:LLM87f54JeWhIfyHBDSKJogoPqc93jrW@dpg-d28s0druibrs73dt691g-a.oregon-postgres.render.com/cariyadb_damb"
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in environment variables")

# Database connection with proper pool configuration
engine = create_engine(
    DATABASE_URL,
    pool_size=20,  # Increased pool size for better concurrency
    max_overflow=30,  # Allow additional connections when pool is full
    pool_pre_ping=True,  # Validate connections before use
    pool_recycle=3600,  # Recycle connections every hour
    pool_timeout=30,  # Timeout for getting connection from pool
    echo=False  # Set to True for SQL debugging
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cariya Wallet API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for background tasks
executor = ThreadPoolExecutor(max_workers=4)

# Global flag to track scoring job status
scoring_job_running = False
scoring_job_lock = threading.Lock()

def generate_transaction_id() -> str:
    """Generate a unique transaction ID for savings transactions."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_suffix = str(uuid.uuid4())[:8]
    return f"SAV{timestamp}{random_suffix}"

verification_codes = {}
partners = [
    {
        "partner_id": "1",
        "partner_name": "Sample Partner",
        "email": "partner@example.com",
        "phone_number": "+1234567890",
        "mother_count": 10,
        "total_contributions": 100000,
        "activities": []
    }
]

class PartnerLoginRequest(BaseModel):
    email: Optional[str] = None
    phone_number: Optional[str] = None

class VerifyCodeRequest(BaseModel):
    method: str
    identifier: str
    code: str

# Pydantic models
class AddPartner(BaseModel):
    partner_name: str
    description: Union[str, None]
    location: str
    total_members: int = 0
    tel_number: Union[str, None]
    email: Union[str, None]

    @field_validator("partner_name")
    @classmethod
    def validate_partner_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Partner name cannot be empty")
        if len(v) > 100:
            raise ValueError("Partner name must be 100 characters or less")
        return v.strip()

    @field_validator("location")
    @classmethod
    def validate_location(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Location cannot be empty")
        if len(v) > 100:
            raise ValueError("Location must be 100 characters or less")
        return v.strip()

    @field_validator("total_members")
    @classmethod
    def validate_total_members(cls, v):
        if v < 0:
            raise ValueError("Total members must be non-negative")
        return v

    @field_validator("tel_number")
    @classmethod
    def validate_tel_number(cls, v):
        if v is None:
            return v
        if not v.startswith("+256") or len(v) != 13 or not v[4:].isdigit():
            raise ValueError("Telephone number must be in the format +256XXXXXXXXX")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if v is None:
            return v
        if len(v) > 255 or not v or "@" not in v or "." not in v:
            raise ValueError("Invalid email format")
        return v.strip()

class AddPartnerSubscription(BaseModel):
    partner_id: str
    subscription_tier: str
    payment_details: Union[str, None]

    @field_validator("partner_id")
    @classmethod
    def validate_partner_id(cls, v):
        if len(v) > 50:
            raise ValueError("Partner ID must be 50 characters or less")
        return v

    @field_validator("subscription_tier")
    @classmethod
    def validate_subscription_tier(cls, v):
        valid_tiers = ["Basic", "Gold", "Platinum"]
        if v not in valid_tiers:
            raise ValueError(f"Subscription tier must be one of {valid_tiers}")
        return v

class UpdatePartnerSubscription(BaseModel):
    subscription_tier: Union[str, None]
    subscription_status: Union[str, None]
    payment_details: Union[str, None]
    end_date: Union[datetime, None]

    @field_validator("subscription_tier")
    @classmethod
    def validate_subscription_tier(cls, v):
        if v is None:
            return v
        valid_tiers = ["Basic", "Gold", "Platinum"]
        if v not in valid_tiers:
            raise ValueError(f"Subscription tier must be one of {valid_tiers}")
        return v

    @field_validator("subscription_status")
    @classmethod
    def validate_subscription_status(cls, v):
        if v is None:
            return v
        valid_statuses = ["active", "inactive", "pending", "expired"]
        if v not in valid_statuses:
            raise ValueError(f"Subscription status must be one of {valid_statuses}")
        return v

class AddPartnerContribution(BaseModel):
    mother_id: str
    partner_id: str
    month_key: str
    amount: float

    @field_validator("mother_id", "partner_id")
    @classmethod
    def validate_id(cls, v):
        if len(v) > 50:
            raise ValueError("ID must be 50 characters or less")
        return v

    @field_validator("month_key")
    @classmethod
    def validate_month_key(cls, v):
        if not re.match(r"^\d{4}-[0-1][0-9]$", v):
            raise ValueError("Invalid month_key format. Expected YYYY-MM")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        if v < 0:
            raise ValueError("Amount must be non-negative")
        return v

class AddDonor(BaseModel):
    first_name: str
    surname: str
    email: str
    country_of_residence: Union[str, None]
    preferred_activities: Union[List[str], None]

    @field_validator("first_name", "surname")
    @classmethod
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Name cannot be empty")
        if len(v) > 100:
            raise ValueError("Name must be 100 characters or less")
        return v.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if len(v) > 255 or not v or "@" not in v or "." not in v:
            raise ValueError("Invalid email format")
        return v.strip()

    @field_validator("country_of_residence")
    @classmethod
    def validate_country(cls, v):
        if v is None:
            return v
        if len(v) > 100:
            raise ValueError("Country of residence must be 100 characters or less")
        return v.strip()

class UpdateDonor(BaseModel):
    first_name: Union[str, None]
    surname: Union[str, None]
    email: Union[str, None]
    country_of_residence: Union[str, None]
    preferred_activities: Union[List[str], None]

    @field_validator("first_name", "surname")
    @classmethod
    def validate_name(cls, v):
        if v is None:
            return v
        if len(v.strip()) == 0:
            raise ValueError("Name cannot be empty")
        if len(v) > 100:
            raise ValueError("Name must be 100 characters or less")
        return v.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if v is None:
            return v
        if len(v) > 255 or not v or "@" not in v or "." not in v:
            raise ValueError("Invalid email format")
        return v.strip()

    @field_validator("country_of_residence")
    @classmethod
    def validate_country(cls, v):
        if v is None:
            return v
        if len(v) > 100:
            raise ValueError("Country of residence must be 100 characters or less")
        return v.strip()


class AddDonation(BaseModel):
    mother_id: str
    donor_email: str
    month_key: str
    amount: float

    @field_validator("mother_id")
    @classmethod
    def validate_mother_id(cls, v):
        if len(v) > 50:
            raise ValueError("Mother ID must be 50 characters or less")
        return v

    @field_validator("donor_email")
    @classmethod
    def validate_email(cls, v):
        if len(v) > 255 or not v or "@" not in v or "." not in v:
            raise ValueError("Invalid email format")
        return v.strip()

    @field_validator("month_key")
    @classmethod
    def validate_month_key(cls, v):
        if not re.match(r"^\d{4}-[0-1][0-9]$", v):
            raise ValueError("Invalid month_key format. Expected YYYY-MM")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        if v < 0:
            raise ValueError("Amount must be non-negative")
        return v

class AddActivity(BaseModel):
    partner_id: str
    name: str
    description: Union[str, None]
    num_people: int = 0

    @field_validator("partner_id")
    @classmethod
    def validate_partner_id(cls, v):
        if len(v) > 50:
            raise ValueError("Partner ID must be 50 characters or less")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Activity name cannot be empty")
        if len(v) > 100:
            raise ValueError("Activity name must be 100 characters or less")
        return v.strip()

    @field_validator("num_people")
    @classmethod
    def validate_num_people(cls, v):
        if v < 0:
            raise ValueError("Number of people must be non-negative")
        return v

class AddMother(BaseModel):
    first_name: str
    surname: str
    mobile_number: str
    num_children: int
    ages_of_children_per_birth: str  # Expected format: "2" or "2/9" or "3/6/7" etc.
    partner_id: Union[str, None]
    location: Union[str, None]
    activity_id: str

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, v):
        normalized = normalize_mobile_number(v)
        if not normalized.startswith("+256") or len(normalized) != 13:
            raise ValueError("Mobile number must be in the format +256XXXXXXXXX")
        return normalized

    @field_validator("num_children")
    @classmethod
    def validate_num_children(cls, v):
        if v < 0:
            raise ValueError("Number of children must be non-negative")
        return v

    @field_validator("ages_of_children_per_birth")
    @classmethod
    def validate_ages_format(cls, v, values):
        if not v or not v.strip():
            raise ValueError("Ages of children cannot be empty")
        if not v.replace("/", "").isdigit():
            raise ValueError("Ages must contain only digits and slashes")
        ages = v.split("/")
        if not all(a.isdigit() and 0 <= int(a) <= 18 for a in ages):
            raise ValueError("Each age must be a number between 0 and 18")
        num_children = values.data.get("num_children", 0)
        if len(ages) != num_children:
            raise ValueError(f"Number of ages ({len(ages)}) must match num_children ({num_children})")
        return v

class MonthlyActivity(BaseModel):
    activity_id: str
    month: int

class SavingsEntry(BaseModel):
    amount: float
    month: Union[int, None]
    phone_number: str
    payment_method: str
    reference_number: Union[str, None] = None
    notes: Union[str, None] = None

class SavingReminderRequest(BaseModel):
    reminder_date: int
    
    @field_validator("reminder_date")
    @classmethod
    def validate_reminder_date(cls, v):
        if v < 1 or v > 31:
            raise ValueError("Reminder date must be between 1 and 31")
        return v

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Scheduler setup - using AsyncIOScheduler for better integration
scheduler = AsyncIOScheduler()

async def run_scoring_job_async():
    """Run the scoring job asynchronously to prevent blocking."""
    global scoring_job_running
    
    with scoring_job_lock:
        if scoring_job_running:
            print("Scoring job already running, skipping...")
            return
        scoring_job_running = True
    
    try:
        # Run the scoring job in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        current_month = datetime.now().month
        
        def scoring_worker():
            """Worker function to run scoring in separate thread."""
            db = SessionLocal()
            try:
                calculate_monthly_scores(db, target_month=current_month)
                print(f"Scoring job executed successfully for month {current_month}")
                return True
            except Exception as e:
                print(f"Error running scoring job: {str(e)}")
                return False
            finally:
                db.close()
        
        # Execute in thread pool
        result = await loop.run_in_executor(executor, scoring_worker)
        if result:
            print(f"Scoring job completed successfully for month {current_month}")
        else:
            print(f"Scoring job failed for month {current_month}")
            
    except Exception as e:
        print(f"Error in async scoring job: {str(e)}")
    finally:
        with scoring_job_lock:
            scoring_job_running = False

def run_scoring_job():
    """Synchronous wrapper for the async scoring job."""
    asyncio.create_task(run_scoring_job_async())

# Schedule the scoring job to run every 30 minutes
scheduler.add_job(run_scoring_job, "interval", minutes=30)
scheduler.start()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_day_suffix(day: int) -> str:
    """Get the appropriate suffix for a day number (1st, 2nd, 3rd, etc.)."""
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return suffix

# =============================================================================
# PARTNER MANAGEMENT DOCKET
# =============================================================================

@app.post("/partner/login", tags=["Partner Management"])
async def partner_login(request: PartnerLoginRequest, db: Session = Depends(get_db)):
    if not request.email and not request.phone_number:
        raise HTTPException(status_code=400, detail="Email or phone number is required")
    
    identifier = request.email or request.phone_number
    partner = db.query(Partners).filter(
        (Partners.email == request.email) | (Partners.tel_number == request.phone_number)
    ).first()
    
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    
    code = generate_verification_code()
    store_verification_code(identifier, code)
    print(f"Generated verification code {code} for {identifier}")  # For testing
    
    return {
        "message": "Verification code generated",
        "partner_id": partner.partner_id,
        "partner_name": partner.partner_name
    }
@app.post("/partner/verify", tags=["Partner Management"])
async def verify_partner(request: VerifyCodeRequest):
    if request.method not in ["email", "phone"]:
        raise HTTPException(status_code=400, detail="Invalid method")
    
    if not validate_verification_code(request.identifier, request.code):
        raise HTTPException(status_code=401, detail="Invalid or expired code")
    
    partner = next((p for p in partners if p["email"] == request.identifier or p["phone_number"] == request.identifier), None)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    
    token = generate_token(partner["partner_id"])
    return {"partner_id": partner["partner_id"], "token": token}


@app.post("/addPartner", tags=["Partner Management"])
async def add_partner(partner_data: AddPartner, db: Session = Depends(get_db)):
    """Add a new partner to the partners table."""
    try:
        if db.query(Partners).filter(Partners.partner_name == partner_data.partner_name).first():
            raise HTTPException(status_code=400, detail=f"Partner name '{partner_data.partner_name}' already exists")
        if partner_data.email and db.query(Partners).filter(Partners.email == partner_data.email).first():
            raise HTTPException(status_code=400, detail=f"Email '{partner_data.email}' already exists")

        partner_id = str(uuid.uuid4())
        partner = Partners(
            partner_id=partner_id,
            partner_name=partner_data.partner_name,
            description=partner_data.description,
            location=partner_data.location,
            total_members=partner_data.total_members,
            tel_number=partner_data.tel_number,
            email=partner_data.email,
        )
        db.add(partner)
        db.commit()
        db.refresh(partner)
        return {"message": "Partner added successfully", "partner_id": partner_id}
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/partners", tags=["Partner Management"])
async def get_partners(db: Session = Depends(get_db)):
    """Retrieve all partners with their activities, subscriptions, and number of associated mothers."""
    try:
        partners = db.query(Partners).all()
        if not partners:
            return {"message": "No partners found"}
        result = []
        for p in partners:
            subscription = db.query(PartnerSubscriptions).filter(PartnerSubscriptions.partner_id == p.partner_id).first()
            activities = db.query(MotherActivity).filter(MotherActivity.partner_id == p.partner_id).all()
            mother_count = db.query(Mother).filter(Mother.partner_id == p.partner_id).count()
            total_contributions = sum(float(c.amount) for c in db.query(PartnerContributions).filter(PartnerContributions.partner_id == p.partner_id).all())
            result.append({
                "partner_id": p.partner_id,
                "partner_name": p.partner_name,
                "description": p.description,
                "location": p.location,
                "total_members": p.total_members,
                "tel_number": p.tel_number,
                "email": p.email,
                "subscription": {
                    "subscription_id": subscription.subscription_id,
                    "subscription_tier": subscription.subscription_tier,
                    "subscription_status": subscription.subscription_status,
                    "start_date": subscription.start_date,
                    "end_date": subscription.end_date
                } if subscription else None,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
                "activities": [
                    {
                        "activity_id": a.activity_id,
                        "name": a.name,
                        "description": a.description,
                        "num_people": a.num_people
                    } for a in activities
                ],
                "mother_count": mother_count,
                "total_contributions": total_contributions
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/addPartnerSubscription", tags=["Partner Management"])
async def add_partner_subscription(subscription_data: AddPartnerSubscription, db: Session = Depends(get_db)):
    """Add a new subscription for a partner."""
    try:
        partner = db.query(Partners).filter(Partners.partner_id == subscription_data.partner_id).first()
        if not partner:
            raise HTTPException(status_code=404, detail=f"Partner with ID '{subscription_data.partner_id}' not found")
        if db.query(PartnerSubscriptions).filter(PartnerSubscriptions.partner_id == subscription_data.partner_id).first():
            raise HTTPException(status_code=400, detail=f"Subscription already exists for partner {subscription_data.partner_id}")

        subscription_id = str(uuid.uuid4())
        subscription = PartnerSubscriptions(
            subscription_id=subscription_id,
            partner_id=subscription_data.partner_id,
            subscription_tier=subscription_data.subscription_tier,
            subscription_status="pending",
            payment_details=subscription_data.payment_details
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)
        return {"message": "Subscription added successfully", "subscription_id": subscription_id}
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.put("/partnerSubscriptions/{subscription_id}", tags=["Partner Management"])
async def update_partner_subscription(subscription_id: str, subscription_data: UpdatePartnerSubscription, db: Session = Depends(get_db)):
    """Update a partner's subscription details."""
    try:
        subscription = db.query(PartnerSubscriptions).filter(PartnerSubscriptions.subscription_id == subscription_id).first()
        if not subscription:
            raise HTTPException(status_code=404, detail=f"No subscription found with ID {subscription_id}")

        if subscription_data.subscription_tier:
            subscription.subscription_tier = subscription_data.subscription_tier
        if subscription_data.subscription_status:
            subscription.subscription_status = subscription_data.subscription_status
        if subscription_data.payment_details is not None:
            subscription.payment_details = subscription_data.payment_details
        if subscription_data.end_date:
            subscription.end_date = subscription_data.end_date
        subscription.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(subscription)
        return {"message": f"Subscription {subscription_id} updated successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/partnerSubscriptions/{partner_id}", tags=["Partner Management"])
async def get_partner_subscription(partner_id: str, db: Session = Depends(get_db)):
    """Retrieve a partner's subscription details."""
    try:
        subscription = db.query(PartnerSubscriptions).filter(PartnerSubscriptions.partner_id == partner_id).first()
        if not subscription:
            return {"message": f"No subscription found for partner {partner_id}"}
        return {
            "subscription_id": subscription.subscription_id,
            "partner_id": subscription.partner_id,
            "subscription_tier": subscription.subscription_tier,
            "subscription_status": subscription.subscription_status,
            "start_date": subscription.start_date,
            "end_date": subscription.end_date,
            "payment_details": subscription.payment_details,
            "created_at": subscription.created_at,
            "updated_at": subscription.updated_at
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/addPartnerContribution", tags=["Partner Management"])
async def add_partner_contribution(contribution_data: AddPartnerContribution, db: Session = Depends(get_db)):
    """Add a partner match funding contribution for a specific mother and month."""
    try:
        result = add_partner_contribution(db, contribution_data.mother_id, contribution_data.partner_id, contribution_data.month_key, contribution_data.amount)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/partners/{partner_id}/contributions", tags=["Partner Management"])
async def get_partner_contributions(partner_id: str, db: Session = Depends(get_db)):
    """Retrieve all match funding contributions made by a specific partner."""
    try:
        partner = db.query(Partners).filter(Partners.partner_id == partner_id).first()
        if not partner:
            raise HTTPException(status_code=404, detail=f"No partner found with ID {partner_id}")
        contributions = db.query(PartnerContributions).filter(PartnerContributions.partner_id == partner_id).all()
        if not contributions:
            return {"message": f"No contributions found for partner {partner_id}"}
        return [
            {
                "id": c.id,
                "mother_id": c.mother_id,
                "month_key": c.month_key,
                "amount": float(c.amount),
                "created_at": c.created_at,
                "updated_at": c.updated_at
            }
            for c in contributions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/partners/{partner_id}", tags=["Partner Management"])
async def get_partner_profile(partner_id: str, db: Session = Depends(get_db)):
    """Retrieve a partner's profile by ID with their activities, subscription, and number of associated mothers."""
    try:
        partner = db.query(Partners).filter(Partners.partner_id == partner_id).first()
        if not partner:
            raise HTTPException(status_code=404, detail=f"No partner found with ID {partner_id}")
        subscription = db.query(PartnerSubscriptions).filter(PartnerSubscriptions.partner_id == partner_id).first()
        activities = db.query(MotherActivity).filter(MotherActivity.partner_id == partner_id).all()
        mother_count = db.query(Mother).filter(Mother.partner_id == partner_id).count()
        total_contributions = sum(float(c.amount) for c in db.query(PartnerContributions).filter(PartnerContributions.partner_id == partner_id).all())
        return {
            "partner_id": partner.partner_id,
            "partner_name": partner.partner_name,
            "description": partner.description,
            "location": partner.location,
            "total_members": partner.total_members,
            "tel_number": partner.tel_number,
            "email": partner.email,
            "subscription": {
                "subscription_id": subscription.subscription_id,
                "subscription_tier": subscription.subscription_tier,
                "subscription_status": subscription.subscription_status,
                "start_date": subscription.start_date,
                "end_date": subscription.end_date
            } if subscription else None,
            "created_at": partner.created_at,
            "updated_at": partner.updated_at,
            "activities": [
                {
                    "activity_id": a.activity_id,
                    "name": a.name,
                    "description": a.description,
                    "num_people": a.num_people
                } for a in activities
            ],
            "mother_count": mother_count,
            "total_contributions": total_contributions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# =============================================================================
# ACTIVITY MANAGEMENT DOCKET
# =============================================================================

@app.get("/partners/{partner_id}/activities", tags=["Partner Management"])
async def get_activities_by_partner(partner_id: str, db: Session = Depends(get_db)):
    """Retrieve activities associated with a specific partner."""
    try:
        activities = db.query(MotherActivity).filter(MotherActivity.partner_id == partner_id).all()
        if not activities:
            return {"message": f"No activities found for partner with ID {partner_id}"}
        return [{"activity_id": a.activity_id, "name": a.name, "description": a.description, "num_people": a.num_people} for a in activities]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/addActivity", tags=["Activity Management"])
async def add_activity(activity_data: AddActivity, db: Session = Depends(get_db)):
    """Add a new activity to the mother_activities table."""
    try:
        partner = db.query(Partners).filter(Partners.partner_id == activity_data.partner_id).first()
        if not partner:
            raise HTTPException(status_code=404, detail=f"Partner with ID '{activity_data.partner_id}' not found")
        if db.query(MotherActivity).filter(
            MotherActivity.partner_id == activity_data.partner_id,
            MotherActivity.name == activity_data.name
        ).first():
            raise HTTPException(status_code=400, detail=f"Activity name '{activity_data.name}' already exists for this partner")

        activity_id = str(uuid.uuid4())
        activity = MotherActivity(
            activity_id=activity_id,
            partner_id=activity_data.partner_id,
            name=activity_data.name,
            description=activity_data.description,
            num_people=activity_data.num_people,
        )
        db.add(activity)
        db.commit()
        db.refresh(activity)
        return {"message": "Activity added successfully", "activity_id": activity_id}
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/activities", tags=["Activity Management"])
async def get_activities(db: Session = Depends(get_db)):
    """Retrieve all activities."""
    try:
        activities = db.query(MotherActivity).all()
        if not activities:
            return {"message": "No activities found"}
        return [{"activity_id": a.activity_id, "name": a.name, "description": a.description, "num_people": a.num_people, "partner_id": a.partner_id} for a in activities]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# =============================================================================
# DONOR MANAGEMENT DOCKET
# =============================================================================

@app.post("/addDonor", tags=["Donor Management"])
async def add_donor(donor_data: AddDonor, db: Session = Depends(get_db)):
    """Add a new donor to the donors table."""
    try:
        if db.query(Donors).filter(Donors.email == donor_data.email).first():
            raise HTTPException(status_code=400, detail=f"Email '{donor_data.email}' already exists")

        donor_id = str(uuid.uuid4())
        donor = Donors(
            donor_id=donor_id,
            first_name=donor_data.first_name,
            surname=donor_data.surname,
            email=donor_data.email,
            country_of_residence=donor_data.country_of_residence,
            preferred_activities=donor_data.preferred_activities,
            total_contributions=0.0
        )
        db.add(donor)
        db.commit()
        db.refresh(donor)
        return {"message": "Donor added successfully", "donor_id": donor_id}
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/donors", tags=["Donor Management"])
async def get_donors(db: Session = Depends(get_db)):
    """Retrieve all donors with their associated mother ID, total contributions, and mother profile."""
    try:
        donors = db.query(Donors).all()
        if not donors:
            return {"message": "No donors found"}
        result = []
        for d in donors:
            # Fetch mother associated with the donor
            mother = db.query(Mother).filter(Mother.donor_id == d.donor_id).first()
            mother_profile = None
            mother_id = None
            if mother:
                mother_id = mother.generated_id
                # Fetch activities for the mother
                mother_activities = db.query(MotherPartnerActivity).filter(MotherPartnerActivity.mother_id == mother.generated_id).all()
                activities = []
                for ma in mother_activities:
                    activity = db.query(MotherActivity).filter(MotherActivity.activity_id == ma.activity_id).first()
                    if activity:
                        activities.append({
                            "activity_id": activity.activity_id,
                            "name": activity.name,
                            "description": activity.description,
                            "num_people": activity.num_people
                        })
                # Fetch monthly savings sum
                monthly_savings = db.query(MonthlySavings).filter(MonthlySavings.mother_id == mother.generated_id).all()
                total_savings = sum(float(saving.savings) for saving in monthly_savings)
                # Fetch compliance score - always out of 24 (2 points × 12 months)
                compliance_score = f"{mother.compliance_score}/24"
                mother_profile = {
                    "generated_id": mother.generated_id,
                    "first_name": mother.first_name,
                    "surname": mother.surname,
                    "mobile_number": mother.mobile_number,
                    "num_children": mother.num_children,
                    "activities": activities,
                    "compliance_score": compliance_score,
                    "total_monthly_savings": total_savings
                }
            result.append({
                "donor_id": d.donor_id,
                "first_name": d.first_name,
                "surname": d.surname,
                "email": d.email,
                "country_of_residence": d.country_of_residence,
                "preferred_activities": d.preferred_activities,
                "total_contributions": float(d.total_contributions),
                "created_at": d.created_at,
                "updated_at": d.updated_at,
                "mother_id": mother_id,
                "mother_profile": mother_profile
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/donors/{donor_id}", tags=["Donor Management"])
async def get_donor_profile(donor_id: str, db: Session = Depends(get_db)):
    """Retrieve a donor's profile by ID with associated mother ID, total contributions, and mother profile."""
    try:
        donor = db.query(Donors).filter(Donors.donor_id == donor_id).first()
        if not donor:
            raise HTTPException(status_code=404, detail=f"No donor found with ID {donor_id}")
        # Fetch mother associated with the donor
        mother = db.query(Mother).filter(Mother.donor_id == donor_id).first()
        mother_profile = None
        mother_id = None
        if mother:
            mother_id = mother.generated_id
            # Fetch activities for the mother
            mother_activities = db.query(MotherPartnerActivity).filter(MotherPartnerActivity.mother_id == mother.generated_id).all()
            activities = []
            for ma in mother_activities:
                activity = db.query(MotherActivity).filter(MotherActivity.activity_id == ma.activity_id).first()
                if activity:
                    activities.append({
                        "activity_id": activity.activity_id,
                        "name": activity.name,
                        "description": activity.description,
                        "num_people": activity.num_people
                    })
            # Fetch monthly savings sum
            monthly_savings = db.query(MonthlySavings).filter(MonthlySavings.mother_id == mother.generated_id).all()
            total_savings = sum(float(saving.savings) for saving in monthly_savings)
            # Fetch compliance score - always out of 24 (2 points × 12 months)
            compliance_score = f"{mother.compliance_score}/24"
            mother_profile = {
                "generated_id": mother.generated_id,
                "first_name": mother.first_name,
                "surname": mother.surname,
                "mobile_number": mother.mobile_number,
                "num_children": mother.num_children,
                "activities": activities,
                "compliance_score": compliance_score,
                "total_monthly_savings": total_savings
            }
        return {
            "donor_id": donor.donor_id,
            "first_name": donor.first_name,
            "surname": donor.surname,
            "email": donor.email,
            "country_of_residence": donor.country_of_residence,
            "preferred_activities": donor.preferred_activities,
            "total_contributions": float(donor.total_contributions),
            "created_at": donor.created_at,
            "updated_at": donor.updated_at,
            "mother_id": mother_id,
            "mother_profile": mother_profile
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.put("/donors/{donor_id}", tags=["Donor Management"])
async def update_donor(donor_id: str, donor_data: UpdateDonor, db: Session = Depends(get_db)):
    """Update a donor's details."""
    try:
        donor = db.query(Donors).filter(Donors.donor_id == donor_id).first()
        if not donor:
            raise HTTPException(status_code=404, detail=f"No donor found with ID {donor_id}")
        if donor_data.email and donor_data.email != donor.email and db.query(Donors).filter(Donors.email == donor_data.email).first():
            raise HTTPException(status_code=400, detail=f"Email '{donor_data.email}' already exists")

        if donor_data.first_name:
            donor.first_name = donor_data.first_name
        if donor_data.surname:
            donor.surname = donor_data.surname
        if donor_data.email:
            donor.email = donor_data.email
        if donor_data.country_of_residence:
            donor.country_of_residence = donor_data.country_of_residence
        if donor_data.preferred_activities is not None:
            donor.preferred_activities = donor_data.preferred_activities
        donor.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(donor)
        return {"message": f"Donor {donor_id} updated successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.delete("/donors/{donor_id}", tags=["Donor Management"])
async def delete_donor(donor_id: str, db: Session = Depends(get_db)):
    """Delete a donor if not assigned to any mother."""
    try:
        donor = db.query(Donors).filter(Donors.donor_id == donor_id).first()
        if not donor:
            raise HTTPException(status_code=404, detail=f"No donor found with ID {donor_id}")
        if db.query(Mother).filter(Mother.donor_id == donor_id).first():
            raise HTTPException(status_code=400, detail=f"Donor {donor_id} is assigned to a mother and cannot be deleted")
        db.delete(donor)
        db.commit()
        return {"message": f"Donor {donor_id} deleted successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/donors/{donor_id}/donations", tags=["Donor Management"])
async def get_donor_donations(donor_id: str, db: Session = Depends(get_db)):
    """Retrieve all donations made by a specific donor."""
    try:
        donor = db.query(Donors).filter(Donors.donor_id == donor_id).first()
        if not donor:
            raise HTTPException(status_code=404, detail=f"No donor found with ID {donor_id}")
        donations = db.query(DonorContributions).filter(DonorContributions.donor_id == donor_id).all()
        if not donations:
            return {"message": f"No donations found for donor {donor_id}"}
        return [
            {
                "id": d.id,
                "mother_id": d.mother_id,
                "month_key": d.month_key,
                "amount": float(d.amount),
                "created_at": d.created_at,
                "updated_at": d.updated_at
            }
            for d in donations
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/addDonation", tags=["Donor Management"])
async def add_donation(donation_data: AddDonation, db: Session = Depends(get_db)):
    """Add a donor contribution for a specific mother and month."""
    try:
        result = add_donor_contribution(db, donation_data.mother_id, donation_data.donor_email, donation_data.month_key, donation_data.amount)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}/donations", tags=["Mother Management"])
async def get_mother_donations(mother_id: str, db: Session = Depends(get_db)):
    """Retrieve all donations for a specific mother."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise HTTPException(status_code=404, detail=f"No mother found with ID {mother_id}")
        donations = db.query(DonorContributions).filter(DonorContributions.mother_id == mother_id).all()
        if not donations:
            return {"message": f"No donations found for mother {mother_id}"}
        return [
            {
                "id": d.id,
                "donor_id": d.donor_id,
                "month_key": d.month_key,
                "amount": float(d.amount),
                "created_at": d.created_at,
                "updated_at": d.updated_at
            }
            for d in donations
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# =============================================================================
# MOTHER MANAGEMENT DOCKET
# =============================================================================

@app.post("/addMother", tags=["Mother Management"])
async def add_mother(mother_data: AddMother, db: Session = Depends(get_db)):
    """Add a new mother and link to an existing activity via mother_partner_activities."""
    try:
        ages = parse_children_ages(mother_data.ages_of_children_per_birth)
        if len(ages) != mother_data.num_children:
            raise HTTPException(status_code=400, detail="Number of children must match ages provided")

        generated_id = generate_unique_identifier(
            mother_data.first_name,
            mother_data.surname,
            mother_data.mobile_number,
            mother_data.num_children,
            mother_data.ages_of_children_per_birth
        )

        if db.query(Mother).filter(Mother.mobile_number == mother_data.mobile_number).first():
            raise HTTPException(status_code=400, detail=f"Mobile number {mother_data.mobile_number} is already registered")
        if db.query(Mother).filter(Mother.generated_id == generated_id).first():
            raise HTTPException(status_code=400, detail=f"Mother with ID {generated_id} already exists")

        if mother_data.partner_id:
            partner = db.query(Partners).filter(Partners.partner_id == mother_data.partner_id).first()
            if not partner:
                raise HTTPException(status_code=404, detail=f"Partner with ID {mother_data.partner_id} not found")

        activity = db.query(MotherActivity).filter(MotherActivity.activity_id == mother_data.activity_id).first()
        if not activity:
            raise HTTPException(status_code=404, detail=f"Activity with ID {mother_data.activity_id} not found")

        activity.num_people += 1

        mother = Mother(
            generated_id=generated_id,
            first_name=mother_data.first_name,
            surname=mother_data.surname,
            mobile_number=mother_data.mobile_number,
            num_children=mother_data.num_children,
            ages_of_children=ages,
            partner_id=mother_data.partner_id,
            location=mother_data.location,
            activity_points=0,
            savings=0.0,
            milestone_score=0,
            compliance_score=0,
            donor_contributions=0.0,
            donor_id=None  # Explicitly set to None to prevent automatic assignment
        )
        db.add(mother)
        db.commit()
        db.refresh(mother)

        if db.query(MotherPartnerActivity).filter(
            MotherPartnerActivity.mother_id == generated_id,
            MotherPartnerActivity.activity_id == mother_data.activity_id
        ).first():
            raise HTTPException(status_code=400, detail=f"Mother already assigned to activity {mother_data.activity_id}")

        mother_partner_activity = MotherPartnerActivity(
            mother_id=generated_id,
            activity_id=mother_data.activity_id
        )
        db.add(mother_partner_activity)
        db.commit()
        return {"message": "Mother added successfully", "generated_id": generated_id}
    except HTTPException as e:
        raise e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers", tags=["Mother Management"])
async def get_mothers(db: Session = Depends(get_db)):
    """Retrieve all mothers with their complete profile, activities, compliance results, sum of monthly savings, and donor profile."""
    try:
        mothers = db.query(Mother).all()
        if not mothers:
            return {"message": "No mothers found"}
        result = []
        for m in mothers:
            # Fetch activities for the mother
            mother_activities = db.query(MotherPartnerActivity).filter(MotherPartnerActivity.mother_id == m.generated_id).all()
            activities = []
            for ma in mother_activities:
                activity = db.query(MotherActivity).filter(MotherActivity.activity_id == ma.activity_id).first()
                if activity:
                    activities.append({
                        "activity_id": activity.activity_id,
                        "name": activity.name,
                        "description": activity.description,
                        "num_people": activity.num_people,
                        "created_at": activity.created_at
                    })
            # Fetch monthly savings sum
            monthly_savings = db.query(MonthlySavings).filter(MonthlySavings.mother_id == m.generated_id).all()
            total_monthly_savings = sum(float(saving.savings) for saving in monthly_savings)
            # Fetch compliance score - always out of 24 (2 points × 12 months)
            compliance_score = f"{m.compliance_score}/24"
            # Fetch donor profile if exists
            donor_profile = None
            if m.donor_id:
                donor = db.query(Donors).filter(Donors.donor_id == m.donor_id).first()
                if donor:
                    donor_profile = {
                        "donor_id": donor.donor_id,
                        "first_name": donor.first_name,
                        "surname": donor.surname,
                        "email": donor.email,
                        "country_of_residence": donor.country_of_residence,
                        "preferred_activities": donor.preferred_activities,
                        "total_contributions": float(donor.total_contributions),
                        "created_at": donor.created_at,
                        "updated_at": donor.updated_at
                    }
            result.append({
                "generated_id": m.generated_id,
                "first_name": m.first_name,
                "surname": m.surname,
                "mobile_number": m.mobile_number,
                "num_children": m.num_children,
                "ages_of_children": m.ages_of_children,
                "activity_points": m.activity_points,
                "savings": float(m.savings),
                "milestone_score": m.milestone_score,
                "compliance_score": compliance_score,
                "donor_contributions": float(m.donor_contributions),
                "partner_id": m.partner_id,
                "donor_id": m.donor_id,
                "location": m.location,
                "education_level": m.education_level,
                "nin": m.nin,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
                "activities": activities,
                "total_monthly_savings": total_monthly_savings,
                "donor_profile": donor_profile
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/partners/{partner_id}/mothers", tags=["Mother Management"])
async def get_mothers_by_partner(partner_id: str, db: Session = Depends(get_db)):
    """Retrieve all mothers associated with a specific partner."""
    try:
        # First check if the partner exists
        partner = db.query(Partners).filter(Partners.partner_id == partner_id).first()
        if not partner:
            raise HTTPException(status_code=404, detail=f"No partner found with ID {partner_id}")
        
        # Get all mothers for this partner
        mothers = db.query(Mother).filter(Mother.partner_id == partner_id).all()
        if not mothers:
            return {"message": f"No mothers found for partner {partner_id}", "partner_name": partner.partner_name, "mothers": []}
        
        result = []
        for mother in mothers:
            # Fetch activities for the mother
            mother_activities = db.query(MotherPartnerActivity).filter(MotherPartnerActivity.mother_id == mother.generated_id).all()
            activities = []
            for ma in mother_activities:
                activity = db.query(MotherActivity).filter(MotherActivity.activity_id == ma.activity_id).first()
                if activity:
                    activities.append({
                        "activity_id": activity.activity_id,
                        "name": activity.name,
                        "description": activity.description,
                        "num_people": activity.num_people,
                        "created_at": activity.created_at
                    })
            
            # Fetch monthly savings sum
            monthly_savings = db.query(MonthlySavings).filter(MonthlySavings.mother_id == mother.generated_id).all()
            total_monthly_savings = sum(float(saving.savings) for saving in monthly_savings)
            
            # Fetch compliance score - always out of 24 (2 points × 12 months)
            compliance_score = f"{mother.compliance_score}/24"
            
            # Fetch donor profile if exists
            donor_profile = None
            if mother.donor_id:
                donor = db.query(Donors).filter(Donors.donor_id == mother.donor_id).first()
                if donor:
                    donor_profile = {
                        "donor_id": donor.donor_id,
                        "first_name": donor.first_name,
                        "surname": donor.surname,
                        "email": donor.email,
                        "country_of_residence": donor.country_of_residence,
                        "preferred_activities": donor.preferred_activities,
                        "total_contributions": float(donor.total_contributions),
                        "created_at": donor.created_at,
                        "updated_at": donor.updated_at
                    }
            
            result.append({
                "generated_id": mother.generated_id,
                "first_name": mother.first_name,
                "surname": mother.surname,
                "mobile_number": mother.mobile_number,
                "num_children": mother.num_children,
                "ages_of_children": mother.ages_of_children,
                "activity_points": mother.activity_points,
                "savings": float(mother.savings),
                "milestone_score": mother.milestone_score,
                "compliance_score": compliance_score,
                "donor_contributions": float(mother.donor_contributions),
                "partner_id": mother.partner_id,
                "donor_id": mother.donor_id,
                "location": mother.location,
                "education_level": mother.education_level,
                "nin": mother.nin,
                "created_at": mother.created_at,
                "updated_at": mother.updated_at,
                "activities": activities,
                "total_monthly_savings": total_monthly_savings,
                "donor_profile": donor_profile
            })
        
        return {
            "partner_id": partner_id,
            "partner_name": partner.partner_name,
            "mother_count": len(result),
            "mothers": result
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}", tags=["Mother Management"])
async def get_mother_info(mother_id: str, db: Session = Depends(get_db)):
    """Retrieve mother information with activities, compliance results, sum of monthly savings, and donor profile."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise HTTPException(status_code=404, detail=f"No mother found with unique identifier {mother_id}")

        monthly_savings = db.query(MonthlySavings).filter(MonthlySavings.mother_id == mother_id).all()
        monthly_data = {saving.month_key: {
            "savings": float(saving.savings),
            "milestone_score": saving.milestone_score,
            "donor_contribution": float(saving.donor_contribution)
        } for saving in monthly_savings}
        total_savings = sum(float(saving.savings) for saving in monthly_savings)

        # Fetch activities for the mother
        mother_activities = db.query(MotherPartnerActivity).filter(MotherPartnerActivity.mother_id == mother_id).all()
        activities = []
        for ma in mother_activities:
            activity = db.query(MotherActivity).filter(MotherActivity.activity_id == ma.activity_id).first()
            if activity:
                activities.append({
                    "activity_id": activity.activity_id,
                    "name": activity.name,
                    "description": activity.description,
                    "num_people": activity.num_people,
                    "created_at": activity.created_at
                })

        # Fetch compliance score - always out of 24 (2 points × 12 months)
        compliance_score = f"{mother.compliance_score}/24"

        # Fetch donor profile if exists
        donor_profile = None
        if mother.donor_id:
            donor = db.query(Donors).filter(Donors.donor_id == mother.donor_id).first()
            if donor:
                donor_profile = {
                    "donor_id": donor.donor_id,
                    "first_name": donor.first_name,
                    "surname": donor.surname,
                    "email": donor.email,
                    "country_of_residence": donor.country_of_residence,
                    "preferred_activities": donor.preferred_activities,
                    "total_contributions": float(donor.total_contributions),
                    "created_at": donor.created_at,
                    "updated_at": donor.updated_at
                }

        return {
            "generated_id": mother.generated_id,
            "first_name": mother.first_name,
            "surname": mother.surname,
            "mobile_number": mother.mobile_number,
            "num_children": mother.num_children,
            "ages_of_children": mother.ages_of_children,
            "activity_points": mother.activity_points,
            "savings": float(mother.savings),
            "milestone_score": mother.milestone_score,
            "compliance_score": compliance_score,
            "donor_contributions": float(mother.donor_contributions),
            "partner_id": mother.partner_id,
            "donor_id": mother.donor_id,
            "location": mother.location,
            "education_level": mother.education_level,
            "nin": mother.nin,
            "created_at": mother.created_at,
            "updated_at": mother.updated_at,
            "activities": activities,
            "total_monthly_savings": total_savings,
            "monthly_data": monthly_data,
            "donor_profile": donor_profile
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# =============================================================================
# SAVINGS & ANALYTICS DOCKET
# =============================================================================

@app.post("/mothers/{mother_id}/savings", tags=["Savings & Analytics"])
async def add_savings(mother_id: str, savings_data: SavingsEntry, db: Session = Depends(get_db)):
    """Add savings for a mother in the specified month with transaction tracking."""
    try:
        if savings_data.amount < 0:
            raise HTTPException(status_code=400, detail="Savings amount cannot be negative")

        # Validate payment method
        valid_payment_methods = ["Mobile Money", "Bank Transfer", "Cash", "Card", "Other"]
        if savings_data.payment_method not in valid_payment_methods:
            raise HTTPException(status_code=400, detail=f"Invalid payment method. Must be one of: {valid_payment_methods}")

        # Validate phone number format
        if not savings_data.phone_number.startswith("+256") or len(savings_data.phone_number) != 13:
            raise HTTPException(status_code=400, detail="Phone number must be in format +256XXXXXXXXX")

        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise HTTPException(status_code=404, detail=f"No mother found with unique identifier {mother_id}")

        expected_savings = calculate_expected_savings(mother.num_children)
        current_month = min(datetime.now().month, 4) if savings_data.month is None else savings_data.month
        if not 1 <= current_month <= 12:
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12")
        month_key = f"{datetime.now().year}-{current_month:02d}"

        amount = Decimal(str(savings_data.amount))
        
        # Create savings transaction record
        transaction_id = generate_transaction_id()
        savings_transaction = SavingsTransaction(
            transaction_id=transaction_id,
            mother_id=mother_id,
            month_key=month_key,
            amount=amount,
            phone_number=savings_data.phone_number,
            payment_method=savings_data.payment_method,
            transaction_status="completed",
            reference_number=savings_data.reference_number,
            notes=savings_data.notes
        )
        db.add(savings_transaction)

        # Update monthly savings
        savings = db.query(MonthlySavings).filter(MonthlySavings.mother_id == mother_id, MonthlySavings.month_key == month_key).first()
        if savings:
            current_savings = savings.savings
        else:
            current_savings = Decimal('0.00')
            savings = MonthlySavings(mother_id=mother_id, month_key=month_key)

        new_savings = current_savings + amount
        milestone_score = 1 if new_savings >= Decimal(str(expected_savings)) else 0
        savings.savings = new_savings
        savings.milestone_score = milestone_score

        if not savings.id:
            db.add(savings)

        # Update mother's total savings
        mother.savings += amount

        # Update compliance score
        compliance_score = update_compliance_score(db, mother_id)
        mother.compliance_score = compliance_score

        db.commit()

        return {
            "message": f"Savings added for {mother.first_name} {mother.surname} in {month_key}",
            "transaction_id": transaction_id,
            "monthly_savings": float(new_savings),
            "total_savings": float(mother.savings),
            "expected_savings": float(expected_savings),
            "milestone_score": milestone_score,
            "compliance_score": f"{compliance_score}/24",
            "payment_method": savings_data.payment_method,
            "phone_number": savings_data.phone_number
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}/monthly-savings", tags=["Savings & Analytics"])
async def get_monthly_savings(mother_id: str, db: Session = Depends(get_db)):
    """Retrieve monthly savings for a specific mother with enhanced analytics."""
    try:
        savings = db.query(MonthlySavings).filter(MonthlySavings.mother_id == mother_id).all()
        if not savings:
            return {"message": f"No savings found for mother with ID {mother_id}"}
        
        # Calculate totals and analytics
        total_savings = sum(float(s.savings) for s in savings)
        total_milestone_score = sum(s.milestone_score for s in savings)
        total_donor_contribution = sum(float(s.donor_contribution) for s in savings)
        total_partner_contribution = sum(float(s.partner_contribution) for s in savings)
        
        # Get mother info for expected savings calculation
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        expected_monthly = calculate_expected_savings(mother.num_children) if mother else 0
        total_expected = expected_monthly * len(savings) if savings else 0
        
        return {
            "mother_id": mother_id,
            "total_savings": total_savings,
            "total_expected": total_expected,
            "savings_ratio": total_savings / total_expected if total_expected > 0 else 0,
            "total_milestone_score": total_milestone_score,
            "total_donor_contribution": total_donor_contribution,
            "total_partner_contribution": total_partner_contribution,
            "monthly_breakdown": [
                {
                    "month_key": s.month_key,
                    "savings": float(s.savings),
                    "milestone_score": s.milestone_score,
                    "donor_contribution": float(s.donor_contribution),
                    "partner_contribution": float(s.partner_contribution),
                    "expected_savings": expected_monthly,
                    "met_target": float(s.savings) >= expected_monthly
                } for s in savings
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/monthly-savings", tags=["Savings & Analytics"])
async def get_all_monthly_savings(month: Union[str, None] = None, db: Session = Depends(get_db)):
    """Retrieve all monthly savings for all mothers, optionally filtered by month (YYYY-MM)."""
    try:
        if month:
            savings = db.query(MonthlySavings).filter(MonthlySavings.month_key == month).all()
        else:
            savings = db.query(MonthlySavings).all()

        if not savings:
            return {"message": "No savings found"}
        return [{"mother_id": s.mother_id, "month_key": s.month_key, "savings": float(s.savings), "milestone_score": s.milestone_score, "donor_contribution": float(s.donor_contribution)} for s in savings]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/savings-transactions", tags=["Savings & Analytics"])
async def get_savings_transactions(
    mother_id: Union[str, None] = None,
    month: Union[str, None] = None,
    payment_method: Union[str, None] = None,
    db: Session = Depends(get_db)
):
    """Retrieve savings transactions with optional filtering."""
    try:
        query = db.query(SavingsTransaction)
        
        if mother_id:
            query = query.filter(SavingsTransaction.mother_id == mother_id)
        if month:
            query = query.filter(SavingsTransaction.month_key == month)
        if payment_method:
            query = query.filter(SavingsTransaction.payment_method == payment_method)
        
        transactions = query.order_by(SavingsTransaction.created_at.desc()).all()
        
        if not transactions:
            return {"message": "No transactions found"}
        
        return [{
            "transaction_id": t.transaction_id,
            "mother_id": t.mother_id,
            "month_key": t.month_key,
            "amount": float(t.amount),
            "phone_number": t.phone_number,
            "payment_method": t.payment_method,
            "transaction_status": t.transaction_status,
            "reference_number": t.reference_number,
            "notes": t.notes,
            "created_at": t.created_at
        } for t in transactions]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/savings-transactions/{transaction_id}", tags=["Savings & Analytics"])
async def get_savings_transaction(transaction_id: str, db: Session = Depends(get_db)):
    """Retrieve a specific savings transaction by ID."""
    try:
        transaction = db.query(SavingsTransaction).filter(SavingsTransaction.transaction_id == transaction_id).first()
        if not transaction:
            raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")
        
        return {
            "transaction_id": transaction.transaction_id,
            "mother_id": transaction.mother_id,
            "month_key": transaction.month_key,
            "amount": float(transaction.amount),
            "phone_number": transaction.phone_number,
            "payment_method": transaction.payment_method,
            "transaction_status": transaction.transaction_status,
            "reference_number": transaction.reference_number,
            "notes": transaction.notes,
            "created_at": transaction.created_at,
            "updated_at": transaction.updated_at
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.put("/savings-transactions/{transaction_id}", tags=["Savings & Analytics"])
async def update_savings_transaction(
    transaction_id: str,
    transaction_data: dict,
    db: Session = Depends(get_db)
):
    """Update a savings transaction (e.g., change status, add notes)."""
    try:
        transaction = db.query(SavingsTransaction).filter(SavingsTransaction.transaction_id == transaction_id).first()
        if not transaction:
            raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")
        
        # Allow updating specific fields
        if "transaction_status" in transaction_data:
            valid_statuses = ["pending", "completed", "failed", "cancelled"]
            if transaction_data["transaction_status"] not in valid_statuses:
                raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
            transaction.transaction_status = transaction_data["transaction_status"]
        
        if "notes" in transaction_data:
            transaction.notes = transaction_data["notes"]
        
        if "reference_number" in transaction_data:
            transaction.reference_number = transaction_data["reference_number"]
        
        transaction.updated_at = datetime.utcnow()
        db.commit()
        
        return {"message": f"Transaction {transaction_id} updated successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}/saving-streak", tags=["Savings & Analytics"])
async def get_mother_saving_streak(
    mother_id: str,
    month: Union[int, None] = None,
    db: Session = Depends(get_db)
):
    """Get the monthly saving streak for a specific mother."""
    try:
        current_month = month if month else datetime.now().month
        streak_data = calculate_monthly_saving_streak(db, mother_id, current_month)
        return streak_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}/credit-score", tags=["Savings & Analytics"])
async def get_mother_credit_score(
    mother_id: str,
    month: Union[str, None] = None,
    db: Session = Depends(get_db)
):
    """Get the credit score for a specific mother."""
    try:
        credit_score_data = calculate_credit_score(db, mother_id, month)
        return credit_score_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}/savings-analytics", tags=["Savings & Analytics"])
async def get_mother_savings_analytics(
    mother_id: str,
    month: Union[str, None] = None,
    db: Session = Depends(get_db)
):
    """Get comprehensive savings analytics for a specific mother."""
    try:
        analytics = get_comprehensive_savings_analytics(db, mother_id, month)
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/savings-analytics", tags=["Savings & Analytics"])
async def get_all_savings_analytics(
    month: Union[str, None] = None,
    db: Session = Depends(get_db)
):
    """Get comprehensive savings analytics for all mothers."""
    try:
        analytics = get_comprehensive_savings_analytics(db, None, month)
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}/transaction-summary", tags=["Savings & Analytics"])
async def get_mother_transaction_summary_endpoint(
    mother_id: str,
    month: Union[str, None] = None,
    db: Session = Depends(get_db)
):
    """Get a summary of transactions for a specific mother."""
    try:
        summary = get_mother_transaction_summary(db, mother_id, month)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/payment-method-statistics", tags=["Savings & Analytics"])
async def get_payment_method_statistics_endpoint(
    month: Union[str, None] = None,
    db: Session = Depends(get_db)
):
    """Get statistics about payment methods used across all transactions."""
    try:
        stats = get_payment_method_statistics(db, month)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}/monthly-activities", tags=["Mother Management"])
async def get_monthly_activities(mother_id: str, db: Session = Depends(get_db)):
    """Retrieve monthly activities for a specific mother."""
    try:
        activities = db.query(MonthlyActivityModel).filter(MonthlyActivityModel.mother_id == mother_id).all()
        if not activities:
            return {"message": f"No activities found for mother with ID {mother_id}"}
        return [{"month_key": a.month_key, "activity_id": a.activity_id, "activity_points": a.activity_points} for a in activities]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}/compliance", tags=["Mother Management"])
async def get_compliance(mother_id: str, db: Session = Depends(get_db)):
    """Get annual compliance score."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise HTTPException(status_code=404, detail=f"No mother found with unique identifier {mother_id}")

        return {
            "first_name": mother.first_name,
            "surname": mother.surname,
            "compliance_score": f"{mother.compliance_score}/24"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# DONOR VIEW DOCKET
# =============================================================================

@app.get("/donor-view", tags=["Donor View"])
async def donor_view(db: Session = Depends(get_db)):
    """Provide a view for donors to see all mothers' savings and contributions."""
    try:
        mothers = db.query(Mother).all()
        if not mothers:
            return {"message": "No mothers found"}

        donor_data = []
        for mother in mothers:
            monthly_savings = db.query(MonthlySavings).filter(MonthlySavings.mother_id == mother.generated_id).all()
            monthly_data = {}
            total_user_savings = 0
            total_donor_contributions = float(mother.donor_contributions)

            for saving in monthly_savings:
                monthly_data[saving.month_key] = {
                    "user_savings": float(saving.savings),
                    "donor_contribution": float(saving.donor_contribution)
                }
                total_user_savings += float(saving.savings)

            donor_data.append({
                "mother_id": mother.generated_id,
                "first_name": mother.first_name,
                "surname": mother.surname,
                "total_savings": float(mother.savings),
                "total_user_savings": total_user_savings,
                "total_donor_contributions": total_donor_contributions,
                "monthly_data": monthly_data
            })

        return {"donor_view": donor_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# =============================================================================
# ADMIN & SYSTEM DOCKET
# =============================================================================

@app.post("/admin/trigger-scoring", tags=["Admin & System"])
async def trigger_scoring_job(background_tasks: BackgroundTasks):
    """Manually trigger the scoring job."""
    try:
        with scoring_job_lock:
            if scoring_job_running:
                return {"message": "Scoring job already running", "status": "running"}
        
        # Add to background tasks to prevent blocking
        background_tasks.add_task(run_scoring_job_async)
        return {"message": "Scoring job triggered successfully", "status": "triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error triggering scoring job: {str(e)}")

@app.get("/admin/scoring-status", tags=["Admin & System"])
async def get_scoring_status():
    """Get the current status of the scoring job."""
    return {
        "scoring_job_running": scoring_job_running,
        "scheduler_running": scheduler.running,
        "next_run_time": scheduler.get_jobs()[0].next_run_time if scheduler.get_jobs() else None
    }

@app.post("/admin/trigger-async-scoring", tags=["Admin & System"])
async def trigger_async_scoring_job(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Manually trigger the async scoring job for better performance."""
    try:
        with scoring_job_lock:
            if scoring_job_running:
                return {"message": "Scoring job already running", "status": "running"}
        
        # Add to background tasks to prevent blocking
        background_tasks.add_task(calculate_monthly_scores_async, db, None, executor)
        return {"message": "Async scoring job triggered successfully", "status": "triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error triggering async scoring job: {str(e)}")

@app.get("/admin/scoring-progress", tags=["Admin & System"])
async def get_scoring_progress_endpoint(db: Session = Depends(get_db)):
    """Get the current progress of scoring operations."""
    try:
        progress = await get_scoring_progress(db)
        return progress
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting scoring progress: {str(e)}")

# =============================================================================
# USSD INTERFACE DOCKET
# =============================================================================

@app.get("/ussd/mothers/{mother_id}/total-savings", tags=["USSD Interface"])
async def ussd_get_total_savings(mother_id: str, db: Session = Depends(get_db)):
    """Get mother's total savings formatted for USSD display."""
    try:
        result = get_mother_total_savings_ussd(db, mother_id)
        return result
    except Exception as e:
        return {
            "success": False,
            "message": f"Internal server error: {str(e)}",
            "ussd_text": "CON System error. Please try again later.\n0. Back to main menu"
        }

@app.get("/ussd/mothers/{mother_id}/months-saved", tags=["USSD Interface"])
async def ussd_get_months_saved(
    mother_id: str, 
    year: Union[int, None] = None,
    db: Session = Depends(get_db)
):
    """Get mother's months saved out of 12 for the year, formatted for USSD."""
    try:
        if year is None:
            year = datetime.now().year
        result = get_mother_months_saved_ussd(db, mother_id, year)
        return result
    except Exception as e:
        return {
            "success": False,
            "message": f"Internal server error: {str(e)}",
            "ussd_text": "CON System error. Please try again later.\n0. Back to main menu"
        }

@app.get("/ussd/mothers/{mother_id}/latest-contributions", tags=["USSD Interface"])
async def ussd_get_latest_contributions(
    mother_id: str,
    limit: Union[int, None] = 5,
    db: Session = Depends(get_db)
):
    """Get mother's latest contributions with amount, date, and transaction IDs formatted for USSD."""
    try:
        if limit is None or limit < 1:
            limit = 5
        elif limit > 10:  # Limit to prevent USSD overflow
            limit = 10
            
        result = get_mother_latest_contributions_ussd(db, mother_id, limit)
        return result
    except Exception as e:
        return {
            "success": False,
            "message": f"Internal server error: {str(e)}",
            "ussd_text": "CON System error. Please try again later.\n0. Back to main menu"
        }

@app.get("/ussd/mothers/{mother_id}/quick-summary", tags=["USSD Interface"])
async def ussd_get_quick_summary(mother_id: str, db: Session = Depends(get_db)):
    """Get mother's quick savings summary formatted for USSD main menu."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            return {
                "success": False,
                "message": "Mother not found",
                "ussd_text": "CON Mother not found. Please try again.\n0. Back to main menu"
            }
        
        # Get basic stats
        monthly_savings = db.query(MonthlySavings).filter(
            MonthlySavings.mother_id == mother_id
        ).all()
        
        total_saved = sum(float(s.savings) for s in monthly_savings)
        current_year = datetime.now().year
        
        # Count months saved this year
        current_year_savings = [s for s in monthly_savings if s.month_key.startswith(str(current_year))]
        months_saved_this_year = sum(1 for s in current_year_savings if s.savings > 0)
        
        # Get compliance score
        compliance_score = mother.compliance_score
        
        # Format for USSD main menu
        ussd_text = f"CON Welcome {mother.first_name}!\n"
        ussd_text += f"Total Saved: UGX {total_saved:,.0f}\n"
        ussd_text += f"Months Saved: {months_saved_this_year}/12\n"
        ussd_text += f"Compliance: {compliance_score}/24\n\n"
        ussd_text += f"1. View Total Savings\n"
        ussd_text += f"2. View Months Progress\n"
        ussd_text += f"3. Latest Contributions\n"
        ussd_text += f"4. Comprehensive Summary\n"
        ussd_text += f"5. Set Reminder\n"
        ussd_text += f"0. Exit"
        
        return {
            "success": True,
            "mother_name": f"{mother.first_name} {mother.surname}",
            "total_saved": total_saved,
            "months_saved": months_saved_this_year,
            "compliance_score": f"{compliance_score}/24",
            "ussd_text": ussd_text
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Internal server error: {str(e)}",
            "ussd_text": "CON System error. Please try again later.\n0. Exit"
        }

@app.get("/ussd/mothers/{mother_id}/comprehensive-summary", tags=["USSD Interface"])
async def ussd_get_comprehensive_summary(
    mother_id: str,
    month: Union[int, None] = None,
    db: Session = Depends(get_db)
):
    """Get mother's comprehensive summary including compliance score, monthly savings, and credit score formatted for USSD."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            return {
                "success": False,
                "message": "Mother not found",
                "ussd_text": "CON Mother not found. Please try again.\n0. Back to main menu"
            }
        
        # Get current month if not specified
        if month is None:
            month = datetime.now().month
        
        if not 1 <= month <= 12:
            return {
                "success": False,
                "message": "Invalid month",
                "ussd_text": "CON Invalid month. Please use 1-12.\n0. Back to main menu"
            }
        
        current_year = datetime.now().year
        month_key = f"{current_year}-{month:02d}"
        
        # Get compliance score
        compliance_score = mother.compliance_score
        
        # Get monthly savings for specific month
        monthly_savings = db.query(MonthlySavings).filter(
            MonthlySavings.mother_id == mother_id,
            MonthlySavings.month_key == month_key
        ).first()
        
        month_savings = 0.0
        month_milestone = 0
        month_expected = calculate_expected_savings(mother.num_children)
        
        if monthly_savings:
            month_savings = float(monthly_savings.savings)
            month_milestone = monthly_savings.milestone_score
        
        # Get credit score
        credit_score_data = calculate_credit_score(db, mother_id, month_key)
        credit_score = credit_score_data["credit_score"]
        credit_rating = credit_score_data["credit_rating"]
        
        # Format month name
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        month_name = month_names[month - 1]
        
        # Format for USSD display
        ussd_text = f"CON {month_name} {current_year} Summary\n"
        ussd_text += f"Compliance: {compliance_score}/24\n"
        ussd_text += f"Credit Score: {credit_score}/850\n"
        ussd_text += f"Rating: {credit_rating}\n\n"
        ussd_text += f"Monthly Savings:\n"
        ussd_text += f"Saved: UGX {month_savings:,.0f}\n"
        ussd_text += f"Expected: UGX {month_expected:,.0f}\n"
        
        if month_expected > 0:
            month_ratio = (month_savings / month_expected) * 100
            ussd_text += f"Progress: {month_ratio:.1f}%\n"
        
        if month_milestone == 1:
            ussd_text += f"✅ Target Met!\n"
        else:
            ussd_text += f"❌ Target Not Met\n"
        
        ussd_text += f"\n0. Back to main menu"
        
        return {
            "success": True,
            "mother_name": f"{mother.first_name} {mother.surname}",
            "month": month,
            "month_name": month_name,
            "year": current_year,
            "compliance_score": f"{compliance_score}/24",
            "credit_score": f"{credit_score}/850",
            "credit_rating": credit_rating,
            "month_savings": month_savings,
            "month_expected": month_expected,
            "month_milestone": month_milestone,
            "ussd_text": ussd_text
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Internal server error: {str(e)}",
            "ussd_text": "CON System error. Please try again later.\n0. Back to main menu"
        }

@app.post("/ussd/mothers/{mother_id}/set-reminder", tags=["USSD Interface"])
async def ussd_set_saving_reminder(
    mother_id: str,
    reminder_data: SavingReminderRequest,
    db: Session = Depends(get_db)
):
    """Set a monthly saving reminder for a mother via USSD."""
    try:
        # Verify mother exists
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            return {
                "success": False,
                "message": "Mother not found",
                "ussd_text": "CON Mother not found. Please try again.\n0. Back to main menu"
            }
        
        # Check if reminder already exists for this mother
        existing_reminder = db.query(SavingReminder).filter(
            SavingReminder.mother_id == mother_id,
            SavingReminder.is_active == True
        ).first()
        
        if existing_reminder:
            # Update existing reminder
            existing_reminder.reminder_date = reminder_data.reminder_date
            existing_reminder.updated_at = datetime.utcnow()
            reminder_id = existing_reminder.reminder_id
        else:
            # Create new reminder
            reminder_id = f"REM{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8]}"
            new_reminder = SavingReminder(
                reminder_id=reminder_id,
                mother_id=mother_id,
                reminder_date=reminder_data.reminder_date,
                reminder_time=time(9, 0),  # Default to 9:00 AM
                is_active=True
            )
            db.add(new_reminder)
        
        db.commit()
        
        # Format confirmation message for USSD
        ussd_text = f"CON Reminder Set Successfully!\n"
        ussd_text += f"You will now receive a monthly reminder on the {reminder_data.reminder_date}{get_day_suffix(reminder_data.reminder_date)} of each month.\n\n"
        ussd_text += f"0. Back to main menu"
        
        return {
            "success": True,
            "message": "Reminder set successfully",
            "reminder_id": reminder_id,
            "reminder_date": reminder_data.reminder_date,
            "mother_name": f"{mother.first_name} {mother.surname}",
            "ussd_text": ussd_text
        }
        
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "message": f"Internal server error: {str(e)}",
            "ussd_text": "CON System error. Please try again later.\n0. Back to main menu"
        }

@app.post("/ussd/mothers/{mother_id}/menu-selection", tags=["USSD Interface"])
async def ussd_handle_menu_selection(
    mother_id: str,
    selection_data: dict,
    db: Session = Depends(get_db)
):
    """Handle USSD menu selections and route to appropriate endpoints."""
    try:
        selection = selection_data.get("selection", "")
        
        if selection == "1":
            # Route to total savings
            result = get_mother_total_savings_ussd(db, mother_id)
            return result
        elif selection == "2":
            # Route to months saved
            result = get_mother_months_saved_ussd(db, mother_id)
            return result
        elif selection == "3":
            # Route to latest contributions
            result = get_mother_latest_contributions_ussd(db, mother_id, 5)
            return result
        elif selection == "4":
            # Route to comprehensive summary
            result = ussd_get_comprehensive_summary(mother_id, None, db)
            return result
        elif selection == "5":
            # Route to set reminder
            return {
                "success": True,
                "message": "Set Reminder",
                "ussd_text": "CON Set Monthly Saving Reminder\n\nEnter the day of the month (1-31) when you want to be reminded:\n\n0. Back to main menu"
            }
        elif selection == "0":
            return {
                "success": True,
                "message": "Session ended",
                "ussd_text": "END Thank you for using Cariya Wallet!"
            }
        else:
            return {
                "success": False,
                "message": "Invalid selection",
                "ussd_text": "CON Invalid selection. Please try again.\n1. Total Savings\n2. Months Progress\n3. Latest Contributions\n4. Comprehensive Summary\n5. Set Reminder\n0. Exit"
            }
            
    except Exception as e:
        return {
            "success": False,
            "message": f"Internal server error: {str(e)}",
            "ussd_text": "CON System error. Please try again later.\n0. Exit"
        }

if __name__ == "__main__":
    import uvicorn
    Base.metadata.create_all(bind=engine)
    try:
        print("Starting FastAPI application with scheduler...")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down scheduler...")
        scheduler.shutdown()
        executor.shutdown(wait=True)