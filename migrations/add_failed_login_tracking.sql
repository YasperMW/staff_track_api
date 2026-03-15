-- Migration: Add failed login tracking columns
-- Date: 2026-03-15
-- Description: Add columns to track failed login attempts and account lockout

-- Add failed login tracking columns to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP WITH TIME ZONE;

-- Create index for faster queries on locked_until
CREATE INDEX IF NOT EXISTS idx_users_locked_until ON users(locked_until) WHERE locked_until IS NOT NULL;

-- Create index for failed_login_attempts
CREATE INDEX IF NOT EXISTS idx_users_failed_login_attempts ON users(failed_login_attempts) WHERE failed_login_attempts > 0;

-- Verify the columns were added
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'users'
AND column_name IN ('failed_login_attempts', 'locked_until');