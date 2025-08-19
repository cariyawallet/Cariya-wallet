from datetime import datetime
import logging
import re
from sqlalchemy.orm import Session
from sqlalchemy import func
from utils.models import Mother, MonthlyActivityModel, MonthlySavings, Donors, DonorContributions, Partners, PartnerSubscriptions, PartnerContributions
from fastapi import HTTPException
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def calculate_expected_savings(num_children: int) -> float:
    """Calculate expected monthly savings (1000 UGX × number of children under 18)."""
    if not isinstance(num_children, int) or num_children < 0:
        raise ValueError("Number of children must be a non-negative integer")
    return 1000 * num_children

def update_activity_points(db: Session, mother_id: str, current_month: int) -> int:
    """Recalculate activity points based on monthly activities."""
    mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
    if not mother:
        raise ValueError(f"No mother found with generated_id {mother_id}")
    
    current_year = datetime.now().year
    
    # More efficient query to get all activity months at once
    activity_months = db.query(MonthlyActivityModel.month_key).filter(
        MonthlyActivityModel.mother_id == mother_id
    ).distinct().all()
    
    activity_points = 0
    for month in range(1, current_month + 1):
        month_key = f"{current_year}-{month:02d}"
        if any(am[0] == month_key for am in activity_months):
            activity_points += 1
    
    mother.activity_points = activity_points
    mother.updated_at = datetime.utcnow()
    db.flush()
    logger.info(f"Updated activity points for mother {mother_id}: {activity_points}")
    return activity_points

def update_compliance_score(db: Session, mother_id: str, current_month: int) -> int:
    """Update annual compliance score based on monthly data."""
    mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
    if not mother:
        raise ValueError(f"No mother found with generated_id {mother_id}")
    
    current_year = datetime.now().year
    
    # More efficient query to get all savings and activities at once
    savings_data = db.query(MonthlySavings.month_key, MonthlySavings.milestone_score).filter(
        MonthlySavings.mother_id == mother_id
    ).all()
    activity_data = db.query(MonthlyActivityModel.month_key).filter(
        MonthlyActivityModel.mother_id == mother_id
    ).distinct().all()
    
    # Convert to sets for faster lookup
    savings_months = {s[0] for s in savings_data}
    activity_months = {a[0] for a in activity_data}
    savings_scores = {s[0]: s[1] for s in savings_data}
    
    annual_compliance = 0
    for month in range(1, current_month + 1):
        month_key = f"{current_year}-{month:02d}"
        milestone_score = savings_scores.get(month_key, 0)
        activity_point = 1 if month_key in activity_months else 0
        annual_compliance += milestone_score + activity_point
    
    mother.compliance_score = annual_compliance
    mother.updated_at = datetime.utcnow()
    db.flush()
    logger.info(f"Updated compliance score for mother {mother_id}: {annual_compliance}")
    return annual_compliance

