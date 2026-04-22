-- ============================================================
-- PostgreSQL Init Script
-- Runs once on first container start (before Alembic migrations)
-- Creates the database if it doesn't exist and enables extensions
-- ============================================================

-- Enable UUID generation extension (used for event_id and user_id PKs)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enable pg_trgm for fast LIKE/ILIKE searches on intersection names
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable btree_gist for exclusion constraints (future: prevent overlapping preemptions)
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ── Application role (least privilege) ──────────────────────
-- The migrations run as ss_admin (superuser in dev)
-- In production, use a limited role:
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ss_app') THEN
    CREATE ROLE ss_app LOGIN PASSWORD 'app_changeme';
  END IF;
END
$$;

-- Grant will be executed after Alembic creates the tables:
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ss_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ss_app;

-- ── Set timezone ─────────────────────────────────────────────
SET timezone = 'UTC';

-- ── Log startup ──────────────────────────────────────────────
DO $$
BEGIN
  RAISE NOTICE '✅ PostgreSQL init complete — extensions enabled, roles created';
END
$$;
