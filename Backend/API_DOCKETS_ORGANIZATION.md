# API Dockets Organization - FastAPI Endpoints

## Overview

The Cariya Wallet Backend API has been organized into logical dockets (groups) using FastAPI's tagging system. This organization makes the Swagger UI much more navigable and easier to understand for developers and API consumers.

## 🏷️ Docket Structure

### 1. **Partner Management** 🏢
*Partner-related operations including subscriptions, contributions, and profile management.*

**Endpoints:**
- `POST /partner/login` - Partner authentication
- `POST /partner/verify` - Partner verification
- `POST /addPartner` - Create new partner
- `GET /partners` - Get all partners
- `POST /addPartnerSubscription` - Add partner subscription
- `PUT /partnerSubscriptions/{subscription_id}` - Update subscription
- `GET /partnerSubscriptions/{partner_id}` - Get partner subscription
- `POST /addPartnerContribution` - Add partner contribution
- `GET /partners/{partner_id}/contributions` - Get partner contributions
- `GET /partners/{partner_id}` - Get partner profile
- `GET /partners/{partner_id}/activities` - Get partner activities

---

### 2. **Activity Management** 🎯
*Activity-related operations for mothers and partners.*

**Endpoints:**
- `POST /addActivity` - Create new activity
- `GET /activities` - Get all activities

---

### 3. **Donor Management** 💝
*Donor-related operations including donations and profile management.*

**Endpoints:**
- `POST /addDonor` - Create new donor
- `GET /donors` - Get all donors
- `GET /donors/{donor_id}` - Get donor profile
- `PUT /donors/{donor_id}` - Update donor
- `DELETE /donors/{donor_id}` - Delete donor
- `GET /donors/{donor_id}/donations` - Get donor donations
- `POST /addDonation` - Add donation

---

### 4. **Mother Management** 👩‍👧‍👦
*Mother-related operations including profiles, activities, and compliance.*

**Endpoints:**
- `POST /addMother` - Create new mother
- `GET /mothers/{mother_id}/donations` - Get mother donations
- `GET /mothers` - Get all mothers
- `GET /partners/{partner_id}/mothers` - Get mothers by partner
- `GET /mothers/{mother_id}` - Get mother profile
- `GET /mothers/{mother_id}/monthly-activities` - Get monthly activities
- `GET /mothers/{mother_id}/compliance` - Get compliance score

---

### 5. **Savings & Analytics** 💰📊
*Comprehensive savings tracking, transaction management, and analytics.*

**Endpoints:**
- `POST /mothers/{mother_id}/savings` - Add savings with transaction tracking
- `GET /mothers/{mother_id}/monthly-savings` - Get monthly savings (enhanced)
- `GET /monthly-savings` - Get all monthly savings
- `GET /savings-transactions` - Get savings transactions
- `GET /savings-transactions/{transaction_id}` - Get specific transaction
- `PUT /savings-transactions/{transaction_id}` - Update transaction
- `GET /mothers/{mother_id}/saving-streak` - Get saving streak
- `GET /mothers/{mother_id}/credit-score` - Get credit score
- `GET /mothers/{mother_id}/savings-analytics` - Get comprehensive analytics
- `GET /savings-analytics` - Get all mothers' analytics
- `GET /mothers/{mother_id}/transaction-summary` - Get transaction summary
- `GET /payment-method-statistics` - Get payment method statistics

---

### 6. **USSD Interface** 📱
*Mobile-optimized endpoints for USSD gateway integration.*

**Endpoints:**
- `GET /ussd/mothers/{mother_id}/total-savings` - Get total savings for USSD
- `GET /ussd/mothers/{mother_id}/months-saved` - Get months saved progress for USSD
- `GET /ussd/mothers/{mother_id}/latest-contributions` - Get latest contributions for USSD
- `GET /ussd/mothers/{mother_id}/quick-summary` - Get quick summary for USSD main menu
- `GET /ussd/mothers/{mother_id}/comprehensive-summary` - Get comprehensive summary (compliance, credit score, monthly savings)
- `POST /ussd/mothers/{mother_id}/set-reminder` - Set monthly saving reminder for USSD
- `POST /ussd/mothers/{mother_id}/menu-selection` - Handle USSD menu selections

---

### 6. **Donor View** 👀
*Donor-specific views and insights.*

**Endpoints:**
- `GET /donor-view` - Comprehensive donor view of all mothers

---

### 7. **Admin & System** ⚙️
*Administrative operations and system management.*

**Endpoints:**
- `POST /admin/trigger-scoring` - Trigger scoring job
- `GET /admin/scoring-status` - Get scoring status
- `POST /admin/trigger-async-scoring` - Trigger async scoring
- `GET /admin/scoring-progress` - Get scoring progress

