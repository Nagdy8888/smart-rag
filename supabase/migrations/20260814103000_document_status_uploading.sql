-- Phase 3 gap close-out Run 3: public Uploading lifecycle value (expand-only).
-- Must live in its own migration: PostgreSQL forbids using a newly added enum
-- value in the same transaction that adds it.

ALTER TYPE app.document_status ADD VALUE IF NOT EXISTS 'uploading' BEFORE 'uploaded';
