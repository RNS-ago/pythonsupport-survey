-- Who may do what in the pis_survey database: the schemas, the group roles and their rights.
-- See "Database logins" in docs/data-analysis.md.
--
-- Edit this file to change the rights, commit, and deploy: setup.sh and every
-- `manage.sh update` apply it (after migrations, so new Django tables are covered).
-- It runs as the postgres superuser, in one transaction, and is safe to run again.
--
-- The reset section takes away every right listed below before granting them again, so
-- deleting a GRANT here takes that right away. A new schema needs a line in the reset too.
--
-- :"analyst", :"viewer" and :"app_user" are psql variables: apply_db_permissions
-- (deploy/lib/postgres.sh) sets them from ANALYST_ROLE (pis_analyst), VIEWER_ROLE (pis_viewer)
-- and APP_USER (pis) in deploy/settings.env. To run this file by hand, pass them too:
-- psql -v analyst=pis_analyst -v viewer=pis_viewer -v app_user=pis ...

SET client_min_messages = warning;  -- no notices for rights that are already there

-- Group roles. Nobody logs in as them; people get them through membership:
-- members of the pythonsupport group become pis_analyst (manage.sh users), and viewers are
-- added by hand (see docs/data-analysis.md).
SELECT format('CREATE ROLE %I NOLOGIN', r) FROM unnest(ARRAY[:'analyst', :'viewer']) AS r
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
\gexec

-- Analysts' sessions switch to pis_analyst, so pis_analyst owns the tables they create.
-- The app (pis) is a member of pis_analyst, so its backups and restores cover those tables.
GRANT :"analyst" TO :"app_user";

-- The analysts' schemas. Django's own tables stay in public.
-- pis_analyst owns them, which gives it full rights there (read, write, create, drop), and
-- lets pg_restore put the analysts' tables back (it sets their owner before their rights).
CREATE SCHEMA IF NOT EXISTS processed_data;  -- results of the processing notebooks
CREATE SCHEMA IF NOT EXISTS static_data;     -- data from outside Django, e.g. the old survey
CREATE SCHEMA IF NOT EXISTS published_data;  -- what viewers may see
ALTER SCHEMA processed_data OWNER TO :"analyst";
ALTER SCHEMA static_data    OWNER TO :"analyst";
ALTER SCHEMA published_data OWNER TO :"analyst";

-- Reset ----------------------------------------------------------------------------------
-- In public both roles start from nothing. In the three schemas above only pis_viewer does:
-- pis_analyst owns them and its tables there, and an owner's rights can't be taken away.
REVOKE ALL ON SCHEMA public FROM :"analyst", :"viewer";
REVOKE ALL ON SCHEMA processed_data, static_data, published_data FROM :"viewer";
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM :"analyst", :"viewer";
REVOKE ALL ON ALL TABLES IN SCHEMA processed_data, static_data, published_data FROM :"viewer";
ALTER DEFAULT PRIVILEGES FOR ROLE :"analyst" IN SCHEMA published_data REVOKE ALL ON TABLES FROM :"viewer";

-- pis_analyst ----------------------------------------------------------------------------
-- Read and write in processed_data, static_data and published_data: it owns the schemas and the
-- tables the analysts create; this covers tables someone else created there.
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
  ON ALL TABLES IN SCHEMA processed_data, static_data, published_data TO :"analyst";

-- Read only, and only Django's survey tables (survey_*), not users or sessions.
GRANT USAGE ON SCHEMA public TO :"analyst";
SELECT format('GRANT SELECT ON public.%I TO %I', tablename, :'analyst') FROM pg_tables
 WHERE schemaname = 'public' AND tablename LIKE 'survey\_%'
\gexec

-- pis_viewer -----------------------------------------------------------------------------
-- Read only, published_data only; also tables the analysts create there later.
GRANT USAGE ON SCHEMA published_data TO :"viewer";
GRANT SELECT ON ALL TABLES IN SCHEMA published_data TO :"viewer";
ALTER DEFAULT PRIVILEGES FOR ROLE :"analyst" IN SCHEMA published_data GRANT SELECT ON TABLES TO :"viewer";
