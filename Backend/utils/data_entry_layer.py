import pandas as pd
import uuid
import logging
from typing import Set
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from fastapi import HTTPException
from unique_identifier_funcs import normalize_mobile_number, parse_children_ages, generate_unique_identifier
from models import Mother, MotherActivity, MotherPartnerActivity, MonthlyActivityModel, Partners

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATABASE_URL = "postgresql://cariyadb_damb_user:LLM87f54JeWhIfyHBDSKJogoPqc93jrW@dpg-d28s0druibrs73dt691g-a.oregon-postgres.render.com/cariyadb_damb"

# Database connection
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def validate_education_level(education_level):
    """Validate education level against allowed options."""
    valid_levels = [
        "Finished University",
        "Started 'A' Level",
        "Started 'O' Level",
        "Finished Primary 7",
        "Finished Primary 5",
        "Never went to school"
    ]
    if education_level not in valid_levels:
        raise ValueError(f"Invalid education level: {education_level}. Must be one of {valid_levels}")
    return education_level

def normalize_columns(columns: list) -> Set[str]:
    """Normalize column names by stripping whitespace and converting to lowercase."""
    return {str(col).strip().lower() for col in columns}

def find_column(columns: list, target: str) -> str:
    """Find a column name case-insensitively, ignoring whitespace."""
    target = target.lower().strip()
    for col in columns:
        if str(col).strip().lower() == target:
            return col
    raise KeyError(f"Column '{target}' not found in {columns}")

def process_add_activity_sheet(df: pd.DataFrame, partner_id: str, db: Session) -> dict:
    """Process AddActivity sheet and insert into mother_activities table."""
    logger.info("Starting to process AddActivity sheet")
    
    # Log DataFrame columns for debugging
    logger.info(f"Columns found in AddActivity sheet: {list(df.columns)}")
    normalized_columns = normalize_columns(df.columns)
    logger.info(f"Normalized columns: {normalized_columns}")

    # Check for required columns (case-insensitive, whitespace-ignored)
    required_columns = {'activity', 'description'}
    if not required_columns.issubset(normalized_columns):
        missing = required_columns - normalized_columns
        raise ValueError(f"AddActivity sheet missing required columns: {missing}. Found: {normalized_columns}")

    # Validate partner_id exists
    partner = db.query(Partners).filter(Partners.partner_id == partner_id).first()
    if not partner:
        raise ValueError(f"Partner with ID {partner_id} not found")

    results = {
        "inserted": [],
        "skipped": [],
        "errors": []
    }
    total_rows = len(df)

    # Find actual column names
    try:
        activity_col = find_column(df.columns, 'Activity')
        description_col = find_column(df.columns, 'Description')
    except KeyError as e:
        raise ValueError(f"Column not found: {str(e)}")

    for idx, row in df.iterrows():
        activity_name = str(row[activity_col]).strip()
        description = str(row[description_col]).strip() if pd.notna(row[description_col]) else None

        if not activity_name:
            results['skipped'].append({"row": idx + 2, "reason": "Empty activity name"})
            logger.warning(f"Row {idx + 2}: Skipped due to empty activity name")
            continue

        try:
            # Check for duplicate activity name under the same partner
            existing_activity = db.query(MotherActivity).filter(
                MotherActivity.partner_id == partner_id,
                MotherActivity.name == activity_name
            ).first()
            if existing_activity:
                results['skipped'].append({"row": idx + 2, "reason": f"Duplicate activity '{activity_name}'"})
                logger.warning(f"Row {idx + 2}: Skipped due to duplicate activity '{activity_name}'")
                continue

            # Generate unique activity_id
            activity_id = str(uuid.uuid4())

            # Create activity record
            activity = MotherActivity(
                activity_id=activity_id,
                partner_id=partner_id,
                name=activity_name,
                description=description,
                num_people=0
            )
            db.add(activity)
            db.flush()  # Ensure activity is persisted before logging
            results['inserted'].append({"row": idx + 2, "activity_id": activity_id, "name": activity_name})
            logger.info(f"Row {idx + 2}: Added activity '{activity_name}' with ID {activity_id}")

        except Exception as e:
            results['errors'].append({"row": idx + 2, "reason": str(e)})
            logger.error(f"Row {idx + 2}: Error adding activity '{activity_name}': {str(e)}")
            db.rollback()  # Roll back on error to prevent partial commits
            continue

    try:
        db.commit()
        logger.info(f"AddActivity sheet processing complete: {len(results['inserted'])} inserted, {len(results['skipped'])} skipped, {len(results['errors'])} errors out of {total_rows} rows")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to commit changes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to commit changes: {str(e)}")

    return results

