-- Sync PostgreSQL enums and constraints with SQLAlchemy models.
--
-- Fixes:
--   1. property_type enum missing 'villa', 'plot', 'condo', 'penthouse',
--      'studio', 'loft', 'pg', 'flatmate', 'office', 'shop', 'warehouse'
--   2. image_category enum missing 'floor_plan'
--   3. bank_auctions unique constraint name mismatch (ORM expects 'uq_bank_auctions_key')
--   4. bank_rates unique constraint name mismatch (ORM expects 'uq_bank_rates_key')

-- =========================================================================
-- 1. property_type: add all values that exist in Python but may be missing in DB
-- =========================================================================
ALTER TYPE property_type ADD VALUE IF NOT EXISTS 'villa';
ALTER TYPE property_type ADD VALUE IF NOT EXISTS 'plot';
ALTER TYPE property_type ADD VALUE IF NOT EXISTS 'condo';
ALTER TYPE property_type ADD VALUE IF NOT EXISTS 'penthouse';
ALTER TYPE property_type ADD VALUE IF NOT EXISTS 'studio';
ALTER TYPE property_type ADD VALUE IF NOT EXISTS 'loft';
ALTER TYPE property_type ADD VALUE IF NOT EXISTS 'pg';
ALTER TYPE property_type ADD VALUE IF NOT EXISTS 'flatmate';
ALTER TYPE property_type ADD VALUE IF NOT EXISTS 'office';
ALTER TYPE property_type ADD VALUE IF NOT EXISTS 'shop';
ALTER TYPE property_type ADD VALUE IF NOT EXISTS 'warehouse';

-- =========================================================================
-- 2. image_category: add 'floor_plan' (Python enum has it, DB does not)
-- =========================================================================
ALTER TYPE image_category ADD VALUE IF NOT EXISTS 'floor_plan';

-- =========================================================================
-- 3. bank_auctions: rename auto-generated unique constraint to match ORM
-- =========================================================================
DO $$ DECLARE _name TEXT;
BEGIN
    SELECT con.conname INTO _name
      FROM pg_constraint con
      JOIN pg_class rel ON rel.oid = con.conrelid
     WHERE rel.relname = 'bank_auctions'
       AND con.contype = 'u'
       AND con.conname != 'uq_bank_auctions_key'
     LIMIT 1;

    IF _name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE bank_auctions RENAME CONSTRAINT %I TO uq_bank_auctions_key',
            _name
        );
    END IF;
END $$;

-- =========================================================================
-- 4. bank_rates: rename auto-generated unique constraint to match ORM
-- =========================================================================
DO $$ DECLARE _name TEXT;
BEGIN
    SELECT con.conname INTO _name
      FROM pg_constraint con
      JOIN pg_class rel ON rel.oid = con.conrelid
     WHERE rel.relname = 'bank_rates'
       AND con.contype = 'u'
       AND con.conname != 'uq_bank_rates_key'
     LIMIT 1;

    IF _name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE bank_rates RENAME CONSTRAINT %I TO uq_bank_rates_key',
            _name
        );
    END IF;
END $$;
