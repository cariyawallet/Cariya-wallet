from datetime import datetime
import logging
import re
from sqlalchemy.orm import Session
from sqlalchemy import func
from utils.models import Mother, MonthlyActivityModel, MonthlySavings, SavingsTransaction, Donors, DonorContributions, Partners, PartnerSubscriptions, PartnerContributions
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

def update_compliance_score(db: Session, mother_id: str, current_month: int = None) -> int:
    """Update annual compliance score based on monthly data. Maximum score is 24 (2 points × 12 months)."""
    mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
    if not mother:
        raise ValueError(f"No mother found with generated_id {mother_id}")
    
    current_year = datetime.now().year
    
    # If no current_month specified, calculate for the full year (12 months)
    if current_month is None:
        current_month = 12
    
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
    # Always calculate for all 12 months to get proper annual score
    for month in range(1, 13):
        month_key = f"{current_year}-{month:02d}"
        milestone_score = savings_scores.get(month_key, 0)
        activity_point = 1 if month_key in activity_months else 0
        annual_compliance += milestone_score + activity_point
    
    mother.compliance_score = annual_compliance
    mother.updated_at = datetime.utcnow()
    db.flush()
    logger.info(f"Updated compliance score for mother {mother_id}: {annual_compliance}/24")
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
                    # Always calculate full annual compliance score (out of 24)
                    compliance_score = update_compliance_score(db, mother_id)
                    
                    logger.info(f"Updated scores for mother {mother_id}: Milestone={milestone_score}, Activity Points={activity_points}, Compliance={compliance_score}/24")
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
        # Maximum possible score is always 24 (2 points × 12 months)
        max_possible_score = 24

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

def get_mother_transaction_summary(db: Session, mother_id: str, month_key: str = None) -> dict:
    """Get a summary of transactions for a mother, optionally filtered by month."""
    try:
        query = db.query(SavingsTransaction).filter(SavingsTransaction.mother_id == mother_id)
        
        if month_key:
            query = query.filter(SavingsTransaction.month_key == month_key)
        
        transactions = query.all()
        
        if not transactions:
            return {
                "mother_id": mother_id,
                "month_key": month_key,
                "total_transactions": 0,
                "total_amount": 0.0,
                "payment_methods": {},
                "transaction_statuses": {}
            }
        
        total_amount = sum(float(t.amount) for t in transactions)
        payment_methods = {}
        transaction_statuses = {}
        
        for transaction in transactions:
            # Count payment methods
            method = transaction.payment_method
            payment_methods[method] = payment_methods.get(method, 0) + 1
            
            # Count transaction statuses
            status = transaction.transaction_status
            transaction_statuses[status] = transaction_statuses.get(status, 0) + 1
        
        return {
            "mother_id": mother_id,
            "month_key": month_key,
            "total_transactions": len(transactions),
            "total_amount": total_amount,
            "payment_methods": payment_methods,
            "transaction_statuses": transaction_statuses,
            "transactions": [{
                "transaction_id": t.transaction_id,
                "amount": float(t.amount),
                "payment_method": t.payment_method,
                "transaction_status": t.transaction_status,
                "created_at": t.created_at
            } for t in transactions]
        }
    except Exception as e:
        logger.error(f"Error getting transaction summary for mother {mother_id}: {str(e)}")
        raise

def get_payment_method_statistics(db: Session, month_key: str = None) -> dict:
    """Get statistics about payment methods used across all transactions."""
    try:
        query = db.query(SavingsTransaction)
        
        if month_key:
            query = query.filter(SavingsTransaction.month_key == month_key)
        
        transactions = query.all()
        
        if not transactions:
            return {"message": "No transactions found"}
        
        payment_methods = {}
        total_amount = 0.0
        
        for transaction in transactions:
            method = transaction.payment_method
            amount = float(transaction.amount)
            
            if method not in payment_methods:
                payment_methods[method] = {
                    "count": 0,
                    "total_amount": 0.0,
                    "percentage": 0.0
                }
            
            payment_methods[method]["count"] += 1
            payment_methods[method]["total_amount"] += amount
            total_amount += amount
        
        # Calculate percentages
        for method_data in payment_methods.values():
            method_data["percentage"] = (method_data["count"] / len(transactions)) * 100
        
        return {
            "month_key": month_key,
            "total_transactions": len(transactions),
            "total_amount": total_amount,
            "payment_methods": payment_methods
        }
    except Exception as e:
        logger.error(f"Error getting payment method statistics: {str(e)}")
        raise

