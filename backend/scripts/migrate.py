"""One-off schema migration runner.

Run on deploy (not per request):  python -m scripts.migrate
Creates tables and applies the lightweight schema repairs in app.database.
"""
from app.database import create_tables

if __name__ == "__main__":
    create_tables()
    print("✅ tables created / schema updated")
