-- Step 6 — Auth identity model (D1=Option B)
--
-- Transforms the public.users stub into a mirror of auth.users (Supabase-managed).
-- Business-table FKs continue to point at public.users(id) — not at auth.users
-- directly — so migrating away from Supabase Auth only requires swapping the
-- sync trigger and JWT middleware, not touching FK constraints or business logic.
--
-- Also enables RLS on products, specs, jobs so the Postgres layer enforces
-- ownership independent of application-level filters (defense-in-depth, D3).

-- ---------------------------------------------------------------------------
-- 1. public.users — make it a mirror (IDs come from auth, not gen_random_uuid)
-- ---------------------------------------------------------------------------

-- Existing rows (if any) were created with gen_random_uuid() IDs that don't
-- match any auth.users row. Safe to truncate at migration time — no real users
-- exist yet at this stage of the project.
TRUNCATE TABLE jobs, specs, products, users CASCADE;

-- Remove the default: UUIDs will be inserted by the trigger, matching auth.users.id
ALTER TABLE users ALTER COLUMN id DROP DEFAULT;

-- ---------------------------------------------------------------------------
-- 2. Sync trigger: auth.users → public.users
-- ---------------------------------------------------------------------------

-- SECURITY DEFINER: the trigger fires as supabase_auth_admin (which owns
-- auth.users) but that role lacks INSERT on public.users. Running the function
-- as its owner (postgres / service role) grants the necessary privilege.
-- SET search_path = public: prevents search-path injection attacks.
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    INSERT INTO public.users (id, email, created_at)
    VALUES (NEW.id, NEW.email, NEW.created_at)
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();

-- ---------------------------------------------------------------------------
-- 3. Row Level Security
-- ---------------------------------------------------------------------------

-- products: owner-only access
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_products" ON products;
CREATE POLICY "users_own_products" ON products
    FOR ALL USING (user_id = auth.uid());

-- specs: access via owning product (no direct user_id on specs table)
ALTER TABLE specs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_specs" ON specs;
CREATE POLICY "users_own_specs" ON specs
    FOR ALL USING (
        product_id IN (
            SELECT id FROM products WHERE user_id = auth.uid()
        )
    );

-- jobs: owner-only access
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_jobs" ON jobs;
CREATE POLICY "users_own_jobs" ON jobs
    FOR ALL USING (user_id = auth.uid());
