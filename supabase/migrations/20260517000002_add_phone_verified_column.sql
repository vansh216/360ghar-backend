-- Add phone_verified column to track phone verification separately from email verification (is_verified)
ALTER TABLE users ADD COLUMN phone_verified BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill: existing users with phone who are verified get phone_verified = true
UPDATE users SET phone_verified = TRUE WHERE phone IS NOT NULL AND is_verified = TRUE;
