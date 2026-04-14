from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/staff_track")


def create_database_if_not_exists():
    """Create the database if it doesn't exist."""
    # Parse the DATABASE_URL to extract components
    parsed = urlparse(DATABASE_URL)
    database_name = parsed.path.lstrip('/')

    # Build URL for connecting to default 'postgres' database
    postgres_url = DATABASE_URL.replace(f"/{database_name}", "/postgres")

    # Create a temporary engine to connect to postgres database
    temp_engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")

    try:
        with temp_engine.connect() as conn:
            # Check if database exists
            result = conn.execute(
                text(f"SELECT 1 FROM pg_database WHERE datname = '{database_name}'")
            )
            exists = result.fetchone()

            if not exists:
                print(f"Database '{database_name}' does not exist. Creating...")
                conn.execute(text(f'CREATE DATABASE "{database_name}"'))
                print(f"Database '{database_name}' created successfully.")
    except Exception as e:
        print(f"Error checking/creating database: {e}")
        raise
    finally:
        temp_engine.dispose()


# Ensure database exists before creating engine
create_database_if_not_exists()

# Create SQLAlchemy engine with optimized pool settings
engine = create_engine(
    DATABASE_URL,
    pool_size=20,          # Increase base pool size
    max_overflow=30,        # Increase overflow connections
    pool_timeout=30,        # Timeout for getting connection from pool
    pool_recycle=3600,      # Recycle connections every hour
    pool_pre_ping=True,     # Validate connections before use
    echo=False              # Disable SQL logging in production
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Ensure PostGIS extension exists for geography types
try:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()
except Exception:
    pass
