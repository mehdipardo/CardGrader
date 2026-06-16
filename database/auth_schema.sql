-- CardGrader custom auth schema
-- Run this in the Supabase SQL Editor BEFORE using the auth endpoints.
-- This uses a custom users table (not Supabase Auth) + service-role key.

-- ── Extensions ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── users ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pseudo        text UNIQUE NOT NULL,
  email         text UNIQUE NOT NULL,
  password_hash text NOT NULL,
  created_at    timestamptz DEFAULT now()
);

-- ── collection ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.collection (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  report     jsonb NOT NULL,
  added_at   timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_collection_user_id ON public.collection(user_id);
