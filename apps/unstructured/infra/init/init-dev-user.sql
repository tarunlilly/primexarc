-- Development User Initialization Script
-- Creates test users and basic data for development

-- Create development users
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_user WHERE usename = 'dev_user') THEN
        CREATE USER dev_user WITH PASSWORD 'dev_password';
        GRANT CONNECT ON DATABASE aird TO dev_user;
        GRANT USAGE ON SCHEMA public TO dev_user;
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO dev_user;
        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO dev_user;
        RAISE NOTICE 'Created dev_user';
    END IF;
END
$$;

-- Create test user
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_user WHERE usename = 'test_user') THEN
        CREATE USER test_user WITH PASSWORD 'test_password';
        GRANT CONNECT ON DATABASE aird TO test_user;
        GRANT USAGE ON SCHEMA public TO test_user;
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO test_user;
        GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO test_user;
        RAISE NOTICE 'Created test_user';
    END IF;
END
$$;

-- Create read-only user for reporting
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_user WHERE usename = 'readonly_user') THEN
        CREATE USER readonly_user WITH PASSWORD 'readonly_password';
        GRANT CONNECT ON DATABASE aird TO readonly_user;
        GRANT USAGE ON SCHEMA public TO readonly_user;
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
        RAISE NOTICE 'Created readonly_user';
    END IF;
END
$$;

-- Alter default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO dev_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO test_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

COMMIT;