---

## 🎯 Benefits of Docket Organization

### **1. Improved Navigation**
- **Logical Grouping**: Related endpoints are grouped together
- **Clear Categories**: Easy to find specific functionality
- **Reduced Cognitive Load**: Developers can focus on relevant sections

### **2. Better Documentation**
- **Organized Swagger UI**: Cleaner, more professional appearance
- **Easier Learning**: New developers can understand the API structure quickly
- **Focused Development**: Teams can work on specific dockets independently

### **3. Enhanced Maintainability**
- **Clear Separation**: Each docket has distinct responsibilities
- **Easier Testing**: Test suites can be organized by docket
- **Simplified Debugging**: Issues can be isolated to specific dockets

### **4. Professional Presentation**
- **Client-Friendly**: External developers can navigate the API easily
- **Enterprise Ready**: Professional appearance for business stakeholders
- **API Gateway Integration**: Easy to configure routing and policies

---

## 🔍 Swagger UI Navigation

### **Accessing the API Documentation**
```bash
# Start the server
uvicorn main:app --reload

# Access Swagger UI
http://localhost:8000/docs

# Access ReDoc (alternative documentation)
http://localhost:8000/redoc
```

### **Navigating by Docket**
1. **Open Swagger UI** at `/docs`
2. **Expand the docket** you want to explore
3. **Browse endpoints** within that docket
4. **Test endpoints** directly from the UI
5. **View schemas** and request/response models

---

## 📋 Endpoint Summary by Docket

| Docket | Endpoint Count | Primary Function |
|--------|----------------|------------------|
| **Partner Management** | 11 | Partner operations and subscriptions |
| **Activity Management** | 2 | Activity creation and management |
| **Donor Management** | 7 | Donor operations and donations |
| **Mother Management** | 7 | Mother profiles and compliance |
| **Savings & Analytics** | 12 | Financial tracking and analytics |
| **USSD Interface** | 7 | Mobile-optimized USSD endpoints |
| **Donor View** | 1 | Donor insights and views |
| **Admin & System** | 4 | System administration |

**Total Endpoints: 52**

---

## 🚀 Development Workflow

### **1. Adding New Endpoints**
```python
@app.post("/new-endpoint", tags=["Appropriate Docket"])
async def new_function():
    """Documentation for the new endpoint."""
    pass
```

### **2. Creating New Dockets**
```python
# =============================================================================
# NEW DOCKET NAME
# =============================================================================

@app.get("/endpoint", tags=["New Docket Name"])
async def function():
    pass
```

### **3. Maintaining Organization**
- **Consistent Tagging**: Always use the correct docket tag
- **Logical Grouping**: Place endpoints in the most appropriate docket
- **Clear Documentation**: Each endpoint should have descriptive docstrings

---

## 🔧 Customization Options

### **1. Docket Descriptions**
You can add descriptions to dockets using FastAPI's `openapi_tags`:

```python
app = FastAPI(
    title="Cariya Wallet Backend",
    openapi_tags=[
        {
            "name": "Partner Management",
            "description": "Partner-related operations including subscriptions, contributions, and profile management."
        },
        {
            "name": "Savings & Analytics",
            "description": "Comprehensive savings tracking, transaction management, and analytics."
        }
    ]
)
```

### **2. Docket Ordering**
Tags are displayed in the order they appear in the `openapi_tags` list.

### **3. Docket Icons**
You can add emojis or icons to docket names for visual appeal.

---

## 📚 Best Practices

### **1. Consistent Naming**
- Use clear, descriptive docket names
- Maintain consistent capitalization
- Use plural forms for resource collections

### **2. Logical Grouping**
- Group related functionality together
- Consider the user's mental model
- Separate concerns appropriately

### **3. Documentation Standards**
- Each endpoint should have a clear description
- Include examples where helpful
- Document error responses

### **4. Testing Organization**
- Organize tests by docket
- Use consistent test naming conventions
- Maintain test coverage per docket

---

## 🎉 Conclusion

The organized docket structure transforms the Cariya Wallet Backend API from a flat list of endpoints into a well-organized, professional API that's easy to navigate, understand, and maintain. This organization benefits:

- **Developers**: Easier navigation and understanding
- **API Consumers**: Clear structure and logical grouping
- **Business Stakeholders**: Professional, enterprise-ready appearance
- **Maintenance Teams**: Clear separation of concerns and responsibilities

The docket organization makes the API more accessible, maintainable, and professional while preserving all the functionality and power of the original implementation.
