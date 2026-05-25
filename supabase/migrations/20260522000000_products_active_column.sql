-- Add active flag to products; default true so all existing rows become active.
ALTER TABLE products
    ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT true;
