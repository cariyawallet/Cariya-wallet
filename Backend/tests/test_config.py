"""
Test configuration for Cariya Wallet Backend tests.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Test database configuration
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", 
    "postgresql://test_user:test_password@localhost:5432/cariya_test_db"
)

# Test engine
test_engine = create_engine(
    TEST_DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False  # Set to True for SQL debugging in tests
)

# Test session factory
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Test data constants
VALID_PAYMENT_METHODS = ["Mobile Money", "Bank Transfer", "Cash", "Card", "Other"]
VALID_TRANSACTION_STATUSES = ["pending", "completed", "failed", "cancelled"]

# Sample test data
SAMPLE_MOTHER_DATA = {
    "first_name": "Test",
    "surname": "Mother",
    "mobile_number": "+256700000000",
    "num_children": 2,
    "ages_of_children": [5, 8],
    "partner_id": None,
    "location": "Test Location"
}

SAMPLE_SAVINGS_DATA = {
    "amount": 2000.0,
    "month": 3,
    "phone_number": "+256700000000",
    "payment_method": "Mobile Money",
    "reference_number": "REF123456",
    "notes": "Test savings entry"
}
