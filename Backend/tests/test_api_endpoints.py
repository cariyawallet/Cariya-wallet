"""
Tests for the API endpoints including enhanced savings functionality.
"""
import pytest
import json
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_config import TestSessionLocal, SAMPLE_MOTHER_DATA, SAMPLE_SAVINGS_DATA
from utils.models import Mother, Base
from utils.unique_identifier_funcs import generate_unique_identifier
from main import app

# Create test client
client = TestClient(app)


class TestAPIEndpoints:
    """Test class for API endpoints."""
    
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
    
    def test_add_savings_endpoint(self, sample_mother: Mother):
        """Test the add savings endpoint."""
        savings_data = {
            "amount": 2000.0,
            "month": 3,
            "phone_number": "+256700000000",
            "payment_method": "Mobile Money",
            "reference_number": "REF123456",
            "notes": "Test savings entry"
        }
        
        response = client.post(
            f"/mothers/{sample_mother.generated_id}/savings",
            json=savings_data
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "transaction_id" in data
        assert "monthly_savings" in data
        assert "total_savings" in data
        assert "expected_savings" in data
        assert "milestone_score" in data
        assert "compliance_score" in data
        assert "payment_method" in data
        assert "phone_number" in data
        
        # Verify values
        assert data["monthly_savings"] == 2000.0
        assert data["expected_savings"] == 2000.0  # 2 children × 1000
        assert data["milestone_score"] == 1  # Met target
        assert data["payment_method"] == "Mobile Money"
        assert data["phone_number"] == "+256700000000"
    
    def test_add_savings_validation(self, sample_mother: Mother):
        """Test savings endpoint validation."""
        # Test invalid amount
        invalid_data = {
            "amount": -100.0,
            "month": 3,
            "phone_number": "+256700000000",
            "payment_method": "Mobile Money"
        }
        
        response = client.post(
            f"/mothers/{sample_mother.generated_id}/savings",
            json=invalid_data
        )
        
        assert response.status_code == 400
        assert "Savings amount cannot be negative" in response.json()["detail"]
        
        # Test invalid payment method
        invalid_data = {
            "amount": 1000.0,
            "month": 3,
            "phone_number": "+256700000000",
            "payment_method": "Invalid Method"
        }
        
        response = client.post(
            f"/mothers/{sample_mother.generated_id}/savings",
            json=invalid_data
        )
        
        assert response.status_code == 400
        assert "Invalid payment method" in response.json()["detail"]
        
        # Test invalid phone number
        invalid_data = {
            "amount": 1000.0,
            "month": 3,
            "phone_number": "1234567890",  # Invalid format
            "payment_method": "Mobile Money"
        }
        
        response = client.post(
            f"/mothers/{sample_mother.generated_id}/savings",
            json=invalid_data
        )
        
        assert response.status_code == 400
        assert "Phone number must be in format" in response.json()["detail"]
    
    def test_get_savings_transactions_endpoint(self, sample_mother: Mother):
        """Test the get savings transactions endpoint."""
        # First add some savings to create transactions
        savings_data = {
            "amount": 2000.0,
            "month": 3,
            "phone_number": "+256700000000",
            "payment_method": "Mobile Money"
        }
        
        client.post(
            f"/mothers/{sample_mother.generated_id}/savings",
            json=savings_data
        )
        
        # Test getting all transactions
        response = client.get("/savings-transactions")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Verify transaction structure
        transaction = data[0]
        assert "transaction_id" in transaction
        assert "mother_id" in transaction
        assert "month_key" in transaction
        assert "amount" in transaction
        assert "phone_number" in transaction
        assert "payment_method" in transaction
        assert "transaction_status" in transaction
        
        # Test filtering by mother_id
        response = client.get(f"/savings-transactions?mother_id={sample_mother.generated_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        for transaction in data:
            assert transaction["mother_id"] == sample_mother.generated_id
        
        # Test filtering by month
        response = client.get("/savings-transactions?month=2024-03")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        for transaction in data:
            assert transaction["month_key"] == "2024-03"
        
        # Test filtering by payment method
        response = client.get("/savings-transactions?payment_method=Mobile Money")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        for transaction in data:
            assert transaction["payment_method"] == "Mobile Money"
    
    def test_get_savings_transaction_by_id(self, sample_mother: Mother):
        """Test getting a specific savings transaction by ID."""
        # First add savings to create a transaction
        savings_data = {
            "amount": 2000.0,
            "month": 3,
            "phone_number": "+256700000000",
            "payment_method": "Mobile Money"
        }
        
        response = client.post(
            f"/mothers/{sample_mother.generated_id}/savings",
            json=savings_data
        )
        
        transaction_id = response.json()["transaction_id"]
        
        # Test getting the specific transaction
        response = client.get(f"/savings-transactions/{transaction_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["transaction_id"] == transaction_id
        assert data["mother_id"] == sample_mother.generated_id
        assert data["amount"] == 2000.0
        assert data["payment_method"] == "Mobile Money"
        
        # Test getting non-existent transaction
        response = client.get("/savings-transactions/NONEXISTENT")
        assert response.status_code == 404
    
    def test_update_savings_transaction(self, sample_mother: Mother):
        """Test updating a savings transaction."""
        # First add savings to create a transaction
        savings_data = {
            "amount": 2000.0,
            "month": 3,
            "phone_number": "+256700000000",
            "payment_method": "Mobile Money"
        }
        
        response = client.post(
            f"/mothers/{sample_mother.generated_id}/savings",
            json=savings_data
        )
        
        transaction_id = response.json()["transaction_id"]
        
        # Test updating transaction status
        update_data = {
            "transaction_status": "failed",
            "notes": "Transaction failed due to insufficient funds"
        }
        
        response = client.put(
            f"/savings-transactions/{transaction_id}",
            json=update_data
        )
        
        assert response.status_code == 200
        assert "updated successfully" in response.json()["message"]
        
        # Verify the update
        response = client.get(f"/savings-transactions/{transaction_id}")
        data = response.json()
        assert data["transaction_status"] == "failed"
        assert data["notes"] == "Transaction failed due to insufficient funds"
    
    def test_get_mother_transaction_summary(self, sample_mother: Mother):
        """Test the mother transaction summary endpoint."""
        # First add multiple savings entries
        savings_entries = [
            {
                "amount": 1000.0,
                "month": 3,
                "phone_number": "+256700000000",
                "payment_method": "Mobile Money"
            },
            {
                "amount": 1500.0,
                "month": 3,
                "phone_number": "+256700000000",
                "payment_method": "Cash"
            }
        ]
        
        for entry in savings_entries:
            client.post(
                f"/mothers/{sample_mother.generated_id}/savings",
                json=entry
            )
        
        # Test getting transaction summary
        response = client.get(f"/mothers/{sample_mother.generated_id}/transaction-summary")
        assert response.status_code == 200
        
        data = response.json()
        assert data["mother_id"] == sample_mother.generated_id
        assert data["total_transactions"] == 2
        assert data["total_amount"] == 2500.0
        
        # Test filtering by month
        response = client.get(f"/mothers/{sample_mother.generated_id}/transaction-summary?month=2024-03")
        assert response.status_code == 200
        
        data = response.json()
        assert data["month_key"] == "2024-03"
        assert data["total_transactions"] == 2
    
    def test_get_payment_method_statistics(self, sample_mother: Mother):
        """Test the payment method statistics endpoint."""
        # First add savings with different payment methods
        savings_entries = [
            {
                "amount": 1000.0,
                "month": 3,
                "phone_number": "+256700000000",
                "payment_method": "Mobile Money"
            },
            {
                "amount": 2000.0,
                "month": 3,
                "phone_number": "+256700000000",
                "payment_method": "Cash"
            },
            {
                "amount": 3000.0,
                "month": 3,
                "phone_number": "+256700000000",
                "payment_method": "Bank Transfer"
            }
        ]
        
        for entry in savings_entries:
            client.post(
                f"/mothers/{sample_mother.generated_id}/savings",
                json=entry
            )
        
        # Test getting payment method statistics
        response = client.get("/payment-method-statistics")
        assert response.status_code == 200
        
        data = response.json()
        assert data["total_transactions"] == 3
        assert data["total_amount"] == 6000.0
        
        # Verify payment method breakdown
        assert "Mobile Money" in data["payment_methods"]
        assert "Cash" in data["payment_methods"]
        assert "Bank Transfer" in data["payment_methods"]
        
        # Test filtering by month
        response = client.get("/payment-method-statistics?month=2024-03")
        assert response.status_code == 200
        
        data = response.json()
        assert data["month_key"] == "2024-03"
    
    def test_get_monthly_savings_endpoint(self, sample_mother: Mother):
        """Test the monthly savings endpoint."""
        # First add savings
        savings_data = {
            "amount": 2000.0,
            "month": 3,
            "phone_number": "+256700000000",
            "payment_method": "Mobile Money"
        }
        
        client.post(
            f"/mothers/{sample_mother.generated_id}/savings",
            json=savings_data
        )
        
        # Test getting monthly savings for specific mother
        response = client.get(f"/mothers/{sample_mother.generated_id}/monthly-savings")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Verify structure
        savings = data[0]
        assert "month_key" in savings
        assert "savings" in savings
        assert "milestone_score" in savings
        assert "donor_contribution" in savings
        
        # Test getting all monthly savings
        response = client.get("/monthly-savings")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Test filtering by month
        response = client.get("/monthly-savings?month=2024-03")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        for savings in data:
            assert savings["month_key"] == "2024-03"


if __name__ == "__main__":
    pytest.main([__file__])
