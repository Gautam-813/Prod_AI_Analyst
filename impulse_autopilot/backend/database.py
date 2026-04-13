"""
Database Configuration & Setup
SQLite database with SQLAlchemy ORM
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get the backend directory path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BACKEND_DIR, "..", "data")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Database URL - use absolute path for SQLite
DB_FILE = os.path.join(DATA_DIR, "autopilot.db")
DATABASE_URL = f"sqlite:///{DB_FILE}"

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set True for SQL debugging
    connect_args={"check_same_thread": False}  # SQLite specific
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency to get DB session
def get_db():
    """FastAPI dependency to provide database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database - creates all tables"""
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized")
