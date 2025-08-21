# Savings Analytics API - Comprehensive Documentation

## Overview

The Cariya Wallet Backend now provides comprehensive savings analytics including accumulated total saved, monthly saving streaks, compliance scores, and credit scores. These analytics can be retrieved for individual mothers or across all mothers in the system.

## New Analytics Features

### 1. Monthly Saving Streak
- **Current Streak**: Number of consecutive months with savings
- **Longest Streak**: Best consecutive savings streak achieved
- **Total Months Saved**: Total number of months with any savings
- **Streak Details**: Month-by-month breakdown of savings and streak counts

### 2. Credit Score System
- **Base Score**: 300 (minimum credit score)
- **Maximum Score**: 850 (excellent credit score)
- **Scoring Factors**:
  - **Savings Consistency (40%)**: 170 points based on meeting expected savings targets
  - **Payment History (30%)**: 127.5 points based on transaction completion rates
  - **Milestone Achievement (20%)**: 85 points based on meeting monthly savings goals
  - **Compliance Score (10%)**: 42.5 points based on overall compliance (out of 24)

### 3. Comprehensive Analytics
- **Total Saved vs Expected**: Comparison of actual vs target savings
- **Savings Ratio**: Percentage of expected savings achieved
- **Monthly Breakdown**: Detailed monthly savings with milestone scores
- **Transaction Summary**: Payment method statistics and transaction counts

## API Endpoints

### 1. Monthly Saving Streak

#### Get Mother's Saving Streak
```http
GET /mothers/{mother_id}/saving-streak?month={month}
```

**Parameters:**
- `mother_id` (required): Unique identifier of the mother
- `month` (optional): Specific month (1-12) for streak calculation

**Response:**
```json
{
    "mother_id": "MOTHER123",
    "current_streak": 3,
    "longest_streak": 5,
    "total_months_saved": 8,
    "streak_details": [
        {
            "month_key": "2024-03",
            "savings": 2000.0,
            "milestone_score": 1,
            "streak_count": 3
        },
        {
            "month_key": "2024-02",
            "savings": 1800.0,
            "milestone_score": 1,
            "streak_count": 2
        }
    ]
}
```

### 2. Credit Score

#### Get Mother's Credit Score
```http
GET /mothers/{mother_id}/credit-score?month={month}
```

**Parameters:**
- `mother_id` (required): Unique identifier of the mother
- `month` (optional): Specific month (YYYY-MM) for monthly credit score

**Response:**
```json
{
    "mother_id": "MOTHER123",
    "month_key": "2024-03",
    "credit_score": 745,
    "credit_rating": "Good",
    "base_score": 300,
    "max_score": 850,
    "factors": {
        "savings_consistency": 136,
        "payment_history": 127.5,
        "milestone_achievement": 85,
        "compliance_score": 38
    },
    "breakdown": {
        "savings_consistency": "136/170 (40%)",
        "payment_history": "127.5/127.5 (30%)",
        "milestone_achievement": "85/85 (20%)",
        "compliance_score": "38/42.5 (10%)"
    }
}
```

**Credit Rating Scale:**
- **800-850**: Excellent
- **740-799**: Very Good
- **670-739**: Good
- **580-669**: Fair
- **300-579**: Poor

### 3. Comprehensive Savings Analytics

#### Get Mother's Comprehensive Analytics
```http
GET /mothers/{mother_id}/savings-analytics?month={month}
```

**Parameters:**
- `mother_id` (required): Unique identifier of the mother
- `month` (optional): Specific month (YYYY-MM) for monthly analytics

**Response:**
```json
{
    "mother_id": "MOTHER123",
    "mother_name": "Jane Doe",
    "month_key": "2024-03",
    "total_saved": 15000.0,
    "total_expected": 24000.0,
    "savings_ratio": 0.625,
    "compliance_score": "18/24",
    "saving_streak": {
        "current_streak": 3,
        "longest_streak": 5,
        "total_months_saved": 8,
        "streak_details": [...]
    },
    "credit_score": {
        "credit_score": 745,
        "credit_rating": "Good",
        "factors": {...},
        "breakdown": {...}
    },
    "transaction_summary": {
        "total_transactions": 12,
        "total_amount": 15000.0,
        "payment_methods": {...},
        "transaction_statuses": {...}
    },
    "monthly_breakdown": [
        {
            "month_key": "2024-03",
            "savings": 2000.0,
            "milestone_score": 1,
            "donor_contribution": 500.0,
            "partner_contribution": 200.0
        }
    ]
}
```

#### Get All Mothers' Analytics
```http
GET /savings-analytics?month={month}
```

**Parameters:**
- `month` (optional): Specific month (YYYY-MM) for monthly analytics

