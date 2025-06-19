import os
import uuid
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from decimal import Decimal
from datetime import datetime
from utils.unique_identifier_funcs import normalize_mobile_number, parse_children_ages, generate_unique_identifier
from utils.helpers import calculate_expected_savings, update_activity_points, update_compliance_score, calculate_monthly_scores, calculate_donor_contribution, segment_users_and_analyze_trends
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
    description: str | None
    location: str
    total_members: int = 0
    tel_number: str | None
    email: str | None

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
    description: str | None
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
    partner_id: str | None
    location: str | None
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
    month: int | None

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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

@app.post("/mothers/{mother_id}/activities")
async def add_monthly_activity(mother_id: str, activity_data: MonthlyActivity, db: Session = Depends(get_db)):
    """Add a monthly activity for a mother and update activity points."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise HTTPException(status_code=404, detail=f"No mother found with unique identifier {mother_id}")

        if not 1 <= activity_data.month <= 12:
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12")

        current_month = min(datetime.now().month, 4)
        if activity_data.month > current_month:
            raise HTTPException(status_code=400, detail=f"Cannot add activity for future month {activity_data.month}")

        activity = db.query(MotherActivity).filter(MotherActivity.activity_id == activity_data.activity_id).first()
        if not activity:
            raise HTTPException(status_code=404, detail=f"No activity found with ID {activity_data.activity_id}")

        month_key = f"{datetime.now().year}-{activity_data.month:02d}"

        # Check if mother is assigned to this activity
        if not db.query(MotherPartnerActivity).filter(
            MotherPartnerActivity.mother_id == mother_id,
            MotherPartnerActivity.activity_id == activity_data.activity_id
        ).first():
            raise HTTPException(status_code=400, detail="Mother is not assigned to this activity")

        # Add monthly activity
        monthly_activity = MonthlyActivityModel(
            mother_id=mother_id,
            month_key=month_key,
            activity_id=activity_data.activity_id,
            activity_points=1
        )
        db.add(monthly_activity)
        db.commit()

        # Update activity points and compliance score
        activity_points = update_activity_points(db, mother_id, current_month)
        mother.activity_points = activity_points
        compliance_score = update_compliance_score(db, mother_id, current_month)
        mother.compliance_score = compliance_score
        db.commit()

        return {
            "message": f"Activity added for month {month_key}",
            "activity_points": activity_points,
            "compliance_score": f"{compliance_score}/{current_month * 2}"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/calculate-scores")
async def calculate_scores(month: int | None = None, db: Session = Depends(get_db)):
    """Calculate and update scores for all mothers."""
    try:
        result = calculate_monthly_scores(db, month)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

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
    uvicorn.run(app, host="0.0.0.0", port=8000)