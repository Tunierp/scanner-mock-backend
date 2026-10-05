-- Création de l'utilisateur et des bases (PostgreSQL installé hors Docker).
-- Usage : sudo -u postgres psql -f scripts/create_databases.sql
CREATE ROLE scanner WITH LOGIN PASSWORD 'scanner';
CREATE DATABASE sts_navio_db OWNER scanner ENCODING 'UTF8';
CREATE DATABASE test_navio_db OWNER scanner ENCODING 'UTF8';

\c sts_navio_db
GRANT ALL ON SCHEMA public TO scanner;

\c test_navio_db
GRANT ALL ON SCHEMA public TO scanner;