**Response:**
```json
{
    "month_key": "2024-03",
    "total_mothers": 25,
    "total_savings_across_all": 125000.0,
    "average_savings_per_mother": 5000.0,
    "mothers_analytics": [
        {
            "mother_id": "MOTHER123",
            "mother_name": "Jane Doe",
            "total_saved": 15000.0,
            "total_expected": 24000.0,
            "savings_ratio": 0.625,
            "compliance_score": "18/24",
            "current_streak": 3,
            "longest_streak": 5,
            "credit_score": 745,
            "credit_rating": "Good"
        }
    ]
}
```

### 4. Enhanced Monthly Savings

#### Get Mother's Monthly Savings (Enhanced)
```http
GET /mothers/{mother_id}/monthly-savings
```

**Response:**
```json
{
    "mother_id": "MOTHER123",
    "total_savings": 15000.0,
    "total_expected": 24000.0,
    "savings_ratio": 0.625,
    "total_milestone_score": 8,
    "total_donor_contribution": 3000.0,
    "total_partner_contribution": 1200.0,
    "monthly_breakdown": [
        {
            "month_key": "2024-03",
            "savings": 2000.0,
            "milestone_score": 1,
            "donor_contribution": 500.0,
            "partner_contribution": 200.0,
            "expected_savings": 2000.0,
            "met_target": true
        }
    ]
}
```

## Analytics Calculation Logic

### Saving Streak Calculation
1. **Consecutive Months**: Months with savings > 0 that follow each other sequentially
2. **Current Streak**: Number of consecutive months from the most recent month
3. **Longest Streak**: Best consecutive streak achieved historically
4. **Streak Breaking**: Any month with 0 savings breaks the current streak

### Credit Score Calculation
1. **Base Score**: 300 (minimum)
2. **Savings Consistency (40%)**: 
   - 100% of expected: 170 points
   - 80% of expected: 136 points
   - 60% of expected: 102 points
   - 40% of expected: 68 points
   - 20% of expected: 34 points
3. **Payment History (30%)**: Based on transaction completion rates
4. **Milestone Achievement (20%)**: Based on meeting monthly savings targets
5. **Compliance Score (10%)**: Based on overall compliance (out of 24)

### Expected Savings Calculation
- **Formula**: Number of children × 1000
- **Examples**:
  - 1 child: 1000 per month
  - 2 children: 2000 per month
  - 3 children: 3000 per month

## Usage Examples

### 1. Track Mother's Progress
```bash
# Get comprehensive analytics for a mother
curl "http://localhost:8000/mothers/MOTHER123/savings-analytics"

# Get just the saving streak
curl "http://localhost:8000/mothers/MOTHER123/saving-streak"

# Get credit score for specific month
curl "http://localhost:8000/mothers/MOTHER123/credit-score?month=2024-03"
```

### 2. Monitor All Mothers
```bash
# Get analytics for all mothers
curl "http://localhost:8000/savings-analytics"

# Get analytics for specific month
curl "http://localhost:8000/savings-analytics?month=2024-03"
```

### 3. Enhanced Monthly Savings
```bash
# Get detailed monthly breakdown
curl "http://localhost:8000/mothers/MOTHER123/monthly-savings"
```

## Benefits

### 1. **Performance Tracking**
- Monitor savings progress over time
- Track milestone achievements
- Identify saving patterns and trends

### 2. **Motivation & Engagement**
- Saving streaks encourage consistency
- Credit scores provide financial health indicators
- Progress visualization drives engagement

### 3. **Financial Planning**
- Compare actual vs expected savings
- Identify areas for improvement
- Track compliance with savings goals

### 4. **Reporting & Analytics**
- Comprehensive mother-level analytics
- System-wide savings overview
- Data-driven decision making

## Error Handling

All endpoints return appropriate HTTP status codes:
- **200**: Success
- **400**: Bad request (invalid parameters)
- **404**: Mother not found
- **500**: Internal server error

## Performance Considerations

- Analytics are calculated on-demand
- Consider caching for frequently accessed data
- Large datasets may require pagination
- Database indexes optimize query performance

## Future Enhancements

### 1. **Caching Layer**
- Cache analytics results for improved performance
- Implement cache invalidation on data updates

### 2. **Real-time Updates**
- WebSocket connections for live analytics
- Push notifications for milestone achievements

### 3. **Advanced Analytics**
- Predictive savings modeling
- Seasonal trend analysis
- Comparative analytics across demographics

### 4. **Export & Reporting**
- PDF report generation
- Excel/CSV export functionality
- Scheduled report delivery

## Conclusion

The new savings analytics API provides comprehensive insights into mothers' financial behavior, enabling better tracking, motivation, and decision-making. The credit score system offers a standardized way to assess financial health, while saving streaks encourage consistent behavior. These analytics form the foundation for data-driven financial empowerment programs.
