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
        error_msg = str(e)
        if "permission denied" in error_msg.lower() or "insufficientprivilege" in error_msg.lower():
            print(f"Warning: Cannot create database '{database_name}' - user lacks CREATEDB permission.")
            print(f"Please create the database manually or grant CREATEDB permission to the user.")
            print(f"Run: CREATE DATABASE \"{database_name}\"; as a superuser, or: ALTER USER your_user CREATEDB;")
        else:
            print(f"Error checking/creating database: {e}")
            raise
    finally:
        temp_engine.dispose()


def create_extensions():
    """Create required PostgreSQL extensions (PostGIS, uuid-ossp)."""
    try:
        with engine.connect() as conn:
            # Create PostGIS extension for geography types
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            # Create uuid-ossp extension for UUID generation
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
            conn.commit()
            print("PostgreSQL extensions (postgis, uuid-ossp) created/verified successfully.")
    except Exception as e:
        error_msg = str(e)
        if "could not open extension control file" in error_msg.lower():
            print("Error: PostGIS extension is not installed on the PostgreSQL server.")
            print("Please install PostGIS on your PostgreSQL server first.")
            print("On Ubuntu/Debian: sudo apt-get install postgresql-<version>-postgis-3")
            print("On macOS with Homebrew: brew install postgis")
            raise
        elif "permission denied" in error_msg.lower():
            print("Warning: Cannot create extensions - user lacks permission.")
            print("Please run as superuser: CREATE EXTENSION postgis; CREATE EXTENSION \"uuid-ossp\";")
            raise
        else:
            print(f"Error creating extensions: {e}")
            raise


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

# Create required extensions before tables
create_extensions()

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


def seed_default_admin():
    """Create default System Admin user if no users exist."""
    from models.db_models import User, Role, Department, Designation, Grade
    import bcrypt
    from datetime import datetime

    db = SessionLocal()
    try:
        # Check if any users exist
        existing_users = db.query(User).first()
        if existing_users:
            return  # Database already has users

        print("No users found. Creating default System Admin account...")

        # Create default Grade
        default_grade = db.query(Grade).filter(Grade.name == "Default").first()
        if not default_grade:
            default_grade = Grade(
                name="Default",
                annual_leave_days=21,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(default_grade)
            db.commit()
            db.refresh(default_grade)

        # Create System Admin role
        admin_role = db.query(Role).filter(Role.name == "System Admin").first()
        if not admin_role:
            admin_role = Role(
                name="System Admin",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(admin_role)
            db.commit()
            db.refresh(admin_role)

        # Create Administration department
        admin_dept = db.query(Department).filter(Department.name == "Administration").first()
        if not admin_dept:
            admin_dept = Department(
                name="Administration",
                description="Hospital Administration",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(admin_dept)
            db.commit()
            db.refresh(admin_dept)

        # Create System Administrator designation
        admin_designation = db.query(Designation).filter(Designation.name == "System Administrator").first()
        if not admin_designation:
            admin_designation = Designation(
                name="System Administrator",
                description="System Administrator",
                department_id=admin_dept.department_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(admin_designation)
            db.commit()
            db.refresh(admin_designation)

        # Hash default password
        default_password = "Admin@123"
        hashed_password = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Create System Admin user
        admin_user = User(
            employee_number="SYS001",
            first_name="System",
            surname="Admin",
            email="admin@stafftrack.com",
            password_hash=hashed_password,
            role_id=admin_role.role_id,
            department_id=admin_dept.department_id,
            designation_id=admin_designation.designation_id,
            grade_id=default_grade.grade_id,
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print("=" * 60)
        print("DEFAULT SYSTEM ADMIN ACCOUNT CREATED")
        print("=" * 60)
        print(f"Email: {admin_user.email}")
        print(f"Password: {default_password}")
        print("IMPORTANT: Please change this password after first login!")
        print("=" * 60)

    except Exception as e:
        print(f"Error creating default admin: {e}")
        db.rollback()
    finally:
        db.close()