-- Creating the database
CREATE DATABASE cariyadb;

-- Connect to the database
\c cariyadb;

-- Creating the partners table to store partner information
CREATE TABLE partners (
    partner_id VARCHAR(50) PRIMARY KEY,
    partner_name VARCHAR(100) NOT NULL,
    description TEXT,
    location VARCHAR(100) NOT NULL,
    total_members INTEGER NOT NULL DEFAULT 0 CHECK (total_members >= 0),
    tel_number VARCHAR(13) CHECK (tel_number ~ '^\+256[0-9]{9,10}$'),
    email VARCHAR(255) CHECK (email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_partner_name UNIQUE (partner_name),
    CONSTRAINT unique_email UNIQUE (email)
);

-- Creating the partner_subscriptions table to track partner subscriptions
CREATE TABLE partner_subscriptions (
    subscription_id VARCHAR(50) PRIMARY KEY,
    partner_id VARCHAR(50) NOT NULL REFERENCES partners(partner_id) ON DELETE CASCADE,
    subscription_tier VARCHAR(20) NOT NULL DEFAULT 'Basic' CHECK (subscription_tier IN ('Basic', 'Gold', 'Platinum')),
    subscription_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (subscription_status IN ('active', 'inactive', 'pending', 'expired')),
    start_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_date TIMESTAMP,
    payment_details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_partner_subscription UNIQUE (partner_id)
);

-- Creating the partner_contributions table to track match funding contributions
CREATE TABLE partner_contributions (
    id SERIAL PRIMARY KEY,
    partner_id VARCHAR(50) NOT NULL REFERENCES partners(partner_id) ON DELETE CASCADE,
    mother_id VARCHAR(50) NOT NULL REFERENCES mothers(generated_id) ON DELETE CASCADE,
    month_key CHAR(7) NOT NULL CHECK (month_key ~ '^[0-9]{4}-[0-1][0-9]$'),
    amount DECIMAL(15, 2) NOT NULL DEFAULT 0.0 CHECK (amount >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_partner_mother_month UNIQUE (partner_id, mother_id, month_key)
);


-- Creating the donors table to store donor information
CREATE TABLE donors (
    donor_id VARCHAR(50) PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    surname VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL CHECK (email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    country_of_residence VARCHAR(100),
    preferred_activities VARCHAR(50)[],
    total_contributions DECIMAL(15, 2) NOT NULL DEFAULT 0.0 CHECK (total_contributions >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_donor_email UNIQUE (email)
);



-- Creating the mother_activities table to store activity information, owned by partners
CREATE TABLE mother_activities (
    activity_id VARCHAR(50) PRIMARY KEY,
    partner_id VARCHAR(50) NOT NULL REFERENCES partners(partner_id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    num_people INTEGER NOT NULL DEFAULT 0 CHECK (num_people >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_activity_name_per_partner UNIQUE (partner_id, name)
);

-- Creating the mothers table to store mother information
CREATE TABLE mothers (
    generated_id VARCHAR(50) PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    surname VARCHAR(100) NOT NULL,
    mobile_number VARCHAR(13) NOT NULL CHECK (mobile_number ~ '^\+256[0-9]{9,10}$'),
    num_children INTEGER NOT NULL CHECK (num_children >= 0),
    ages_of_children INTEGER[] NOT NULL CHECK (array_length(ages_of_children, 1) = num_children AND (ages_of_children IS NULL OR (SELECT bool_and(age BETWEEN 0 AND 18) FROM unnest(ages_of_children) AS age))),
    activity_points INTEGER NOT NULL DEFAULT 0 CHECK (activity_points >= 0),
    savings DECIMAL(15, 2) NOT NULL DEFAULT 0.0 CHECK (savings >= 0),
    milestone_score INTEGER NOT NULL DEFAULT 0 CHECK (milestone_score >= 0),
    compliance_score INTEGER NOT NULL DEFAULT 0 CHECK (compliance_score >= 0),
    donor_contributions DECIMAL(15, 2) NOT NULL DEFAULT 0.0 CHECK (donor_contributions >= 0),
    partner_id VARCHAR(50) REFERENCES partners(partner_id) ON DELETE SET NULL,
    donor_id VARCHAR(50) UNIQUE REFERENCES donors(donor_id) ON DELETE SET NULL, -- Nullable for unassigned mothers
    location VARCHAR(100),
    education_level VARCHAR(50),
    nin VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_mobile_number UNIQUE (mobile_number)
);

-- Creating the mother_partner_activities junction table for many-to-many relationships
CREATE TABLE mother_partner_activities (
    mother_id VARCHAR(50) NOT NULL REFERENCES mothers(generated_id) ON DELETE CASCADE,
    activity_id VARCHAR(50) NOT NULL REFERENCES mother_activities(activity_id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (mother_id, activity_id),
    CONSTRAINT unique_mother_activity UNIQUE (mother_id, activity_id)
);

-- Creating the monthly_savings table to store monthly savings and donor contributions
CREATE TABLE monthly_savings (
    id SERIAL PRIMARY KEY,
    mother_id VARCHAR(50) NOT NULL REFERENCES mothers(generated_id) ON DELETE CASCADE,
    month_key CHAR(7) NOT NULL CHECK (month_key ~ '^[0-9]{4}-[0-1][0-9]$'),
    savings DECIMAL(15, 2) NOT NULL DEFAULT 0.0 CHECK (savings >= 0),
    milestone_score INTEGER NOT NULL DEFAULT 0 CHECK (milestone_score IN (0, 1)),
    donor_contribution DECIMAL(15, 2) NOT NULL DEFAULT 0.0 CHECK (donor_contribution >= 0),
    partner_contribution DECIMAL(15, 2) NOT NULL DEFAULT 0.0 CHECK (partner_contribution >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_mother_month UNIQUE (mother_id, month_key)
);

-- Creating the savings_transactions table to track individual savings transactions
CREATE TABLE savings_transactions (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(100) NOT NULL UNIQUE,
    mother_id VARCHAR(50) NOT NULL REFERENCES mothers(generated_id) ON DELETE CASCADE,
    month_key CHAR(7) NOT NULL CHECK (month_key ~ '^[0-9]{4}-[0-1][0-9]$'),
    amount DECIMAL(15, 2) NOT NULL DEFAULT 0.0 CHECK (amount >= 0),
    phone_number VARCHAR(13) NOT NULL CHECK (phone_number ~ '^\+256[0-9]{9,10}$'),
    payment_method VARCHAR(50) NOT NULL CHECK (payment_method IN ('Mobile Money', 'Bank Transfer', 'Cash', 'Card', 'Other')),
    transaction_status VARCHAR(20) NOT NULL DEFAULT 'completed' CHECK (transaction_status IN ('pending', 'completed', 'failed', 'cancelled')),
    reference_number VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_transaction_id UNIQUE (transaction_id)
);

-- Creating the monthly_activities table to store monthly activities
CREATE TABLE monthly_activities (
    id SERIAL PRIMARY KEY,
    mother_id VARCHAR(50) NOT NULL REFERENCES mothers(generated_id) ON DELETE CASCADE,
    month_key CHAR(7) NOT NULL CHECK (month_key ~ '^[0-9]{4}-[0-1][0-9]$'),
    activity_id VARCHAR(50) NOT NULL REFERENCES mother_activities(activity_id) ON DELETE CASCADE,
    activity_points INTEGER NOT NULL DEFAULT 1 CHECK (activity_points = 1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_mother_month_activity UNIQUE (mother_id, month_key, activity_id)
);

-- Creating the donor_contributions table to track individual donor contributions
CREATE TABLE donor_contributions (
    id SERIAL PRIMARY KEY,
    donor_id VARCHAR(50) NOT NULL REFERENCES donors(donor_id) ON DELETE CASCADE,
    mother_id VARCHAR(50) NOT NULL REFERENCES mothers(generated_id) ON DELETE CASCADE,
    month_key CHAR(7) NOT NULL CHECK (month_key ~ '^[0-9]{4}-[0-1][0-9]$'),
    amount DECIMAL(15, 2) NOT NULL DEFAULT 0.0 CHECK (amount >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_donor_mother_month UNIQUE (donor_id, mother_id, month_key),
    CONSTRAINT check_donor_mother_match CHECK (
        mother_id IN (SELECT generated_id FROM mothers WHERE donor_id = donor_contributions.donor_id)
    )
);

-- Creating indexes for faster queries
CREATE INDEX idx_partners_location ON partners (location);
CREATE INDEX idx_partner_subscriptions_partner_id ON partner_subscriptions (partner_id);
CREATE INDEX idx_partner_contributions_partner_id ON partner_contributions (partner_id);
CREATE INDEX idx_partner_contributions_mother_id ON partner_contributions (mother_id);
CREATE INDEX idx_partner_contributions_month_key ON partner_contributions (month_key);
CREATE INDEX idx_donors_country ON donors (country_of_residence);
CREATE INDEX idx_mother_activities_partner_id ON mother_activities (partner_id);
CREATE INDEX idx_mothers_partner_id ON mothers (partner_id);
CREATE INDEX idx_mothers_location ON mothers (location);
CREATE INDEX idx_mothers_donor_id ON mothers (donor_id);
CREATE INDEX idx_monthly_savings_mother_id ON monthly_savings (mother_id);
CREATE INDEX idx_monthly_savings_month_key ON monthly_savings (month_key);
CREATE INDEX idx_savings_transactions_mother_id ON savings_transactions (mother_id);
CREATE INDEX idx_savings_transactions_month_key ON savings_transactions (month_key);
CREATE INDEX idx_savings_transactions_transaction_id ON savings_transactions (transaction_id);
CREATE INDEX idx_savings_transactions_phone_number ON savings_transactions (phone_number);
CREATE INDEX idx_savings_transactions_payment_method ON savings_transactions (payment_method);
CREATE INDEX idx_savings_transactions_status ON savings_transactions (transaction_status);
CREATE INDEX idx_monthly_activities_mother_id ON monthly_activities (mother_id);
CREATE INDEX idx_monthly_activities_month_key ON monthly_activities (month_key);
CREATE INDEX idx_monthly_activities_activity_id ON monthly_activities (activity_id);
CREATE INDEX idx_mother_partner_activities_mother_id ON mother_partner_activities (mother_id);
CREATE INDEX idx_mother_partner_activities_activity_id ON mother_partner_activities (activity_id);
CREATE INDEX idx_donor_contributions_donor_id ON donor_contributions (donor_id);
CREATE INDEX idx_donor_contributions_mother_id ON donor_contributions (mother_id);
CREATE INDEX idx_donor_contributions_month_key ON donor_contributions (month_key);

-- Creating a trigger function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attaching triggers to update the updated_at column
CREATE TRIGGER update_partners_timestamp
    BEFORE UPDATE ON partners
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_partner_subscriptions_timestamp
    BEFORE UPDATE ON partner_subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_partner_contributions_timestamp
    BEFORE UPDATE ON partner_contributions
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_donors_timestamp
    BEFORE UPDATE ON donors
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();


CREATE TRIGGER update_mother_activities_timestamp
    BEFORE UPDATE ON mother_activities
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_mothers_timestamp
    BEFORE UPDATE ON mothers
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_mother_partner_activities_timestamp
    BEFORE UPDATE ON mother_partner_activities
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_monthly_savings_timestamp
    BEFORE UPDATE ON monthly_savings
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_savings_transactions_timestamp
    BEFORE UPDATE ON savings_transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_monthly_activities_timestamp
    BEFORE UPDATE ON monthly_activities
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_donor_contributions_timestamp
    BEFORE UPDATE ON donor_contributions
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- =============================================================================
-- SAVING REMINDERS TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS saving_reminders (
    id SERIAL PRIMARY KEY,
    reminder_id VARCHAR(50) UNIQUE NOT NULL,
    mother_id VARCHAR(50) NOT NULL,
    reminder_date INTEGER NOT NULL CHECK (reminder_date >= 1 AND reminder_date <= 31),
    reminder_time TIME DEFAULT '09:00:00',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mother_id) REFERENCES mothers(generated_id) ON DELETE CASCADE
);

-- Index for efficient queries
CREATE INDEX idx_saving_reminders_mother_id ON saving_reminders(mother_id);
CREATE INDEX idx_saving_reminders_active ON saving_reminders(is_active);
CREATE INDEX idx_saving_reminders_date ON saving_reminders(reminder_date);

-- Trigger to update updated_at timestamp
CREATE TRIGGER update_saving_reminders_timestamp
    BEFORE UPDATE ON saving_reminders
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();