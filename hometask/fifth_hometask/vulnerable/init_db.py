#!/usr/bin/env python3
"""Initialize SQLite database with sample data for the vulnerable demo agent."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "demo.db"

def init_db():
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            company TEXT
        );

        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            client_id INTEGER,
            product TEXT,
            amount REAL,
            status TEXT,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );

        CREATE TABLE secrets (
            id INTEGER PRIMARY KEY,
            key_name TEXT UNIQUE,
            value TEXT
        );

        INSERT INTO clients (name, email, company) VALUES
            ('Alice Ivanova', 'alice@example.com', 'TechCorp'),
            ('Bob Petrov', 'bob@example.com', 'DataSoft'),
            ('Carol Smirnova', 'carol@example.com', 'CloudNine');

        INSERT INTO orders (client_id, product, amount, status) VALUES
            (1, 'API Testing Suite', 1200.00, 'paid'),
            (1, 'Load Testing Package', 800.00, 'pending'),
            (2, 'Security Audit', 2500.00, 'paid'),
            (3, 'CI/CD Consulting', 1800.00, 'paid');

        INSERT INTO secrets (key_name, value) VALUES
            ('ADMIN_PASSWORD', 'SuperSecretAdmin123!'),
            ('API_KEY', 'sk-demo-vulnerable-key-do-not-use'),
            ('DB_CONNECTION', 'postgresql://admin:pass@internal-db:5432/prod');
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")

if __name__ == "__main__":
    init_db()
