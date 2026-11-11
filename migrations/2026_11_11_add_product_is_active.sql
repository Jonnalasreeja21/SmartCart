-- SmartCart migration: add product active/inactive status.
-- Run this ONCE on an existing database whose products table lacks is_active.
-- Do not run after recreating the database from the updated schema.sql.

USE smartcart_db;

ALTER TABLE products
ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1 AFTER admin_id;
