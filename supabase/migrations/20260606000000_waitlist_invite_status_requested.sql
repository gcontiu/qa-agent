-- Add 'requested' to invite_status check constraint.
-- 'requested' is set when a user clicks the CTA in the mini-scan results email
-- (beta claim flow) — before the founder manually approves and sends the invite.
ALTER TABLE growth.waitlist DROP CONSTRAINT waitlist_invite_status_check;
ALTER TABLE growth.waitlist ADD CONSTRAINT waitlist_invite_status_check
  CHECK (invite_status IN ('none', 'requested', 'sent', 'accepted'));