def calculate_monthly_saving_streak(db: Session, mother_id: str, current_month: int = None) -> dict:
    """Calculate the monthly saving streak for a mother."""
    try:
        if current_month is None:
            current_month = datetime.now().month
        
        current_year = datetime.now().year
        
        # Get all monthly savings for the mother
        monthly_savings = db.query(MonthlySavings).filter(
            MonthlySavings.mother_id == mother_id
        ).order_by(MonthlySavings.month_key.desc()).all()
        
        if not monthly_savings:
            return {
                "mother_id": mother_id,
                "current_streak": 0,
                "longest_streak": 0,
                "total_months_saved": 0,
                "streak_details": []
            }
        
        # Calculate streak
        current_streak = 0
        longest_streak = 0
        temp_streak = 0
        total_months_saved = 0
        streak_details = []
        
        # Sort months in descending order (most recent first)
        sorted_months = sorted(monthly_savings, key=lambda x: x.month_key, reverse=True)
        
        for savings in sorted_months:
            year, month = savings.month_key.split('-')
            month_num = int(month)
            
            if savings.savings > 0:
                total_months_saved += 1
                
                # Check if this month is part of current streak
                if current_streak == 0:
                    # Start of a new streak
                    current_streak = 1
                    temp_streak = 1
                else:
                    # Check if this month is consecutive to the previous month
                    prev_savings = streak_details[-1] if streak_details else None
                    if prev_savings:
                        prev_year, prev_month = prev_savings["month_key"].split('-')
                        prev_month_num = int(prev_month)
                        
                        # Check if months are consecutive
                        if (int(year) == int(prev_year) and month_num == prev_month_num - 1) or \
                           (int(year) == int(prev_year) - 1 and month_num == 12 and prev_month_num == 1):
                            current_streak += 1
                            temp_streak += 1
                        else:
                            # Streak broken, start new streak
                            temp_streak = 1
                    else:
                        temp_streak = 1
                
                # Update longest streak
                longest_streak = max(longest_streak, temp_streak)
                
                streak_details.append({
                    "month_key": savings.month_key,
                    "savings": float(savings.savings),
                    "milestone_score": savings.milestone_score,
                    "streak_count": temp_streak
                })
            else:
                # No savings this month, streak broken
                temp_streak = 0
        
        return {
            "mother_id": mother_id,
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "total_months_saved": total_months_saved,
            "streak_details": streak_details
        }
        
    except Exception as e:
        logger.error(f"Error calculating saving streak for mother {mother_id}: {str(e)}")
        raise

