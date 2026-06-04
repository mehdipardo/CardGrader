-- CardGrader — Supabase schema
-- Run this in the Supabase SQL Editor (https://supabase.com/dashboard → SQL Editor → New query).
-- Requires auth.users to be populated by Supabase Auth.

-- ── Extensions ─────────────────────────────────────────────────────────────
create extension if not exists "uuid-ossp";

-- ── profiles ───────────────────────────────────────────────────────────────
create table if not exists profiles (
    id          uuid primary key references auth.users (id) on delete cascade,
    username    text unique,
    created_at  timestamptz not null default now()
);

alter table profiles enable row level security;

create policy "Users can view own profile"
    on profiles for select
    using (auth.uid() = id);

create policy "Users can insert own profile"
    on profiles for insert
    with check (auth.uid() = id);

create policy "Users can update own profile"
    on profiles for update
    using (auth.uid() = id);

-- ── scans ──────────────────────────────────────────────────────────────────
create table if not exists scans (
    id                  uuid primary key default uuid_generate_v4(),
    user_id             uuid not null references profiles (id) on delete cascade,

    -- Image storage URLs (Supabase Storage)
    front_image_url     text,
    back_image_url      text,

    -- Card identity
    card_name           text not null,
    card_number         text not null,
    card_language       text not null,
    set_name            text,
    set_code            text,
    rarity              text,

    -- Grading scores
    centering           numeric(4, 1),
    corners             numeric(4, 1),
    edges               numeric(4, 1),
    surface             numeric(4, 1),
    overall_score       numeric(4, 1) not null,
    grading_confidence  numeric(4, 3),

    -- Pricing
    raw_price           numeric(10, 2),
    currency            text default 'EUR',
    estimated_value     numeric(10, 2),
    value_range_low     numeric(10, 2),
    value_range_high    numeric(10, 2),
    confidence_score    numeric(4, 3),
    pricing_source      text,
    language_specific   boolean default false,

    -- Metadata
    scanned_at          timestamptz not null default now()
);

alter table scans enable row level security;

create policy "Users can view own scans"
    on scans for select
    using (auth.uid() = user_id);

create policy "Users can insert own scans"
    on scans for insert
    with check (auth.uid() = user_id);

create policy "Users can delete own scans"
    on scans for delete
    using (auth.uid() = user_id);

create index if not exists idx_scans_user on scans (user_id);

-- ── collection ─────────────────────────────────────────────────────────────
create table if not exists collection (
    id          uuid primary key default uuid_generate_v4(),
    user_id     uuid not null references profiles (id) on delete cascade,
    scan_id     uuid not null references scans (id) on delete cascade,
    added_at    timestamptz not null default now(),
    notes       text,

    constraint collection_user_scan_unique unique (user_id, scan_id)
);

alter table collection enable row level security;

create policy "Users can view own collection"
    on collection for select
    using (auth.uid() = user_id);

create policy "Users can add to own collection"
    on collection for insert
    with check (auth.uid() = user_id);

create policy "Users can remove from own collection"
    on collection for delete
    using (auth.uid() = user_id);

create index if not exists idx_collection_user on collection (user_id);

-- ── listings ───────────────────────────────────────────────────────────────
create table if not exists listings (
    id               uuid primary key default uuid_generate_v4(),
    scan_id          uuid not null references scans (id) on delete cascade,
    user_id          uuid not null references profiles (id) on delete cascade,
    platform         text not null,
    title            text not null,
    description      text not null,
    suggested_price  numeric(10, 2) not null,
    tags             text[],
    redirect_url     text,
    created_at       timestamptz not null default now()
);

alter table listings enable row level security;

create policy "Users can view own listings"
    on listings for select
    using (auth.uid() = user_id);

create policy "Users can create own listings"
    on listings for insert
    with check (auth.uid() = user_id);

create policy "Users can delete own listings"
    on listings for delete
    using (auth.uid() = user_id);

create index if not exists idx_listings_scan on listings (scan_id);

-- ── collection_dashboard view ───────────────────────────────────────────────
create or replace view collection_dashboard as
select
    c.user_id,
    count(*)                        as total_cards,
    sum(s.estimated_value)          as total_estimated_value,
    avg(s.overall_score)            as avg_condition_score,
    max(s.scanned_at)               as last_scan_at
from collection c
join scans s on s.id = c.scan_id
group by c.user_id;
