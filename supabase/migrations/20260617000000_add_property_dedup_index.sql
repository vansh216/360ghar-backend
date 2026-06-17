-- 20260617000000_add_property_dedup_index.sql
--
-- Advisory (non-unique) index on the physical-listing dedup key
-- (full_address, latitude, longitude, bedrooms). This is the exact key
-- that identified the 108 phantom hc_properties duplicates (2026-06-17
-- incident).
--
-- A UNIQUE index was originally intended but cannot be created because the
-- dataset still contains 5 pre-existing pairs of seed duplicates (kept by
-- operator choice). This non-unique index still gives a fast lookup for
-- application-level dedup checks and the integrity sweep, and surfaces
-- potential duplicates cheaply. The application layer
-- (app.services.property.crud) is responsible for rejecting exact
-- duplicates at insert time; this index makes that check O(log n).
--
-- Partial: only covers rows with all four columns populated.

CREATE INDEX IF NOT EXISTS idx_properties_phys_listing
    ON properties (full_address, latitude, longitude, bedrooms)
    WHERE full_address IS NOT NULL
      AND latitude IS NOT NULL
      AND longitude IS NOT NULL;

