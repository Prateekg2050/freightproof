/* ============================================================
   FILE:      sql/00_setup/01_database_schemas.sql
   PURPOSE:   Role, warehouse, database and schemas
   RUN AFTER: none
   RERUN:     SAFE
   ============================================================ */

USE ROLE ACCOUNTADMIN;

CREATE WAREHOUSE IF NOT EXISTS SUPPLY_TRUST_WH
    WAREHOUSE_TYPE = STANDARD
    WAREHOUSE_SIZE = XSMALL
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    STATEMENT_TIMEOUT_IN_SECONDS = 300
    COMMENT = 'X-Small warehouse for Supply Chain Trust Layer MVP';

USE WAREHOUSE SUPPLY_TRUST_WH;

CREATE DATABASE IF NOT EXISTS SUPPLY_TRUST_DB
    COMMENT = 'Governed supply-chain trust and evidence platform';

USE DATABASE SUPPLY_TRUST_DB;

CREATE SCHEMA IF NOT EXISTS RAW
    COMMENT = 'Immutable data received from source systems';

CREATE SCHEMA IF NOT EXISTS CORE
    COMMENT = 'Canonical supply-chain business entities';

CREATE SCHEMA IF NOT EXISTS TRUST
    COMMENT = 'Trust contracts, evaluations and evidence';

CREATE SCHEMA IF NOT EXISTS SEMANTIC
    COMMENT = 'Governed views and semantic-layer objects';

CREATE SCHEMA IF NOT EXISTS APP
    COMMENT = 'Application-facing views and procedures';
