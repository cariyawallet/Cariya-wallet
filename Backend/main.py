import os
import uuid
import re
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Union, List
from decimal import Decimal
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from utils.unique_identifier_funcs import normalize_mobile_number, parse_children_ages, generate_unique_identifier
from utils.helpers import calculate_expected_savings, update_activity_points, update_compliance_score, calculate_monthly_scores, add_donor_contribution, segment_mothers_and_analyze_trends
from utils.models import Mother, MotherActivity, MotherPartnerActivity, MonthlySavings, MonthlyActivityModel, Partners, Donors, Businesses, DonorContributions, Base

DATABASE_URL = "postgresql://cariyadb_user:hOZPY44VmR4vQv8P9OFzwCOHdShXrGBv@dpg-d1972anfte5s73c2rao0-a.oregon-postgres.render.com/cariyadb"
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in environment variables")

# Database connection
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI(title="Cariya Wallet API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class AddBusiness(BaseModel):
    business_name: str
    contact_email: str
    country_of_residence: Union[str, None]
    payment_details: Union[str, None]
    subscription_status: str = "pending"

    @field_validator("business_name")
    @classmethod
    def validate_business_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Business name cannot be empty")
        if len(v) > 100:
            raise ValueError("Business name must be 100 characters or less")
        return v.strip()

    @field_validator("contact_email")
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

    @field_validator("subscription_status")
    @classmethod
    def validate_subscription_status(cls, v):
        valid_statuses = ["active", "inactive", "pending"]
        if v not in valid_statuses:
            raise ValueError(f"Subscription status must be one of {valid_statuses}")
        return v

class UpdateBusiness(BaseModel):
    business_name: Union[str, None]
    contact_email: Union[str, None]
    country_of_residence: Union[str, None]
    payment_details: Union[str, None]
    subscription_status: Union[str, None]

    @field_validator("business_name")
    @classmethod
    def validate_business_name(cls, v):
        if v is None:
            return v
        if len(v.strip()) == 0:
            raise ValueError("Business name cannot be empty")
        if len(v) > 100:
            raise ValueError("Business name must be 100 characters or less")
        return v.strip()

    @field_validator("contact_email")
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

    @field_validator("subscription_status")
    @classmethod
    def validate_subscription_status(cls, v):
        if v is None:
            return v
        valid_statuses = ["active", "inactive", "pending"]
        if v not in valid_statuses:
            raise ValueError(f"Subscription status must be one of {valid_statuses}")
        return v

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

# Scheduler setup
scheduler = BackgroundScheduler()

def run_scoring_job():
    """Run the scoring job every 30 minutes."""
    db = SessionLocal()
    try:
        current_month = datetime.now().month
        calculate_monthly_scores(db, target_month=current_month)
        print(f"Scoring job executed successfully for month {current_month}")
    except Exception as e:
        print(f"Error running scoring job: {str(e)}")
    finally:
        db.close()

# Schedule the scoring job to run every 30 minutes
scheduler.add_job(run_scoring_job, "interval", minutes=30)
scheduler.start()

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
    """Retrieve all partners with their activities and number of associated mothers."""
    try:
        partners = db.query(Partners).all()
        if not partners:
            return {"message": "No partners found"}
        result = []
        for p in partners:
            # Fetch activities for the partner
            activities = db.query(MotherActivity).filter(MotherActivity.partner_id == p.partner_id).all()
            # Count mothers associated with the partner
            mother_count = db.query(Mother).filter(Mother.partner_id == p.partner_id).count()
            result.append({
                "partner_id": p.partner_id,
                "partner_name": p.partner_name,
                "description": p.description,
                "location": p.location,
                "total_members": p.total_members,
                "tel_number": p.tel_number,
                "email": p.email,
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
                "mother_count": mother_count
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/partners/{partner_id}")
async def get_partner_profile(partner_id: str, db: Session = Depends(get_db)):
    """Retrieve a partner's profile by ID with their activities and number of associated mothers."""
    try:
        partner = db.query(Partners).filter(Partners.partner_id == partner_id).first()
        if not partner:
            raise HTTPException(status_code=404, detail=f"No partner found with ID {partner_id}")
        # Fetch activities for the partner
        activities = db.query(MotherActivity).filter(MotherActivity.partner_id == partner_id).all()
        # Count mothers associated with the partner
        mother_count = db.query(Mother).filter(Mother.partner_id == partner_id).count()
        return {
            "partner_id": partner.partner_id,
            "partner_name": partner.partner_name,
            "description": partner.description,
            "location": partner.location,
            "total_members": partner.total_members,
            "tel_number": partner.tel_number,
            "email": partner.email,
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
            "mother_count": mother_count
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

if __name__ == "__main__":
    import uvicorn
    Base.metadata.create_all(bind=engine)
    try:
        print("Starting FastAPI application with scheduler...")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down scheduler...")
        scheduler.shutdown()