import os
import uuid
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Union
from decimal import Decimal
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from utils.unique_identifier_funcs import normalize_mobile_number, parse_children_ages, generate_unique_identifier
from utils.helpers import calculate_expected_savings, update_activity_points, update_compliance_score, calculate_monthly_scores, calculate_donor_contribution, segment_mothers_and_analyze_trends
from utils.models import Mother, MotherActivity, MotherPartnerActivity, MonthlySavings, MonthlyActivityModel, Partners, Base


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
        # Check for duplicate partner_name or email
        if db.query(Partners).filter(Partners.partner_name == partner_data.partner_name).first():
            raise HTTPException(status_code=400, detail=f"Partner name '{partner_data.partner_name}' already exists")
        if partner_data.email and db.query(Partners).filter(Partners.email == partner_data.email).first():
            raise HTTPException(status_code=400, detail=f"Email '{partner_data.email}' already exists")

        # Generate unique partner_id
        partner_id = str(uuid.uuid4())

        # Create partner record
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
    """Retrieve all partners."""
    try:
        partners = db.query(Partners).all()
        if not partners:
            return {"message": "No partners found"}
        return [{"partner_id": p.partner_id, "partner_name": p.partner_name, "location": p.location, "total_members": p.total_members} for p in partners]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/partners")
async def get_partners(db: Session = Depends(get_db)):
    """Retrieve all partners."""
    try:
        partners = db.query(Partners).all()
        if not partners:
            return {"message": "No partners found"}
        return [
            {
                "partner_id": p.partner_id,
                "partner_name": p.partner_name,
                "description": p.description,
                "location": p.location,
                "total_members": p.total_members,
                "tel_number": p.tel_number,
                "email": p.email,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            }
            for p in partners
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/partners/{partner_id}")
async def get_partner_profile(partner_id: str, db: Session = Depends(get_db)):
    """Retrieve a partner's profile by ID."""
    try:
        partner = db.query(Partners).filter(Partners.partner_id == partner_id).first()
        if not partner:
            raise HTTPException(status_code=404, detail=f"No partner found with ID {partner_id}")
        
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
        # Validate partner_id exists
        partner = db.query(Partners).filter(Partners.partner_id == activity_data.partner_id).first()
        if not partner:
            raise HTTPException(status_code=404, detail=f"Partner with ID '{activity_data.partner_id}' not found")

        # Check for duplicate activity name under the same partner
        if db.query(MotherActivity).filter(
            MotherActivity.partner_id == activity_data.partner_id,
            MotherActivity.name == activity_data.name
        ).first():
            raise HTTPException(status_code=400, detail=f"Activity name '{activity_data.name}' already exists for this partner")

        # Generate unique activity_id
        activity_id = str(uuid.uuid4())

        # Create activity record
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

@app.post("/addMother")
async def add_mother(mother_data: AddMother, db: Session = Depends(get_db)):
    """Add a new mother and link to an existing activity via mother_partner_activities."""
    try:
        # Parse and validate ages of children
        ages = parse_children_ages(mother_data.ages_of_children_per_birth)
        if len(ages) != mother_data.num_children:
            raise HTTPException(status_code=400, detail="Number of children must match ages provided")

        # Generate unique identifier
        generated_id = generate_unique_identifier(
            mother_data.first_name,
            mother_data.surname,
            mother_data.mobile_number,
            mother_data.num_children,
            mother_data.ages_of_children_per_birth
        )

        # Check for duplicate mother
        if db.query(Mother).filter(Mother.mobile_number == mother_data.mobile_number).first():
            raise HTTPException(status_code=400, detail=f"Mobile number {mother_data.mobile_number} is already registered")

        if db.query(Mother).filter(Mother.generated_id == generated_id).first():
            raise HTTPException(status_code=400, detail=f"Mother with ID {generated_id} already exists")

        # Validate partner_id if provided for mother
        if mother_data.partner_id:
            partner = db.query(Partners).filter(Partners.partner_id == mother_data.partner_id).first()
            if not partner:
                raise HTTPException(status_code=404, detail=f"Partner with ID {mother_data.partner_id} not found")

        # Validate activity_id exists
        activity = db.query(MotherActivity).filter(MotherActivity.activity_id == mother_data.activity_id).first()
        if not activity:
            raise HTTPException(status_code=404, detail=f"Activity with ID {mother_data.activity_id} not found")

        # Increment num_people in mother_activities
        activity.num_people += 1

        # Create mother record
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
            donor_contributions=0.0
        )
        db.add(mother)
        db.commit()
        db.refresh(mother)

        # Check if mother is already assigned to this activity
        if db.query(MotherPartnerActivity).filter(
            MotherPartnerActivity.mother_id == generated_id,
            MotherPartnerActivity.activity_id == mother_data.activity_id
        ).first():
            raise HTTPException(status_code=400, detail=f"Mother already assigned to activity {mother_data.activity_id}")

        # Create mother_partner_activities record
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
    """Retrieve all mothers."""
    try:
        mothers = db.query(Mother).all()
        if not mothers:
            return {"message": "No mothers found"}
        return [{"generated_id": m.generated_id, "first_name": m.first_name, "surname": m.surname, "mobile_number": m.mobile_number, "num_children": m.num_children} for m in mothers]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/mothers/{mother_id}")