def process_profiles_sheet(df, partner_id, activity_id, db: Session):
    """Process Profiles sheet and insert into mothers and mother_partner_activities tables."""
    logger.info("Starting to process Profiles sheet")
    required_columns = {'First name', 'Surname', 'Mobile number', 'No.of children under 18', 'Ages of children per birth order'}
    if not required_columns.issubset(df.columns):
        raise ValueError(f"Profiles sheet must contain {required_columns} columns")

    # Validate partner_id exists
    partner = db.query(Partners).filter(Partners.partner_id == partner_id).first()
    if not partner:
        raise ValueError(f"Partner with ID {partner_id} not found")

    # Validate activity_id exists
    activity = db.query(MotherActivity).filter(MotherActivity.activity_id == activity_id).first()
    if not activity:
        raise ValueError(f"Activity with ID {activity_id} not found")

    results = {
        "inserted": [],
        "skipped": [],
        "errors": []
    }
    total_rows = len(df)

    for idx, row in df.iterrows():
        first_name = str(row['First name']).strip()
        surname = str(row['Surname']).strip()
        mobile_number = str(row['Mobile number']).strip()
        num_children = int(row['No.of children under 18']) if pd.notna(row['No.of children under 18']) else 0
        ages_str = str(row['Ages of children per birth order']).strip() if pd.notna(row['Ages of children per birth order']) else ""
        location = str(row['Location']).strip() if pd.notna(row['Location']) and 'Location' in df.columns else None
        education_level = str(row['Education Level']).strip() if pd.notna(row['Education Level']) and 'Education Level' in df.columns else None
        nin = str(row['NIN']).strip() if pd.notna(row['NIN']) and 'NIN' in df.columns else None

        if not first_name or not surname or not mobile_number:
            results['skipped'].append({"row": idx + 2, "reason": "Missing required fields"})
            logger.warning(f"Row {idx + 2}: Skipped due to missing required fields")
            continue

        try:
            # Normalize and validate mobile number
            mobile_number = normalize_mobile_number(mobile_number)

            # Check for duplicate mobile number
            if db.query(Mother).filter(Mother.mobile_number == mobile_number).first():
                results['skipped'].append({"row": idx + 2, "reason": f"Duplicate mobile number {mobile_number}"})
                logger.warning(f"Row {idx + 2}: Skipped due to duplicate mobile number {mobile_number}")
                continue

            # Parse and validate ages
            ages = parse_children_ages(ages_str)
            if len(ages) != num_children:
                raise ValueError(f"Number of ages ({len(ages)}) does not match num_children ({num_children})")

            # Validate education level if provided
            if education_level:
                education_level = validate_education_level(education_level)

            # Generate unique identifier
            generated_id = generate_unique_identifier(first_name, surname, mobile_number, num_children, ages_str)

            # Check for duplicate generated_id
            if db.query(Mother).filter(Mother.generated_id == generated_id).first():
                results['skipped'].append({"row": idx + 2, "reason": f"Duplicate generated ID {generated_id}"})
                logger.warning(f"Row {idx + 2}: Skipped due to duplicate generated ID {generated_id}")
                continue

            # Create mother record
            mother = Mother(
                generated_id=generated_id,
                first_name=first_name,
                surname=surname,
                mobile_number=mobile_number,
                num_children=num_children,
                ages_of_children=ages,
                partner_id=partner_id,
                location=location,
                education_level=education_level,
                nin=nin,
                activity_points=0,
                savings=0.0,
                milestone_score=0,
                compliance_score=0,
                donor_contributions=0.0
            )
            db.add(mother)

            # Increment num_people in mother_activities
            activity.num_people += 1

            # Create mother_partner_activities record
            mother_partner_activity = MotherPartnerActivity(
                mother_id=generated_id,
                activity_id=activity_id
            )
            db.add(mother_partner_activity)
            results['inserted'].append({"row": idx + 2, "generated_id": generated_id, "name": f"{first_name} {surname}"})
            logger.info(f"Row {idx + 2}: Added mother '{first_name} {surname}' with ID {generated_id}")

        except ValueError as e:
            results['errors'].append({"row": idx + 2, "reason": str(e)})
            logger.error(f"Row {idx + 2}: Error adding mother '{first_name} {surname}': {str(e)}")

    db.commit()
    logger.info(f"Profiles processing complete: {len(results['inserted'])} inserted, {len(results['skipped'])} skipped, {len(results['errors'])} errors out of {total_rows} rows")
    return results