def calculate_credit_score(db: Session, mother_id: str, month_key: str = None) -> dict:
    """Calculate credit score for a mother based on savings behavior."""
    try:
        # Get mother's information
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            raise ValueError(f"Mother {mother_id} not found")
        
        # Base credit score starts at 300 (minimum credit score)
        base_score = 300
        max_score = 850
        
        # Calculate factors
        factors = {}
        
        # 1. Savings consistency (40% of score)
        if month_key:
            # Calculate for specific month
            monthly_savings = db.query(MonthlySavings).filter(
                MonthlySavings.mother_id == mother_id,
                MonthlySavings.month_key == month_key
            ).first()
            
            if monthly_savings and monthly_savings.savings > 0:
                expected_savings = calculate_expected_savings(mother.num_children)
                savings_ratio = float(monthly_savings.savings) / expected_savings
                
                if savings_ratio >= 1.0:
                    factors["savings_consistency"] = 170  # Full points
                elif savings_ratio >= 0.8:
                    factors["savings_consistency"] = 136  # 80% of points
                elif savings_ratio >= 0.6:
                    factors["savings_consistency"] = 102  # 60% of points
                elif savings_ratio >= 0.4:
                    factors["savings_consistency"] = 68   # 40% of points
                else:
                    factors["savings_consistency"] = 34   # 20% of points
            else:
                factors["savings_consistency"] = 0
        else:
            # Calculate overall credit score
            monthly_savings = db.query(MonthlySavings).filter(
                MonthlySavings.mother_id == mother_id
            ).all()
            
            if monthly_savings:
                total_savings = sum(float(s.savings) for s in monthly_savings)
                total_expected = calculate_expected_savings(mother.num_children) * len(monthly_savings)
                overall_ratio = total_savings / total_expected if total_expected > 0 else 0
                
                if overall_ratio >= 1.0:
                    factors["savings_consistency"] = 170
                elif overall_ratio >= 0.8:
                    factors["savings_consistency"] = 136
                elif overall_ratio >= 0.6:
                    factors["savings_consistency"] = 102
                elif overall_ratio >= 0.4:
                    factors["savings_consistency"] = 68
                else:
                    factors["savings_consistency"] = 34
            else:
                factors["savings_consistency"] = 0
        
        # 2. Payment history (30% of score)
        if month_key:
            transactions = db.query(SavingsTransaction).filter(
                SavingsTransaction.mother_id == mother_id,
                SavingsTransaction.month_key == month_key
            ).all()
        else:
            transactions = db.query(SavingsTransaction).filter(
                SavingsTransaction.mother_id == mother_id
            ).all()
        
        if transactions:
            completed_transactions = sum(1 for t in transactions if t.transaction_status == "completed")
            total_transactions = len(transactions)
            completion_rate = completed_transactions / total_transactions
            
            if completion_rate >= 0.95:
                factors["payment_history"] = 127.5  # Full points
            elif completion_rate >= 0.9:
                factors["payment_history"] = 102
            elif completion_rate >= 0.8:
                factors["payment_history"] = 76.5
            elif completion_rate >= 0.7:
                factors["payment_history"] = 51
            else:
                factors["payment_history"] = 25.5
        else:
            factors["payment_history"] = 0
        
        # 3. Milestone achievement (20% of score)
        if month_key:
            monthly_savings = db.query(MonthlySavings).filter(
                MonthlySavings.mother_id == mother_id,
                MonthlySavings.month_key == month_key
            ).first()
            
            if monthly_savings and monthly_savings.milestone_score == 1:
                factors["milestone_achievement"] = 85
            else:
                factors["milestone_achievement"] = 0
        else:
            monthly_savings = db.query(MonthlySavings).filter(
                MonthlySavings.mother_id == mother_id
            ).all()
            
            if monthly_savings:
                milestone_count = sum(1 for s in monthly_savings if s.milestone_score == 1)
                total_months = len(monthly_savings)
                milestone_rate = milestone_count / total_months if total_months > 0 else 0
                factors["milestone_achievement"] = int(milestone_rate * 85)
            else:
                factors["milestone_achievement"] = 0
        
        # 4. Compliance score (10% of score)
        compliance_score = mother.compliance_score
        max_compliance = 24
        compliance_rate = compliance_score / max_compliance if max_compliance > 0 else 0
        factors["compliance_score"] = int(compliance_rate * 42.5)  # 10% of 850 = 42.5
        
        # Calculate total credit score
        total_score = base_score + sum(factors.values())
        total_score = min(total_score, max_score)  # Cap at maximum
        
        # Determine credit rating
        if total_score >= 800:
            credit_rating = "Excellent"
        elif total_score >= 740:
            credit_rating = "Very Good"
        elif total_score >= 670:
            credit_rating = "Good"
        elif total_score >= 580:
            credit_rating = "Fair"
        else:
            credit_rating = "Poor"
        
        return {
            "mother_id": mother_id,
            "month_key": month_key,
            "credit_score": total_score,
            "credit_rating": credit_rating,
            "base_score": base_score,
            "max_score": max_score,
            "factors": factors,
            "breakdown": {
                "savings_consistency": f"{factors.get('savings_consistency', 0)}/170 (40%)",
                "payment_history": f"{factors.get('payment_history', 0)}/127.5 (30%)",
                "milestone_achievement": f"{factors.get('milestone_achievement', 0)}/85 (20%)",
                "compliance_score": f"{factors.get('compliance_score', 0)}/42.5 (10%)"
            }
        }
        
    except Exception as e:
        logger.error(f"Error calculating credit score for mother {mother_id}: {str(e)}")
        raise