async def get_mother_info(mother_id: str, db: Session = Depends(get_db)):
    """Retrieve mother information."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise HTTPException(status_code=404, detail=f"No mother found with unique identifier {mother_id}")

        monthly_savings = db.query(MonthlySavings).filter(MonthlySavings.mother_id == mother_id).all()
        monthly_data = {saving.month_key: {
            "savings": saving.savings,
            "milestone_score": saving.milestone_score,
            "donor_contribution": saving.donor_contribution
        } for saving in monthly_savings}
        total_savings = sum(saving.savings for saving in monthly_savings)

        return {
            "first_name": mother.first_name,
            "surname": mother.surname,
            "total_savings": total_savings,
            "monthly_data": monthly_data,
            "activity_points": mother.activity_points,
            "milestone_score": mother.milestone_score,
            "compliance_score": mother.compliance_score
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

        # Convert savings_data.amount to Decimal
        amount = Decimal(str(savings_data.amount))

        # Update monthly savings
        savings = db.query(MonthlySavings).filter(MonthlySavings.mother_id == mother_id, MonthlySavings.month_key == month_key).first()
        if savings:
            current_savings = savings.savings  # Decimal from database
        else:
            current_savings = Decimal('0.00')  # Use Decimal instead of float
            savings = MonthlySavings(mother_id=mother_id, month_key=month_key)

        new_savings = current_savings + amount
        milestone_score = 1 if new_savings >= Decimal(str(expected_savings)) else 0
        savings.savings = new_savings
        savings.milestone_score = milestone_score

        if not savings.id:
            db.add(savings)
        db.commit()

        # Update total savings in mothers table
        mother.savings += amount
        db.commit()

        # Recalculate compliance score
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
    """
    Retrieve all monthly savings for all mothers.
    Optionally filter by a specific month using the 'month' query parameter (format: YYYY-MM).
    """
    try:
        # Query all monthly savings
        if month:
            # Filter by the given month
            savings = db.query(MonthlySavings).filter(MonthlySavings.month_key == month).all()
        else:
            # Retrieve all savings if no month is specified
            savings = db.query(MonthlySavings).all()

        if not savings:
            return {"message": "No savings found"}

        # Format the response
        result = [
            {
                "mother_id": s.mother_id,
                "month_key": s.month_key,
                "savings": float(s.savings),
                "milestone_score": s.milestone_score,
                "donor_contribution": float(s.donor_contribution),
            }
            for s in savings
        ]

        return {"monthly_savings": result}

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
            total_donor_contributions = mother.donor_contributions

            for saving in monthly_savings:
                monthly_data[saving.month_key] = {
                    "user_savings": saving.savings,
                    "donor_contribution": saving.donor_contribution
                }
                total_user_savings += saving.savings

            donor_data.append({
                "mother_id": mother.generated_id,
                "first_name": mother.first_name,
                "surname": mother.surname,
                "total_savings": mother.savings,
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