def add_donor_contribution(db: Session, mother_id: str, donor_email: str, month_key: str, amount: float) -> dict:
    """Add a donor contribution for a specific mother and month."""
    try:
        if not isinstance(amount, (int, float)) or amount < 0:
            raise ValueError("Amount must be a non-negative number")
        if not month_key or not re.match(r"^\d{4}-[0-1][0-9]$", month_key):
            raise ValueError("Invalid month_key format. Expected YYYY-MM")

        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise ValueError(f"No mother found with generated_id {mother_id}")
        if not mother.donor_id:
            raise ValueError(f" {mother_id} has no assigned donor")

        donor = db.query(Donors).filter(Donors.email == donor_email).first()
        if not donor:
            raise ValueError(f"No donor found with email {donor_email}")
        if donor.donor_id != mother.donor_id:
            raise ValueError(f"Donor {donor_email} is not assigned to mother {mother_id}")

        existing_contribution = db.query(DonorContributions).filter(
            DonorContributions.mother_id == mother_id,
            DonorContributions.donor_id == donor.donor_id,
            DonorContributions.month_key == month_key
        ).first()
        if existing_contribution:
            raise ValueError(f"Donor contribution already exists for mother {mother_id} in {month_key}")

        savings = db.query(MonthlySavings).filter(
            MonthlySavings.mother_id == mother_id,
            MonthlySavings.month_key == month_key
        ).first()
        if not savings:
            savings = MonthlySavings(
                mother_id=mother_id,
                month_key=month_key,
                savings=0.0,
                milestone_score=0,
                donor_contribution=amount,
                partner_contribution=0.0
            )
            db.add(savings)
        else:
            savings.donor_contribution = amount
            savings.updated_at = datetime.utcnow()

        contribution = DonorContributions(
            donor_id=donor.donor_id,
            mother_id=mother_id,
            month_key=month_key,
            amount=amount
        )
        db.add(contribution)
        donor.total_contributions += amount
        mother.donor_contributions += amount
        mother.savings += amount
        mother.updated_at = datetime.utcnow()
        donor.updated_at = datetime.utcnow()
        db.flush()
        logger.info(f"Added donor contribution for mother {mother_id} by donor {donor.donor_id} in {month_key}: {amount}")
        db.commit()
        return {"message": f"Donor contribution of {amount} UGX added for mother {mother_id} in {month_key}"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding donor contribution: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error adding donor contribution: {str(e)}")

def add_partner_contribution(db: Session, mother_id: str, partner_id: str, month_key: str, amount: float) -> dict:
    """Add a partner match funding contribution for a specific mother and month."""
    try:
        if not isinstance(amount, (int, float)) or amount < 0:
            raise ValueError("Amount must be a non-negative number")
        if not month_key or not re.match(r"^\d{4}-[0-1][0-9]$", month_key):
            raise ValueError("Invalid month_key format. Expected YYYY-MM")

        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise ValueError(f"No mother found with generated_id {mother_id}")
        if mother.partner_id != partner_id:
            raise ValueError(f"Mother {mother_id} is not associated with partner {partner_id}")

        partner = db.query(Partners).filter(Partners.partner_id == partner_id).first()
        if not partner:
            raise ValueError(f"No partner found with partner_id {partner_id}")

        subscription = db.query(PartnerSubscriptions).filter(PartnerSubscriptions.partner_id == partner_id).first()
        if not subscription or subscription.subscription_status != "active":
            raise ValueError(f"Partner {partner_id} does not have an active subscription")

        max_contribution = 0
        if subscription.subscription_tier == "Basic":
            max_contribution = 100000
        elif subscription.subscription_tier == "Gold":
            max_contribution = 600000
        elif subscription.subscription_tier == "Platinum":
            max_contribution = 200000

        if amount > max_contribution:
            raise ValueError(f"Contribution amount {amount} exceeds maximum allowed ({max_contribution} UGX) for {subscription.subscription_tier} tier")

        existing_contribution = db.query(PartnerContributions).filter(
            PartnerContributions.mother_id == mother_id,
            PartnerContributions.partner_id == partner_id,
            PartnerContributions.month_key == month_key
        ).first()
        if existing_contribution:
            raise ValueError(f"Partner contribution already exists for mother {mother_id} in {month_key}")

        savings = db.query(MonthlySavings).filter(
            MonthlySavings.mother_id == mother_id,
            MonthlySavings.month_key == month_key
        ).first()
        if not savings:
            savings = MonthlySavings(
                mother_id=mother_id,
                month_key=month_key,
                savings=0.0,
                milestone_score=0,
                donor_contribution=0.0,
                partner_contribution=amount
            )
            db.add(savings)
        else:
            savings.partner_contribution = amount
            savings.updated_at = datetime.utcnow()

        contribution = PartnerContributions(
            partner_id=partner_id,
            mother_id=mother_id,
            month_key=month_key,
            amount=amount
        )
        db.add(contribution)
        partner.total_members = db.query(Mother).filter(Mother.partner_id == partner_id).count()
        mother.savings += amount
        mother.updated_at = datetime.utcnow()
        partner.updated_at = datetime.utcnow()
        db.flush()
        logger.info(f"Added partner contribution for mother {mother_id} by partner {partner_id} in {month_key}: {amount}")
        db.commit()
        return {"message": f"Partner contribution of {amount} UGX added for mother {mother_id} in {month_key}"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding partner contribution: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error adding partner contribution: {str(e)}")

def calculate_monthly_scores(db: Session, target_month: int = None) -> dict:
    """Calculate and update scores for all mothers at the end of the month."""
    try:
        current_date = datetime.now()
        current_month = current_date.month
        target_month = target_month if target_month is not None else (current_month - 1) if current_month > 1 else 12
        if not 1 <= target_month <= 12:
            raise ValueError(f"Target month {target_month} must be between 1 and 12")

        current_year = current_date.year
        month_key = f"{current_year}-{target_month:02d}"
        logger.info(f"Calculating scores for month: {month_key}")

        # Get all mothers in batches to reduce memory usage
        batch_size = 50
        offset = 0
        total_processed = 0
        
        while True:
            mothers = db.query(Mother).offset(offset).limit(batch_size).all()
            if not mothers:
                break
                
            logger.info(f"Processing batch of {len(mothers)} mothers (offset: {offset})")
            
            for mother in mothers:
                mother_id = mother.generated_id

                # Calculate milestone score
                expected_savings = calculate_expected_savings(mother.num_children)
                savings = db.query(MonthlySavings).filter(
                    MonthlySavings.mother_id == mother_id,
                    MonthlySavings.month_key == month_key
                ).first()
                
                if savings:
                    monthly_savings = float(savings.savings)
                    milestone_score = 1 if monthly_savings >= expected_savings else 0
                else:
                    monthly_savings = 0
                    milestone_score = 0

                # Update or create monthly_savings
                if savings:
                    savings.milestone_score = milestone_score
                    savings.updated_at = datetime.utcnow()
                else:
                    savings = MonthlySavings(
                        mother_id=mother_id,
                        month_key=month_key,
                        savings=monthly_savings,
                        milestone_score=milestone_score,
                        donor_contribution=0.0,
                        partner_contribution=0.0
                    )
                    db.add(savings)
                
                # Update activity points and compliance score in smaller transactions
                try:
                    activity_points = update_activity_points(db, mother_id, current_month)
                    compliance_score = update_compliance_score(db, mother_id, current_month)
                    
                    logger.info(f"Updated scores for mother {mother_id}: Milestone={milestone_score}, Activity Points={activity_points}, Compliance={compliance_score}")
                except Exception as e:
                    logger.error(f"Error updating scores for mother {mother_id}: {str(e)}")
                    continue
            
            # Commit batch to reduce transaction size
            db.commit()
            total_processed += len(mothers)
            offset += batch_size
            
            logger.info(f"Processed {total_processed} mothers so far")

        logger.info(f"Completed scoring calculation for month {month_key}. Total mothers processed: {total_processed}")
        return {"message": f"Scores calculated for month {month_key}. Total mothers processed: {total_processed}"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error calculating monthly scores: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error calculating monthly scores: {str(e)}")

def segment_mothers_and_analyze_trends(db: Session) -> dict:
    """Segment mothers based on compliance scores and analyze behavior trends."""
    try:
        current_month = datetime.now().month
        max_possible_score = current_month * 2

        mothers = db.query(Mother).all()
        if not mothers:
            return {"message": "No mothers found to segment"}

        high_compliance = []
        moderate_compliance = []
        low_compliance = []
        total_mothers = len(mothers)
        total_savings = 0
        total_activities = 0
        total_compliance_score = 0

        for mother in mothers:
            compliance_score = mother.compliance_score
            total_compliance_score += compliance_score

            mother_info = {
                "mother_id": mother.generated_id,
                "first_name": mother.first_name,
                "surname": mother.surname,
                "compliance_score": compliance_score,
                "total_savings": float(mother.savings),
                "activity_points": mother.activity_points,
                "donor_id": mother.donor_id,
                "partner_id": mother.partner_id
            }

            if compliance_score >= max_possible_score * 0.75:
                high_compliance.append(mother_info)
            elif compliance_score >= max_possible_score * 0.5:
                moderate_compliance.append(mother_info)
            else:
                low_compliance.append(mother_info)

            total_savings += float(mother.savings)
            total_activities += mother.activity_points

        avg_compliance_score = total_compliance_score / total_mothers if total_mothers > 0 else 0
        avg_savings_per_mother = total_savings / total_mothers if total_mothers > 0 else 0
        activity_participation_rate = (total_activities / (total_mothers * current_month)) * 100 if total_mothers > 0 else 0

        high_percentage = (len(high_compliance) / total_mothers) * 100 if total_mothers > 0 else 0
        moderate_percentage = (len(moderate_compliance) / total_mothers) * 100 if total_mothers > 0 else 0
        low_percentage = (len(low_compliance) / total_mothers) * 100 if total_mothers > 0 else 0

        insights = []
        if low_percentage > 50:
            insights.append(f"{low_percentage:.1f}% of mothers need intervention to increase engagement. Consider targeted outreach.")
        if activity_participation_rate < 50:
            insights.append(f"Only {activity_participation_rate:.1f}% of possible activities are being completed. Encourage more activity participation.")
        if avg_savings_per_mother < 1000 * current_month:
            insights.append(f"Average savings ({avg_savings_per_mother:.1f} UGX) is below expected ({1000 * current_month} UGX per mother). Promote savings initiatives.")

        return {
            "segmentation": {
                "high_compliance": {
                    "mothers": high_compliance,
                    "count": len(high_compliance),
                    "percentage": high_percentage
                },
                "moderate_compliance": {
                    "mothers": moderate_compliance,
                    "count": len(moderate_compliance),
                    "percentage": moderate_percentage
                },
                "low_compliance": {
                    "mothers": low_compliance,
                    "count": len(low_compliance),
                    "percentage": low_percentage
                }
            },
            "trends": {
                "total_mothers": total_mothers,
                "average_compliance_score": avg_compliance_score,
                "average_savings_per_mother": avg_savings_per_mother,
                "activity_participation_rate": activity_participation_rate
            },
            "insights": insights
        }
    except Exception as e:
        logger.error(f"Error segmenting mothers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error segmenting mothers: {str(e)}")

def assign_donor_to_mother(db: Session, mother_id: str, donor_email: str) -> dict:
    """Assign a donor to a mother, ensuring one-to-one matching."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise ValueError(f"No mother found with generated_id {mother_id}")
        
        if mother.donor_id:
            raise ValueError(f"Mother {mother_id} already has an assigned donor {mother.donor_id}")
        
        donor = db.query(Donors).filter(Donors.email == donor_email).first()
        if not donor:
            donor_id = str(uuid.uuid4())
            donor = Donors(
                donor_id=donor_id,
                first_name="Unknown",
                surname="Donor",
                email=donor_email,
                country_of_residence=None,
                preferred_activities=None
            )
            db.add(donor)
        else:
            donor_id = donor.donor_id
            existing_assignment = db.query(Mother).filter(Mother.donor_id == donor_id).first()
            if existing_assignment:
                raise ValueError(f"Donor {donor_email} already assigned to mother {existing_assignment.generated_id}")
        
        mother.donor_id = donor_id
        mother.updated_at = datetime.utcnow()
        db.commit()
        logger.info(f"Assigned donor {donor_id} to mother {mother_id}")
        return {"message": f"Donor {donor_email} assigned to mother {mother_id}"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error assigning donor to mother: {str(e)}")
        raise ValueError(f"Error assigning donor: {str(e)}")