def get_comprehensive_savings_analytics(db: Session, mother_id: str = None, month_key: str = None) -> dict:
    """Get comprehensive savings analytics for a mother or all mothers."""
    try:
        if mother_id:
            # Get analytics for specific mother
            mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
            if not mother:
                raise ValueError(f"Mother {mother_id} not found")
            
            # Calculate all metrics
            saving_streak = calculate_monthly_saving_streak(db, mother_id, month_key)
            credit_score = calculate_credit_score(db, mother_id, month_key)
            
            # Get transaction summary
            transaction_summary = get_mother_transaction_summary(db, mother_id, month_key)
            
            # Get monthly savings
            monthly_savings = db.query(MonthlySavings).filter(
                MonthlySavings.mother_id == mother_id
            ).all()
            
            total_saved = sum(float(s.savings) for s in monthly_savings)
            total_expected = calculate_expected_savings(mother.num_children) * 12  # Annual expected
            
            return {
                "mother_id": mother_id,
                "mother_name": f"{mother.first_name} {mother.surname}",
                "month_key": month_key,
                "total_saved": total_saved,
                "total_expected": total_expected,
                "savings_ratio": total_saved / total_expected if total_expected > 0 else 0,
                "compliance_score": f"{mother.compliance_score}/24",
                "saving_streak": saving_streak,
                "credit_score": credit_score,
                "transaction_summary": transaction_summary,
                "monthly_breakdown": [
                    {
                        "month_key": s.month_key,
                        "savings": float(s.savings),
                        "milestone_score": s.milestone_score,
                        "donor_contribution": float(s.donor_contribution),
                        "partner_contribution": float(s.partner_contribution)
                    } for s in monthly_savings
                ]
            }
        else:
            # Get analytics for all mothers
            mothers = db.query(Mother).all()
            all_analytics = []
            
            for mother in mothers:
                try:
                    # Calculate basic metrics for each mother
                    monthly_savings = db.query(MonthlySavings).filter(
                        MonthlySavings.mother_id == mother.generated_id
                    ).all()
                    
                    total_saved = sum(float(s.savings) for s in monthly_savings)
                    total_expected = calculate_expected_savings(mother.num_children) * 12
                    
                    # Get saving streak
                    saving_streak = calculate_monthly_saving_streak(db, mother.generated_id)
                    
                    # Get credit score
                    credit_score = calculate_credit_score(db, mother.generated_id)
                    
                    all_analytics.append({
                        "mother_id": mother.generated_id,
                        "mother_name": f"{mother.first_name} {mother.surname}",
                        "total_saved": total_saved,
                        "total_expected": total_expected,
                        "savings_ratio": total_saved / total_expected if total_expected > 0 else 0,
                        "compliance_score": f"{mother.compliance_score}/24",
                        "current_streak": saving_streak["current_streak"],
                        "longest_streak": saving_streak["longest_streak"],
                        "credit_score": credit_score["credit_score"],
                        "credit_rating": credit_score["credit_rating"]
                    })
                except Exception as e:
                    logger.error(f"Error calculating analytics for mother {mother.generated_id}: {str(e)}")
                    continue
            
            # Sort by total saved (descending)
            all_analytics.sort(key=lambda x: x["total_saved"], reverse=True)
            
            return {
                "month_key": month_key,
                "total_mothers": len(all_analytics),
                "total_savings_across_all": sum(x["total_saved"] for x in all_analytics),
                "average_savings_per_mother": sum(x["total_saved"] for x in all_analytics) / len(all_analytics) if all_analytics else 0,
                "mothers_analytics": all_analytics
            }
            
    except Exception as e:
        logger.error(f"Error getting comprehensive savings analytics: {str(e)}")
        raise

