from datetime import datetime
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import Mother, MonthlyActivityModel, MonthlySavings
from fastapi import HTTPException

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
    activity_points = 0
    for month in range(1, current_month + 1):
        month_key = f"{current_year}-{month:02d}"
        activity_count = db.query(MonthlyActivityModel).filter(
            MonthlyActivityModel.mother_id == mother_id,
            MonthlyActivityModel.month_key == month_key
        ).count()
        if activity_count > 0:
            activity_points += 1  # 1 point per month with at least one activity
    
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
    annual_compliance = 0
    
    for month in range(1, current_month + 1):
        month_key = f"{current_year}-{month:02d}"
        savings = db.query(MonthlySavings).filter(
            MonthlySavings.mother_id == mother_id,
            MonthlySavings.month_key == month_key
        ).first()
        activity = db.query(MonthlyActivityModel).filter(
            MonthlyActivityModel.mother_id == mother_id,
            MonthlyActivityModel.month_key == month_key
        ).first()
        milestone_score = savings.milestone_score if savings else 0
        activity_point = 1 if activity else 0
        annual_compliance += milestone_score + activity_point
    
    mother.compliance_score = annual_compliance
    mother.updated_at = datetime.utcnow()
    db.flush()
    logger.info(f"Updated compliance score for mother {mother_id}: {annual_compliance}")
    return annual_compliance

def calculate_donor_contribution(db: Session, mother_id: str, target_month: int) -> float:
    """Calculate donor contribution for a mother in a specific month."""
    mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
    if not mother:
        raise ValueError(f"No mother found with generated_id {mother_id}")

    current_year = datetime.now().year
    month_key = f"{current_year}-{target_month:02d}"
    activity = db.query(MonthlyActivityModel).filter(
        MonthlyActivityModel.mother_id == mother_id,
        MonthlyActivityModel.month_key == month_key
    ).first()
    savings = db.query(MonthlySavings).filter(
        MonthlySavings.mother_id == mother_id,
        MonthlySavings.month_key == month_key
    ).first()

    # Check if mother has an activity for the month
    if not activity:
        return 0.0  # No activity, no donor contribution

    # Check savings for the month
    if savings and savings.savings > 0:
        donor_contribution = float(savings.savings)  # Donor matches the savings
    else:
        return 0.0  # No savings, no donor contribution

    # Update monthly_savings with donor contribution
    if savings:
        savings.donor_contribution = donor_contribution
        savings.updated_at = datetime.utcnow()
    else:
        savings = MonthlySavings(
            mother_id=mother_id,
            month_key=month_key,
            savings=0.0,
            milestone_score=0,
            donor_contribution=donor_contribution
        )
        db.add(savings)

    # Update mother's total savings and donor contributions
    mother.donor_contributions += donor_contribution
    mother.savings += donor_contribution
    mother.updated_at = datetime.utcnow()
    db.flush()
    logger.info(f"Calculated donor contribution for mother {mother_id} in {month_key}: {donor_contribution}")
    return donor_contribution

def calculate_monthly_scores(db: Session, target_month: int = None) -> dict:
    """Calculate and update scores for all mothers at the end of the month, including donor contributions."""
    try:
        current_date = datetime.now()
        current_month = current_date.month
        target_month = target_month if target_month is not None else (current_month - 1) if current_month > 1 else 12
        if not 1 <= target_month <= 12:
            raise ValueError(f"Target month {target_month} must be between 1 and 12")

        current_year = current_date.year
        month_key = f"{current_year}-{target_month:02d}"
        logger.info(f"Calculating scores for month: {month_key}")

        mothers = db.query(Mother).all()
        if not mothers:
            return {"message": "No mothers found to process"}

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
                    donor_contribution=0.0
                )
                db.add(savings)
            db.flush()

            # Calculate donor contribution
            donor_contribution = calculate_donor_contribution(db, mother_id, target_month)

            # Update activity points
            activity_points = update_activity_points(db, mother_id, current_month)

            # Update compliance score
            compliance_score = update_compliance_score(db, mother_id, current_month)

            logger.info(f"Updated scores for mother {mother_id}: Milestone={milestone_score}, Activity Points={activity_points}, Compliance={compliance_score}, Donor Contribution={donor_contribution}")

        db.commit()
        return {"message": f"Scores and donor contributions calculated for month {month_key}"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error calculating monthly scores: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error calculating monthly scores: {str(e)}")

def segment_mothers_and_analyze_trends(db: Session) -> dict:
    """Segment mothers based on compliance scores and analyze behavior trends."""
    try:
        current_month = datetime.now().month
        max_possible_score = current_month * 2  # 2 points per month (milestone + activity)

        mothers = db.query(Mother).all()
        if not mothers:
            return {"message": "No mothers found to segment"}

        # Segmentation
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

            # Classify mother
            mother_info = {
                "mother_id": mother.generated_id,
                "first_name": mother.first_name,
                "surname": mother.surname,
                "compliance_score": compliance_score,
                "total_savings": float(mother.savings),
                "activity_points": mother.activity_points
            }

            # Adjust classification based on current max possible score
            if compliance_score >= max_possible_score * 0.75:  # Top 75% of possible score
                high_compliance.append(mother_info)
            elif compliance_score >= max_possible_score * 0.5:  # Top 50% of possible score
                moderate_compliance.append(mother_info)
            else:
                low_compliance.append(mother_info)

            # Collect data for trends
            total_savings += float(mother.savings)
            total_activities += mother.activity_points

        # Calculate trends and insights
        avg_compliance_score = total_compliance_score / total_mothers if total_mothers > 0 else 0
        avg_savings_per_mother = total_savings / total_mothers if total_mothers > 0 else 0
        activity_participation_rate = (total_activities / (total_mothers * current_month)) * 100 if total_mothers > 0 else 0

        high_percentage = (len(high_compliance) / total_mothers) * 100 if total_mothers > 0 else 0
        moderate_percentage = (len(moderate_compliance) / total_mothers) * 100 if total_mothers > 0 else 0
        low_percentage = (len(low_compliance) / total_mothers) * 100 if total_mothers > 0 else 0

        # Insights
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