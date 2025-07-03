import pandas as pd
from sqlalchemy.orm import Session
from datetime import datetime
import logging
import uuid
from models import Partners, Mother, MotherActivity, MotherPartnerActivity, MonthlySavings, MonthlyActivityModel, Donors

logger = logging.getLogger(__name__)

def process_profiles_sheet(df: pd.DataFrame, partner_id: str, db: Session) -> dict:
    """Process the Profiles sheet to insert or update mother profiles."""
    logger.info("Starting to process Profiles sheet")
    normalized_columns = {col.lower().replace(" ", "_"): col for col in df.columns}
    required_columns = {"first_name", "surname", "mobile_number", "num_children", "ages_of_children"}
    optional_columns = {"donor_email", "location", "education_level", "nin"}
    if not required_columns.issubset(normalized_columns):
        raise ValueError(f"Profiles sheet missing required columns: {required_columns - set(normalized_columns.keys())}")
    
    results = {"inserted": [], "skipped": [], "errors": []}
    for idx, row in df.iterrows():
        first_name = str(row[normalized_columns["first_name"]]).strip()
        surname = str(row[normalized_columns["surname"]]).strip()
        mobile_number = str(row[normalized_columns["mobile_number"]]).strip()
        num_children = int(row[normalized_columns["num_children"]]) if pd.notna(row[normalized_columns["num_children"]]) else None
        ages_of_children = row[normalized_columns["ages_of_children"]]
        location = str(row[normalized_columns["location"]]).strip() if "location" in normalized_columns and pd.notna(row[normalized_columns["location"]]) else None
        education_level = str(row[normalized_columns["education_level"]]).strip() if "education_level" in normalized_columns and pd.notna(row[normalized_columns["education_level"]]) else None
        nin = str(row[normalized_columns["nin"]]).strip() if "nin" in normalized_columns and pd.notna(row[normalized_columns["nin"]]) else None
        
        if not all([first_name, surname, mobile_number, num_children is not None, ages_of_children]):
            results["skipped"].append({"row": idx + 2, "reason": "Missing required fields"})
            continue
        
        try:
            mobile_number = f"+256{mobile_number}" if not mobile_number.startswith("+256") else mobile_number
            if not (12 <= len(mobile_number) <= 13):
                results["skipped"].append({"row": idx + 2, "reason": f"Invalid mobile number length: {mobile_number}"})
                continue
            
            ages_of_children = [int(age) for age in ages_of_children.split(",")] if isinstance(ages_of_children, str) else list(ages_of_children)
            if len(ages_of_children) != num_children or not all(0 <= age <= 18 for age in ages_of_children):
                results["skipped"].append({"row": idx + 2, "reason": "Invalid ages_of_children"})
                continue
            
            existing_mother = db.query(Mother).filter(Mother.mobile_number == mobile_number).first()
            if existing_mother:
                results["skipped"].append({"row": idx + 2, "reason": f"Mother with mobile {mobile_number} already exists"})
                continue
            
            mother = Mother(
                generated_id=str(uuid.uuid4()),
                first_name=first_name,
                surname=surname,
                mobile_number=mobile_number,
                num_children=num_children,
                ages_of_children=ages_of_children,
                partner_id=partner_id,
                donor_id=None,  # Explicitly set to None to prevent automatic assignment
                location=location,
                education_level=education_level,
                nin=nin
            )
            db.add(mother)
            db.flush()
            results["inserted"].append({"row": idx + 2, "mother_id": mother.generated_id})
        except Exception as e:
            results["errors"].append({"row": idx + 2, "reason": str(e)})
            db.rollback()
    
    db.commit()
    return results


def process_savings_sheet(df: pd.DataFrame, db: Session) -> dict:
    """Process the Savings sheet to insert or update monthly savings."""
    logger.info("Starting to process Savings sheet")
    normalized_columns = {col.lower().replace(" ", "_"): col for col in df.columns}
    required_columns = {"mobile_number", "month", "year", "savings"}
    if not required_columns.issubset(normalized_columns):
        raise ValueError(f"Savings sheet missing required columns: {required_columns - set(normalized_columns.keys())}")
    
    results = {"inserted": [], "skipped": [], "errors": []}
    for idx, row in df.iterrows():
        mobile_number = str(row[normalized_columns["mobile_number"]]).strip()
        month = int(row[normalized_columns["month"]]) if pd.notna(row[normalized_columns["month"]]) else None
        year = int(row[normalized_columns["year"]]) if pd.notna(row[normalized_columns["year"]]) else None
        savings = float(row[normalized_columns["savings"]]) if pd.notna(row[normalized_columns["savings"]]) else 0.0
        
        if not mobile_number or month is None or year is None:
            results["skipped"].append({"row": idx + 2, "reason": "Missing required fields"})
            continue
        
        try:
            mobile_number = f"+256{mobile_number}" if not mobile_number.startswith("+256") else mobile_number
            mother = db.query(Mother).filter(Mother.mobile_number == mobile_number).first()
            if not mother:
                results["skipped"].append({"row": idx + 2, "reason": f"Mother with mobile {mobile_number} not found"})
                continue
            
            month_key = f"{year}-{month:02d}"
            existing_savings = db.query(MonthlySavings).filter(
                MonthlySavings.mother_id == mother.generated_id,
                MonthlySavings.month_key == month_key
            ).first()
            
            if existing_savings:
                existing_savings.savings = savings
                existing_savings.updated_at = datetime.utcnow()
            else:
                savings_record = MonthlySavings(
                    mother_id=mother.generated_id,
                    month_key=month_key,
                    savings=savings,
                    milestone_score=0,
                    donor_contribution=0.0
                )
                db.add(savings_record)
            
            db.flush()
            results["inserted"].append({"row": idx + 2, "mother_id": mother.generated_id, "month_key": month_key})
        except Exception as e:
            results["errors"].append({"row": idx + 2, "reason": str(e)})
            db.rollback()
    
    db.commit()
    return results


if __name__ == "__main__":
    # Example usage
    file_path = "Okere City Mothers.xlsx"
    partner_id = "example-partner-id"  # Replace with actual partner_id
    activity_id = "example-activity-id"  # Replace with actual activity_id
    db_session = next(get_db())
    result = import_excel_data(file_path, partner_id, activity_id, db_session)
    print(result)