def get_mother_total_savings_ussd(db: Session, mother_id: str) -> dict:
    """Get mother's total savings formatted for USSD display."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            return {
                "success": False,
                "message": "Mother not found",
                "ussd_text": "CON Mother not found. Please try again.\n0. Back to main menu"
            }
        
        # Get total savings from monthly savings table
        monthly_savings = db.query(MonthlySavings).filter(
            MonthlySavings.mother_id == mother_id
        ).all()
        
        total_saved = sum(float(s.savings) for s in monthly_savings)
        expected_savings = calculate_expected_savings(mother.num_children) * 12  # Annual expected
        
        # Format for USSD display
        ussd_text = f"CON Your Savings Summary\n"
        ussd_text += f"Total Saved: UGX {total_saved:,.0f}\n"
        ussd_text += f"Expected: UGX {expected_savings:,.0f}\n"
        
        if expected_savings > 0:
            percentage = (total_saved / expected_savings) * 100
            ussd_text += f"Progress: {percentage:.1f}%\n"
        
        ussd_text += f"\n0. Back to main menu"
        
        return {
            "success": True,
            "mother_name": f"{mother.first_name} {mother.surname}",
            "total_saved": total_saved,
            "expected_savings": expected_savings,
            "percentage": percentage if expected_savings > 0 else 0,
            "ussd_text": ussd_text
        }
        
    except Exception as e:
        logger.error(f"Error getting total savings for USSD (mother {mother_id}): {str(e)}")
        return {
            "success": False,
            "message": f"Error retrieving savings: {str(e)}",
            "ussd_text": "CON Error retrieving your savings. Please try again later.\n0. Back to main menu"
        }

def get_mother_months_saved_ussd(db: Session, mother_id: str, year: int = None) -> dict:
    """Get mother's months saved out of 12 for the year, formatted for USSD."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            return {
                "success": False,
                "message": "Mother not found",
                "ussd_text": "CON Mother not found. Please try again.\n0. Back to main menu"
            }
        
        if year is None:
            year = datetime.now().year
        
        # Get monthly savings for the specified year
        monthly_savings = db.query(MonthlySavings).filter(
            MonthlySavings.mother_id == mother_id,
            MonthlySavings.month_key.like(f"{year}-%")
        ).all()
        
        # Count months with savings > 0
        months_with_savings = sum(1 for s in monthly_savings if s.savings > 0)
        
        # Create month breakdown
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        saved_months = []
        for s in monthly_savings:
            if s.savings > 0:
                month_num = int(s.month_key.split('-')[1])
                saved_months.append(month_names[month_num - 1])
        
        # Format for USSD display
        ussd_text = f"CON Savings Progress {year}\n"
        ussd_text += f"Months Saved: {months_with_savings}/12\n"
        
        if saved_months:
            ussd_text += f"Saved in: {', '.join(saved_months[:6])}"  # Limit for USSD
            if len(saved_months) > 6:
                ussd_text += f" +{len(saved_months) - 6} more"
            ussd_text += "\n"
        
        # Show progress bar
        progress_chars = "█" * (months_with_savings // 2) + "░" * ((12 - months_with_savings) // 2)
        ussd_text += f"Progress: [{progress_chars}]\n"
        ussd_text += f"\n0. Back to main menu"
        
        return {
            "success": True,
            "mother_name": f"{mother.first_name} {mother.surname}",
            "year": year,
            "months_saved": months_with_savings,
            "total_months": 12,
            "saved_months": saved_months,
            "ussd_text": ussd_text
        }
        
    except Exception as e:
        logger.error(f"Error getting months saved for USSD (mother {mother_id}): {str(e)}")
        return {
            "success": False,
            "message": f"Error retrieving months data: {str(e)}",
            "ussd_text": "CON Error retrieving months data. Please try again later.\n0. Back to main menu"
        }

def get_mother_latest_contributions_ussd(db: Session, mother_id: str, limit: int = 5) -> dict:
    """Get mother's latest contributions formatted for USSD display."""
    try:
        mother = db.query(Mother).filter(Mother.generated_id == mother_id).first()
        if not mother:
            return {
                "success": False,
                "message": "Mother not found",
                "ussd_text": "CON Mother not found. Please try again.\n0. Back to main menu"
            }
        
        # Get latest savings transactions
        transactions = db.query(SavingsTransaction).filter(
            SavingsTransaction.mother_id == mother_id,
            SavingsTransaction.transaction_status == "completed"
        ).order_by(SavingsTransaction.created_at.desc()).limit(limit).all()
        
        if not transactions:
            ussd_text = f"CON No contributions found\n"
            ussd_text += f"Start saving today!\n"
            ussd_text += f"\n0. Back to main menu"
            
            return {
                "success": True,
                "mother_name": f"{mother.first_name} {mother.surname}",
                "contributions": [],
                "ussd_text": ussd_text
            }
        
        # Format for USSD display
        ussd_text = f"CON Latest Contributions\n"
        
        contributions = []
        for i, transaction in enumerate(transactions, 1):
            amount = float(transaction.amount)
            date_str = transaction.created_at.strftime("%d/%m/%y")
            tx_id_short = transaction.transaction_id[-6:]  # Last 6 chars
            
            contributions.append({
                "amount": amount,
                "date": date_str,
                "transaction_id": transaction.transaction_id,
                "transaction_id_short": tx_id_short,
                "payment_method": transaction.payment_method
            })
            
            ussd_text += f"{i}. UGX {amount:,.0f} - {date_str}\n"
            ussd_text += f"   ID: {tx_id_short} ({transaction.payment_method})\n"
        
        ussd_text += f"\n0. Back to main menu"
        
        return {
            "success": True,
            "mother_name": f"{mother.first_name} {mother.surname}",
            "contributions": contributions,
            "ussd_text": ussd_text
        }
        
    except Exception as e:
        logger.error(f"Error getting latest contributions for USSD (mother {mother_id}): {str(e)}")
        return {
            "success": False,
            "message": f"Error retrieving contributions: {str(e)}",
            "ussd_text": "CON Error retrieving contributions. Please try again later.\n0. Back to main menu"
        }