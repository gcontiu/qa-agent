-- Trigger: auto-accept waitlist invite when a matching auth user is created.
-- Handles: waitlist.invite_status → 'accepted', beta_enrollments insert,
--          public.users tier → 'beta'.
-- Idempotent: ON CONFLICT DO NOTHING on beta_enrollments.

CREATE OR REPLACE FUNCTION growth.handle_new_auth_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = growth, public
AS $$
DECLARE
    wl RECORD;
BEGIN
    -- Match by email, only if an invite was sent
    SELECT * INTO wl
    FROM growth.waitlist
    WHERE email = NEW.email
      AND invite_status = 'sent'
    LIMIT 1;

    IF wl IS NOT NULL THEN
        UPDATE growth.waitlist
        SET invite_status  = 'accepted',
            invite_user_id = NEW.id::text
        WHERE id = wl.id;

        -- Grant beta tier in host users table (may not exist yet — ignore)
        UPDATE public.users
        SET tier = 'beta'
        WHERE id = NEW.id;

        INSERT INTO growth.beta_enrollments (user_id, waitlist_id, expires_at)
        VALUES (NEW.id::text, wl.id, now() + interval '30 days')
        ON CONFLICT (user_id) DO NOTHING;
    END IF;

    RETURN NEW;
END;
$$;

-- Drop trigger if it exists to allow re-running migration safely
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION growth.handle_new_auth_user();