def process_activity_compliance_sheet(df, db: Session):
    """Process Activity compliance sheet and insert into monthly_activities table."""
    logger.info("Starting to process Activity compliance sheet")
    required_columns = {'Activity', 'Mobile number', 'Month', 'Year'}
    if not required_columns.issubset(df.columns):
        raise ValueError(f"Activity compliance sheet must contain {required_columns} columns")

    results = {
        "inserted": [],
        "skipped": [],
        "errors": []
    }
    total_rows = len(df)

    for idx, row in df.iterrows():
        activity_name = str(row['Activity']).strip()
        mobile_number = str(row['Mobile number']).strip()
        month = int(row['Month']) if pd.notna(row['Month']) else None
        year = int(row['Year']) if pd.notna(row['Year']) else None

        if not activity_name or not mobile_number or month is None or year is None:
            results['skipped'].append({"row": idx + 2, "reason": "Missing required fields"})
            logger.warning(f"Row {idx + 2}: Skipped due to missing required fields")
            continue

        try:
            # Normalize mobile number
            mobile_number = normalize_mobile_number(mobile_number)

            # Find mother by mobile number
            mother = db.query(Mother).filter(Mother.mobile_number == mobile_number).first()
            if not mother:
                results['skipped'].append({"row": idx + 2, "reason": f"Mother with mobile {mobile_number} not found"})
                logger.warning(f"Row {idx + 2}: Skipped due to mother with mobile {mobile_number} not found")
                continue

            # Find activity by name
            activity = db.query(MotherActivity).join(Partners).filter(
                MotherActivity.name == activity_name,
                MotherActivity.partner_id == mother.partner_id
            ).first()
            if not activity:
                results['skipped'].append({"row": idx + 2, "reason": f"Activity '{activity_name}' not found"})
                logger.warning(f"Row {idx + 2}: Skipped due to activity '{activity_name}' not found")
                continue

            # Check if mother is assigned to this activity
            if not db.query(MotherPartnerActivity).filter(
                MotherPartnerActivity.mother_id == mother.generated_id,
                MotherPartnerActivity.activity_id == activity.activity_id
            ).first():
                results['skipped'].append({"row": idx + 2, "reason": f"Mother not assigned to activity '{activity_name}'"})
                logger.warning(f"Row {idx + 2}: Skipped due to mother not assigned to activity '{activity_name}'")
                continue

            # Validate month and year
            if not 1 <= month <= 12:
                raise ValueError(f"Invalid month: {month}")
            current_year = datetime.now().year
            if year != current_year:
                raise ValueError(f"Year must be {current_year}, got {year}")

            month_key = f"{year}-{month:02d}"

            # Check for duplicate activity for this month
            if db.query(MonthlyActivityModel).filter(
                MonthlyActivityModel.mother_id == mother.generated_id,
                MonthlyActivityModel.month_key == month_key,
                MonthlyActivityModel.activity_id == activity.activity_id
            ).first():
                results['skipped'].append({"row": idx + 2, "reason": f"Duplicate activity for {month_key}"})
                logger.warning(f"Row {idx + 2}: Skipped due to duplicate activity for {month_key}")
                continue

            # Add monthly activity
            monthly_activity = MonthlyActivityModel(
                mother_id=mother.generated_id,
                month_key=month_key,
                activity_id=activity.activity_id,
                activity_points=1
            )
            db.add(monthly_activity)
            results['inserted'].append({"row": idx + 2, "activity_id": activity.activity_id, "mother_id": mother.generated_id, "month_key": month_key})
            logger.info(f"Row {idx + 2}: Added activity '{activity_name}' for mother {mother.generated_id} in {month_key}")

        except ValueError as e:
            results['errors'].append({"row": idx + 2, "reason": str(e)})
            logger.error(f"Row {idx + 2}: Error adding activity for mobile {mobile_number}: {str(e)}")

    db.commit()
    logger.info(f"Activity compliance processing complete: {len(results['inserted'])} inserted, {len(results['skipped'])} skipped, {len(results['errors'])} errors out of {total_rows} rows")
    return results

def import_excel_data(file_path: str, partner_id: str, activity_id: str, db: Session):
    """Main function to import data from Excel file."""
    logger.info(f"Starting Excel import from {file_path}")
    try:
        # Read Excel file
        xls = pd.ExcelFile(file_path)
        print("Sheet names:", xls.sheet_names)

        results = {
            "add_activity": {"inserted": [], "skipped": [], "errors": []},
            "profiles": {"inserted": [], "skipped": [], "errors": []},
            "activity_compliance": {"inserted": [], "skipped": [], "errors": []}
        }

        # Process AddActivity sheet
        # if 'AddActivity' in xls.sheet_names:
        #     df_activity = pd.read_excel(xls, 'AddActivity')
        #     print("AddActivity columns:", list(df_activity.columns))
        #     results['add_activity'] = process_add_activity_sheet(df_activity, partner_id, db)

        # # Process Profiles sheet
        # if 'Profiles' in xls.sheet_names:
        #     df_profiles = pd.read_excel(xls, 'Profiles')
        #     results['profiles'] = process_profiles_sheet(df_profiles, partner_id, activity_id, db)

        # Process Activity compliance sheet
        if 'Activity compliance' in xls.sheet_names:
            df_compliance = pd.read_excel(xls, 'Activity compliance')
            results['activity_compliance'] = process_activity_compliance_sheet(df_compliance, db)

        logger.info("Excel import completed successfully")
        return {
            "message": "Excel data imported successfully",
            "details": results
        }

    except ValueError as e:
        logger.error(f"Excel import failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Internal server error during Excel import: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

if __name__ == "__main__":
    # Example usage
    file_path = "/Users/user/Documents/CARIYA/cariya_wallet/Backend/utils/data/Okere City Mothers.xlsx"
    partner_id = "ca2c7c25-bfbd-4138-b579-0197e914aa4b" 
    activity_id = "fa461116-791a-4fc7-830a-b741711035ba" 
    db_session = next(get_db())
    result = import_excel_data(file_path, partner_id, activity_id, db_session)
    print(result)