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
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from utils.unique_identifier_funcs import normalize_mobile_number, parse_children_ages, generate_unique_identifier
from utils.helpers import calculate_expected_savings,update_compliance_score, calculate_monthly_scores, add_donor_contribution, add_partner_contribution
from utils.async_helpers import calculate_monthly_scores_async, get_scoring_progress
from utils.models import Mother, MotherActivity, MotherPartnerActivity, MonthlySavings, MonthlyActivityModel, Partners, Donors,DonorContributions,PartnerSubscriptions, PartnerContributions,Base
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


@app.post("/partner/login")
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
@app.post("/partner/verify")
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


@app.post("/addPartner")
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

@app.get("/partners")
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

@app.post("/addPartnerSubscription")
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

@app.put("/partnerSubscriptions/{subscription_id}")
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

@app.get("/partnerSubscriptions/{partner_id}")
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

@app.post("/addPartnerContribution")
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

@app.get("/partners/{partner_id}/contributions")
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

@app.get("/partners/{partner_id}")
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

@app.get("/partners/{partner_id}/activities")
async def get_activities_by_partner(partner_id: str, db: Session = Depends(get_db)):
    """Retrieve activities associated with a specific partner."""
    try:
        activities = db.query(MotherActivity).filter(MotherActivity.partner_id == partner_id).all()
        if not activities:
            return {"message": f"No activities found for partner with ID {partner_id}"}
        return [{"activity_id": a.activity_id, "name": a.name, "description": a.description, "num_people": a.num_people} for a in activities]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/addActivity")
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

@app.get("/activities")
async def get_activities(db: Session = Depends(get_db)):
    """Retrieve all activities."""
    try:
        activities = db.query(MotherActivity).all()
        if not activities:
            return {"message": "No activities found"}
        return [{"activity_id": a.activity_id, "name": a.name, "description": a.description, "num_people": a.num_people, "partner_id": a.partner_id} for a in activities]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/addDonor")
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

@app.get("/donors")
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
                # Fetch compliance score
                current_month = min(datetime.now().month, 4)
                max_compliance = current_month * 2
                compliance_score = f"{mother.compliance_score}/{max_compliance}"
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

@app.get("/donors/{donor_id}")
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
            # Fetch compliance score
            current_month = min(datetime.now().month, 4)
            max_compliance = current_month * 2
            compliance_score = f"{mother.compliance_score}/{max_compliance}"
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

@app.put("/donors/{donor_id}")
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

@app.delete("/donors/{donor_id}")
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

@app.get("/donors/{donor_id}/donations")
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

@app.post("/addDonation")
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

@app.get("/mothers/{mother_id}/donations")
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

@app.post("/addMother")
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

@app.get("/mothers")
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
            # Fetch compliance score
            current_month = min(datetime.now().month, 4)
            max_compliance = current_month * 2
            compliance_score = f"{m.compliance_score}/{max_compliance}"
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

@app.get("/partners/{partner_id}/mothers")
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
            
            # Fetch compliance score
            current_month = min(datetime.now().month, 4)
            max_compliance = current_month * 2
            compliance_score = f"{mother.compliance_score}/{max_compliance}"
            
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

@app.get("/mothers/{mother_id}")
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

        # Fetch compliance score
        current_month = min(datetime.now().month, 4)
        max_compliance = current_month * 2
        compliance_score = f"{mother.compliance_score}/{max_compliance}"

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

@app.post("/mothers/{mother_id}/savings")
async def add_savings(mother_id: str, savings_data: SavingsEntry, db: Session = Depends(get_db)):
    """Add savings for a mother in the specified month."""
    try:
        if savings_data.amount < 0:
            raise HTTPException(status_code=400, detail="Savings amount cannot be negative")

        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise HTTPException(status_code=404, detail=f"No mother found with unique identifier {mother_id}")

        expected_savings = calculate_expected_savings(mother.num_children)
        current_month = min(datetime.now().month, 4) if savings_data.month is None else savings_data.month
        if not 1 <= current_month <= 12:
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12")
        month_key = f"{datetime.now().year}-{current_month:02d}"

        amount = Decimal(str(savings_data.amount))
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
        db.commit()

        mother.savings += amount
        db.commit()

        compliance_score = update_compliance_score(db, mother_id, current_month)
        mother.compliance_score = compliance_score
        db.commit()

        return {
            "message": f"Savings added for {mother.first_name} {mother.surname} in {month_key}",
            "monthly_savings": float(new_savings),
            "total_savings": float(mother.savings),
            "expected_savings": float(expected_savings),
            "milestone_score": milestone_score,
            "compliance_score": f"{compliance_score}/{current_month * 2}"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}/monthly-savings")
async def get_monthly_savings(mother_id: str, db: Session = Depends(get_db)):
    """Retrieve monthly savings for a specific mother."""
    try:
        savings = db.query(MonthlySavings).filter(MonthlySavings.mother_id == mother_id).all()
        if not savings:
            return {"message": f"No savings found for mother with ID {mother_id}"}
        return [{"month_key": s.month_key, "savings": float(s.savings), "milestone_score": s.milestone_score, "donor_contribution": float(s.donor_contribution)} for s in savings]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/monthly-savings")
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

@app.get("/mothers/{mother_id}/monthly-activities")
async def get_monthly_activities(mother_id: str, db: Session = Depends(get_db)):
    """Retrieve monthly activities for a specific mother."""
    try:
        activities = db.query(MonthlyActivityModel).filter(MonthlyActivityModel.mother_id == mother_id).all()
        if not activities:
            return {"message": f"No activities found for mother with ID {mother_id}"}
        return [{"month_key": a.month_key, "activity_id": a.activity_id, "activity_points": a.activity_points} for a in activities]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}/compliance")
async def get_compliance(mother_id: str, db: Session = Depends(get_db)):
    """Get annual compliance score."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise HTTPException(status_code=404, detail=f"No mother found with unique identifier {mother_id}")

        current_month = min(datetime.now().month, 4)
        max_compliance = current_month * 2
        return {
            "first_name": mother.first_name,
            "surname": mother.surname,
            "compliance_score": f"{mother.compliance_score}/{max_compliance}"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/donor-view")
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

@app.post("/admin/trigger-scoring")
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

@app.get("/admin/scoring-status")
async def get_scoring_status():
    """Get the current status of the scoring job."""
    return {
        "scoring_job_running": scoring_job_running,
        "scheduler_running": scheduler.running,
        "next_run_time": scheduler.get_jobs()[0].next_run_time if scheduler.get_jobs() else None
    }

@app.post("/admin/trigger-async-scoring")
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

@app.get("/admin/scoring-progress")
async def get_scoring_progress_endpoint(db: Session = Depends(get_db)):
    """Get the current progress of scoring operations."""
    try:
        progress = await get_scoring_progress(db)
        return progress
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting scoring progress: {str(e)}")

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