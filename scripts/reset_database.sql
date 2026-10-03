/* ============================================================
   FILE:      scripts/reset_database.sql
   PURPOSE:   Drop the database for a clean rebuild (warehouse is kept)
   RUN AFTER: any
   RERUN:     SAFE but DESTRUCTIVE
   ============================================================ */

USE ROLE ACCOUNTADMIN;

-- WARNING: permanently deletes all objects and data in SUPPLY_TRUST_DB.
DROP DATABASE IF EXISTS SUPPLY_TRUST_DB;

-- Next: rebuild by running the files in the order listed in README.md
