-- Rotation review fixes (docs/phase1/ROTATION.md §14).
--
-- One source of truth for after-use rotation: rotate_after_checkin is merged into
-- rotate_after_use (a TRUE in either stays TRUE), then dropped.

UPDATE inventory.accounts SET rotate_after_use = TRUE
    WHERE rotate_after_checkin AND NOT rotate_after_use;
ALTER TABLE inventory.accounts DROP COLUMN IF EXISTS rotate_after_checkin;
