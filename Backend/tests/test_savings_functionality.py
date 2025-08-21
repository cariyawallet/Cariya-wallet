"""
Tests for the enhanced savings functionality with transaction tracking.
"""
import pytest
import uuid
from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session

from tests.test_config import TestSessionLocal, SAMPLE_MOTHER_DATA, SAMPLE_SAVINGS_DATA
from utils.models import Mother, MonthlySavings, SavingsTransaction, Base
from utils.helpers import calculate_expected_savings, get_mother_transaction_summary, get_payment_method_statistics
from utils.unique_identifier_funcs import generate_unique_identifier


class TestSavingsFunctionality:
    """Test class for savings functionality."""
    
    @pytest.fixture(autoreuse=True)
    def db_session(self):
        """Create a test database session."""
        session = TestSessionLocal()
        try:
            # Create tables
            Base.metadata.create_all(bind=session.bind)
            yield session
        finally:
            session.close()
            # Drop tables
            Base.metadata.drop_all(bind=session.bind)
    
    @pytest.fixture
    def sample_mother(self, db_session: Session):
        """Create a sample mother for testing."""
        mother_id = generate_unique_identifier(
            SAMPLE_MOTHER_DATA["first_name"],
            SAMPLE_MOTHER_DATA["surname"],
            SAMPLE_MOTHER_DATA["mobile_number"],
            SAMPLE_MOTHER_DATA["num_children"],
            "/".join(map(str, SAMPLE_MOTHER_DATA["ages_of_children"]))
        )
        
        mother = Mother(
            generated_id=mother_id,
            **SAMPLE_MOTHER_DATA
        )
        db_session.add(mother)
        db_session.commit()
        return mother
    
    def test_calculate_expected_savings(self):
        """Test expected savings calculation."""
        # Test with different numbers of children
        assert calculate_expected_savings(1) == 1000.0
        assert calculate_expected_savings(3) == 3000.0
        assert calculate_expected_savings(5) == 5000.0
        
        # Test edge cases
        assert calculate_expected_savings(0) == 0.0
        
        # Test invalid input
        with pytest.raises(ValueError):
            calculate_expected_savings(-1)
    
    def test_savings_transaction_creation(self, db_session: Session, sample_mother: Mother):
        """Test creating a savings transaction."""
        # Create transaction data
        transaction_data = {
            "transaction_id": f"SAV{datetime.now().strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4())[:8]}",
            "mother_id": sample_mother.generated_id,
            "month_key": "2024-03",
            "amount": Decimal("2000.00"),
            "phone_number": "+256700000000",
            "payment_method": "Mobile Money",
            "transaction_status": "completed",
            "reference_number": "REF123456",
            "notes": "Test transaction"
        }
        
        # Create transaction
        transaction = SavingsTransaction(**transaction_data)
        db_session.add(transaction)
        db_session.commit()
        
        # Verify transaction was created
        assert transaction.id is not None
        assert transaction.transaction_id == transaction_data["transaction_id"]
        assert transaction.mother_id == sample_mother.generated_id
        assert transaction.amount == Decimal("2000.00")
        assert transaction.payment_method == "Mobile Money"
        assert transaction.transaction_status == "completed"
    
    def test_monthly_savings_aggregation(self, db_session: Session, sample_mother: Mother):
        """Test monthly savings aggregation from transactions."""
        month_key = "2024-03"
        
        # Create multiple transactions for the same month
        transactions = [
            {
                "transaction_id": f"SAV{datetime.now().strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4())[:8]}",
                "mother_id": sample_mother.generated_id,
                "month_key": month_key,
                "amount": Decimal("1000.00"),
                "phone_number": "+256700000000",
                "payment_method": "Mobile Money",
                "transaction_status": "completed"
            },
            {
                "transaction_id": f"SAV{datetime.now().strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4())[:8]}",
                "mother_id": sample_mother.generated_id,
                "month_key": month_key,
                "amount": Decimal("1500.00"),
                "phone_number": "+256700000000",
                "payment_method": "Cash",
                "transaction_status": "completed"
            }
        ]
        
        # Add transactions
        for t_data in transactions:
            transaction = SavingsTransaction(**t_data)
            db_session.add(transaction)
        db_session.commit()
        
        # Create monthly savings record
        monthly_savings = MonthlySavings(
            mother_id=sample_mother.generated_id,
            month_key=month_key,
            savings=Decimal("2500.00"),  # 1000 + 1500
            milestone_score=1,  # 2500 >= 2000 (expected for 2 children)
            donor_contribution=Decimal("0.00"),
            partner_contribution=Decimal("0.00")
        )
        db_session.add(monthly_savings)
        db_session.commit()
        
        # Verify monthly savings
        assert monthly_savings.savings == Decimal("2500.00")
        assert monthly_savings.milestone_score == 1
        
        # Verify milestone calculation
        expected_savings = calculate_expected_savings(sample_mother.num_children)
        assert expected_savings == 2000.0
        assert monthly_savings.savings >= expected_savings
    
    def test_transaction_summary(self, db_session: Session, sample_mother: Mother):
        """Test transaction summary functionality."""
        month_key = "2024-03"
        
        # Create transactions with different payment methods
        payment_methods = ["Mobile Money", "Cash", "Bank Transfer"]
        for i, method in enumerate(payment_methods):
            transaction = SavingsTransaction(
                transaction_id=f"SAV{datetime.now().strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4())[:8]}",
                mother_id=sample_mother.generated_id,
                month_key=month_key,
                amount=Decimal(f"{1000 + i * 500}.00"),
                phone_number="+256700000000",
                payment_method=method,
                transaction_status="completed"
            )
            db_session.add(transaction)
        db_session.commit()
        
        # Get transaction summary
        summary = get_mother_transaction_summary(db_session, sample_mother.generated_id, month_key)
        
        # Verify summary
        assert summary["mother_id"] == sample_mother.generated_id
        assert summary["month_key"] == month_key
        assert summary["total_transactions"] == 3
        assert summary["total_amount"] == 3000.0  # 1000 + 1500 + 2000
        
        # Verify payment method counts
        assert summary["payment_methods"]["Mobile Money"] == 1
        assert summary["payment_methods"]["Cash"] == 1
        assert summary["payment_methods"]["Bank Transfer"] == 1
        
        # Verify transaction statuses
        assert summary["transaction_statuses"]["completed"] == 3
    
    def test_payment_method_statistics(self, db_session: Session, sample_mother: Mother):
        """Test payment method statistics functionality."""
        month_key = "2024-03"
        
        # Create transactions with different payment methods
        payment_data = [
            ("Mobile Money", 1000),
            ("Mobile Money", 1500),
            ("Cash", 2000),
            ("Bank Transfer", 3000)
        ]
        
        for method, amount in payment_data:
            transaction = SavingsTransaction(
                transaction_id=f"SAV{datetime.now().strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4())[:8]}",
                mother_id=sample_mother.generated_id,
                month_key=month_key,
                amount=Decimal(f"{amount}.00"),
                phone_number="+256700000000",
                payment_method=method,
                transaction_status="completed"
            )
            db_session.add(transaction)
        db_session.commit()
        
        # Get payment method statistics
        stats = get_payment_method_statistics(db_session, month_key)
        
        # Verify statistics
        assert stats["month_key"] == month_key
        assert stats["total_transactions"] == 4
        assert stats["total_amount"] == 7500.0
        
        # Verify Mobile Money stats
        mobile_money = stats["payment_methods"]["Mobile Money"]
        assert mobile_money["count"] == 2
        assert mobile_money["total_amount"] == 2500.0
        assert mobile_money["percentage"] == 50.0
        
        # Verify Cash stats
        cash = stats["payment_methods"]["Cash"]
        assert cash["count"] == 1
        assert cash["total_amount"] == 2000.0
        assert cash["percentage"] == 25.0
        
        # Verify Bank Transfer stats
        bank_transfer = stats["payment_methods"]["Bank Transfer"]
        assert bank_transfer["count"] == 1
        assert bank_transfer["total_amount"] == 3000.0
        assert bank_transfer["percentage"] == 25.0
    
    def test_transaction_validation(self, db_session: Session, sample_mother: Mother):
        """Test transaction validation rules."""
        # Test invalid payment method
        with pytest.raises(Exception):  # Should fail due to invalid payment method
            transaction = SavingsTransaction(
                transaction_id=f"SAV{datetime.now().strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4())[:8]}",
                mother_id=sample_mother.generated_id,
                month_key="2024-03",
                amount=Decimal("1000.00"),
                phone_number="+256700000000",
                payment_method="Invalid Method",  # Invalid payment method
                transaction_status="completed"
            )
            db_session.add(transaction)
            db_session.commit()
        
        # Test invalid transaction status
        with pytest.raises(Exception):  # Should fail due to invalid status
            transaction = SavingsTransaction(
                transaction_id=f"SAV{datetime.now().strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4())[:8]}",
                mother_id=sample_mother.generated_id,
                month_key="2024-03",
                amount=Decimal("1000.00"),
                phone_number="+256700000000",
                payment_method="Mobile Money",
                transaction_status="invalid_status"  # Invalid status
            )
            db_session.add(transaction)
            db_session.commit()
    
    def test_milestone_score_calculation(self, db_session: Session, sample_mother: Mother):
        """Test milestone score calculation based on savings amount."""
        month_key = "2024-03"
        expected_savings = calculate_expected_savings(sample_mother.num_children)  # 2000 for 2 children
        
        # Test case 1: Below target (should get 0 points)
        below_target_savings = MonthlySavings(
            mother_id=sample_mother.generated_id,
            month_key=month_key,
            savings=Decimal("1500.00"),  # Below 2000 target
            milestone_score=0,
            donor_contribution=Decimal("0.00"),
            partner_contribution=Decimal("0.00")
        )
        db_session.add(below_target_savings)
        db_session.commit()
        
        # Verify milestone score
        assert below_target_savings.milestone_score == 0
        
        # Test case 2: At target (should get 1 point)
        at_target_savings = MonthlySavings(
            mother_id=sample_mother.generated_id,
            month_key="2024-04",
            savings=Decimal("2000.00"),  # Exactly at 2000 target
            milestone_score=1,
            donor_contribution=Decimal("0.00"),
            partner_contribution=Decimal("0.00")
        )
        db_session.add(at_target_savings)
        db_session.commit()
        
        # Verify milestone score
        assert at_target_savings.milestone_score == 1
        
        # Test case 3: Above target (should get 1 point)
        above_target_savings = MonthlySavings(
            mother_id=sample_mother.generated_id,
            month_key="2024-05",
            savings=Decimal("3000.00"),  # Above 2000 target
            milestone_score=1,
            donor_contribution=Decimal("0.00"),
            partner_contribution=Decimal("0.00")
        )
        db_session.add(above_target_savings)
        db_session.commit()
        
        # Verify milestone score
        assert above_target_savings.milestone_score == 1


if __name__ == "__main__":
    pytest.main([__file__])
