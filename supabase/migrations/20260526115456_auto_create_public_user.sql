-- Trigger: auto-create public.users row when a new auth user is created.
-- Runs for every provider (email, GitHub, magic link, etc.).
-- Idempotent: ON CONFLICT DO NOTHING.

CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.users (id, email)
    VALUES (NEW.id, NEW.email)
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created_public ON auth.users;

CREATE TRIGGER on_auth_user_created_public
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_auth_user();

-- Extend tier check constraint to include 'admin'
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_tier_check;
ALTER TABLE public.users ADD CONSTRAINT users_tier_check
    CHECK (tier IN ('free', 'beta', 'starter', 'pro', 'admin'));

-- Seed: ensure founder account is admin
INSERT INTO public.users (id, email, tier)
VALUES ('1bb25362-e675-4409-87db-b1201318dbaf', 'anghel.contiu@gmail.com', 'admin')
ON CONFLICT (id) DO UPDATE SET tier = 'admin';
