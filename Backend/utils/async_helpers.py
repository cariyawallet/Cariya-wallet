"""
Async helper functions for non-blocking scoring operations.
These functions can be used as alternatives to the synchronous versions
for better performance in async contexts.
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor
from utils.models import Mother, MonthlyActivityModel, MonthlySavings
from utils.helpers import calculate_expected_savings

logger = logging.getLogger(__name__)

async def calculate_monthly_scores_async(db: Session, target_month: int = None, executor: ThreadPoolExecutor = None) -> Dict[str, Any]:
    """
    Async version of calculate_monthly_scores that processes mothers in parallel batches.
    """
    if executor is None:
        executor = ThreadPoolExecutor(max_workers=4)
    
    try:
        current_date = datetime.now()
        current_month = current_date.month
        target_month = target_month if target_month is not None else (current_month - 1) if current_month > 1 else 12
        
        if not 1 <= target_month <= 12:
            raise ValueError(f"Target month {target_month} must be between 1 and 12")

        current_year = current_date.year
        month_key = f"{current_year}-{target_month:02d}"
        logger.info(f"Starting async scoring calculation for month: {month_key}")

        # Get total count of mothers
        total_mothers = db.query(Mother).count()
        if total_mothers == 0:
            return {"message": "No mothers found to process"}

        # Process in parallel batches
        batch_size = 25  # Smaller batches for parallel processing
        total_batches = (total_mothers + batch_size - 1) // batch_size
        
        logger.info(f"Processing {total_mothers} mothers in {total_batches} batches of {batch_size}")
        
        # Create tasks for each batch
        tasks = []
        for batch_num in range(total_batches):
            offset = batch_num * batch_size
            task = asyncio.create_task(
                process_mother_batch_async(db, offset, batch_size, month_key, current_month, executor)
            )
            tasks.append(task)
        
        # Wait for all batches to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        total_processed = 0
        errors = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
            else:
                total_processed += result.get('processed', 0)
        
        logger.info(f"Completed async scoring calculation for month {month_key}. "
                   f"Total mothers processed: {total_processed}")
        
        return {
            "message": f"Async scores calculated for month {month_key}",
            "total_processed": total_processed,
            "total_mothers": total_mothers,
            "errors": errors if errors else None
        }
        
    except Exception as e:
        logger.error(f"Error in async scoring calculation: {str(e)}")
        raise

async def process_mother_batch_async(
    db: Session, 
    offset: int, 
    batch_size: int, 
    month_key: str, 
    current_month: int,
    executor: ThreadPoolExecutor
) -> Dict[str, Any]:
    """
    Process a batch of mothers asynchronously.
    """
    loop = asyncio.get_event_loop()
    
    def process_batch():
        """Worker function to process batch in thread pool."""
        batch_db = db.bind.connect()
        try:
            mothers = batch_db.execute(
                text("SELECT generated_id, num_children FROM mothers LIMIT :limit OFFSET :offset"),
                {"limit": batch_size, "offset": offset}
            ).fetchall()
            
            processed = 0
            for mother_row in mothers:
                mother_id = mother_row[0]
                num_children = mother_row[1]
                
                try:
                    # Calculate expected savings
                    expected_savings = calculate_expected_savings(num_children)
                    
                    # Get or create monthly savings
                    savings_result = batch_db.execute(
                        text("""
                            SELECT savings, milestone_score FROM monthly_savings 
                            WHERE mother_id = :mother_id AND month_key = :month_key
                        """),
                        {"mother_id": mother_id, "month_key": month_key}
                    ).fetchone()
                    
                    if savings_result:
                        monthly_savings = float(savings_result[0])
                        milestone_score = 1 if monthly_savings >= expected_savings else 0
                        
                        # Update existing record
                        batch_db.execute(
                            text("""
                                UPDATE monthly_savings 
                                SET milestone_score = :milestone_score, updated_at = NOW()
                                WHERE mother_id = :mother_id AND month_key = :month_key
                            """),
                            {"milestone_score": milestone_score, "mother_id": mother_id, "month_key": month_key}
                        )
                    else:
                        milestone_score = 0
                        
                        # Create new record
                        batch_db.execute(
                            text("""
                                INSERT INTO monthly_savings 
                                (mother_id, month_key, savings, milestone_score, donor_contribution, partner_contribution, created_at, updated_at)
                                VALUES (:mother_id, :month_key, 0.0, :milestone_score, 0.0, 0.0, NOW(), NOW())
                            """),
                            {"mother_id": mother_id, "month_key": month_key, "milestone_score": milestone_score}
                        )
                    
                    processed += 1
                    
                except Exception as e:
                    logger.error(f"Error processing mother {mother_id}: {str(e)}")
                    continue
            
            batch_db.commit()
            return {"processed": processed}
            
        except Exception as e:
            batch_db.rollback()
            logger.error(f"Error processing batch (offset {offset}): {str(e)}")
            raise
        finally:
            batch_db.close()
    
    # Execute in thread pool
    return await loop.run_in_executor(executor, process_batch)

async def get_scoring_progress(db: Session) -> Dict[str, Any]:
    """
    Get the current progress of scoring operations.
    """
    try:
        total_mothers = db.query(Mother).count()
        current_month = datetime.now().month
        current_year = datetime.now().year
        month_key = f"{current_year}-{current_month:02d}"
        
        # Count mothers with updated scores for current month
        updated_count = db.query(MonthlySavings).filter(
            MonthlySavings.month_key == month_key
        ).count()
        
        return {
            "total_mothers": total_mothers,
            "updated_this_month": updated_count,
            "current_month": month_key,
            "progress_percentage": (updated_count / total_mothers * 100) if total_mothers > 0 else 0
        }
    except Exception as e:
        logger.error(f"Error getting scoring progress: {str(e)}")
        raise
