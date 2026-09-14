-- Generated SQL from Alembic migrations for PrimeData
-- This represents the full database schema setup

-- ============================================================================
-- UPGRADE (alembic upgrade head)
-- ============================================================================

-- Create data_sources table
CREATE TABLE IF NOT EXISTS data_sources (
    id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100) NOT NULL,
    config TEXT,
    is_active BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_data_sources_id ON data_sources (id);

-- Create pipelines table
CREATE TABLE IF NOT EXISTS pipelines (
    id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    config TEXT,
    is_active BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_pipelines_id ON pipelines (id);

-- Create users table with all required fields
CREATE TABLE IF NOT EXISTS users (
    id UUID NOT NULL,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    timezone VARCHAR(50),
    picture_url VARCHAR(500),
    auth_provider VARCHAR(10) NOT NULL DEFAULT 'none',
    google_sub VARCHAR(255),
    roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN,
    password_hash VARCHAR(255),
    email_verified BOOLEAN NOT NULL DEFAULT false,
    verification_token VARCHAR(255),
    verification_token_expires TIMESTAMP WITH TIME ZONE,
    password_reset_token VARCHAR(255),
    password_reset_token_expires TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_verification_token ON users (verification_token);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_password_reset_token ON users (password_reset_token);
CREATE INDEX IF NOT EXISTS ix_users_id ON users (id);

-- Create workspaces table
CREATE TABLE IF NOT EXISTS workspaces (
    id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    settings JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_workspaces_id ON workspaces (id);

-- Create workspace_members table (junction table)
CREATE TABLE IF NOT EXISTS workspace_members (
    id UUID NOT NULL,
    workspace_id UUID NOT NULL,
    user_id UUID NOT NULL,
    role VARCHAR(10) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT fk_workspace_members_user_id FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_workspace_members_workspace_id FOREIGN KEY (workspace_id) REFERENCES workspaces (id),
    CONSTRAINT unique_workspace_user UNIQUE (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_workspace_members_id ON workspace_members (id);

-- ============================================================================
-- CREATE ENUM TYPES (if not using check constraints)
-- ============================================================================

-- For auth_provider enum
CREATE TYPE authprovider AS ENUM ('GOOGLE', 'SIMPLE', 'NONE');
ALTER TABLE users ALTER COLUMN auth_provider TYPE authprovider USING auth_provider::authprovider;

-- For workspace role enum
CREATE TYPE workspacerole AS ENUM ('OWNER', 'ADMIN', 'EDITOR', 'VIEWER');
ALTER TABLE workspace_members ALTER COLUMN role TYPE workspacerole USING role::workspacerole;


-- ============================================================================
-- DOWNGRADE (alembic downgrade -1)
-- ============================================================================
-- Run these to tear down the schema

-- DROP TABLE workspace_members;
-- DROP TABLE workspaces;
-- DROP TABLE users;
-- DROP TABLE pipelines;
-- DROP TABLE data_sources;
-- DROP TYPE workspacerole;
-- DROP TYPE authprovider;
