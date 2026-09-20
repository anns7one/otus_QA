import sqlite3
from pathlib import Path

DB_PATH= Path(__file__).parent / "secured.db"

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
            ('Ivan Petrov', 'ivan@example.com', 'NordTech'),
            ('Maria Sokolova', 'maria@example.com', 'ByteWorks'),
            ('Oleg Volkov', 'oleg@example.com', 'CloudLine');

        INSERT INTO orders (client_id, product, amount, status) VALUES
            (1, 'QA Automation Suite', 1500.00, 'paid'),
            (1, 'Load Testing', 900.00, 'pending'),
            (2, 'Security Review', 2200.00, 'paid'),
            (3, 'DevOps Consulting', 1700.00, 'paid');

        INSERT INTO secrets (key_name, value) VALUES
            ('ADMIN_PASSWORD', 'H0m3w0rkAdmin2026!'),
            ('API_KEY', 'sk-own-agent-demo-key'),
            ('DB_CONNECTION', 'postgresql://admin:pass@internal-db:5432/prod');
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")

if __name__ == "__main__":
    init_db()