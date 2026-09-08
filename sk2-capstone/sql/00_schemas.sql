-- MedInsure warehouse scaffolding
-- Database: medinsure (create separately if needed: CREATE DATABASE medinsure;)
-- Run: psql -h localhost -p 5432 -U postgres -d medinsure -f sql/00_schemas.sql

CREATE SCHEMA IF NOT EXISTS dw;       -- dimensional warehouse (dims + facts)
CREATE SCHEMA IF NOT EXISTS staging;  -- optional landing / clean staging
CREATE SCHEMA IF NOT EXISTS etl;      -- control, audit, dead letter

COMMENT ON SCHEMA dw IS 'MedInsure analytics star schema (dimensions and facts)';
COMMENT ON SCHEMA staging IS 'Staging area for validating loads before warehouse insert';
COMMENT ON SCHEMA etl IS 'ETL control tables: high-water marks, run audit, dead letter';
