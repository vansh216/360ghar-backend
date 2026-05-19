-- Migration: Add is_seed_data flag to distinguish seeded vs real data.
-- Applied to users, agents, and properties tables.
-- Default is FALSE so real user-created records are not marked as seed data.

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_seed_data BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_seed_data BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS is_seed_data BOOLEAN NOT NULL DEFAULT FALSE;
