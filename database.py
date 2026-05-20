import logging
from timezone_config import get_current_time
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

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
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database_name},
            )
            exists = result.fetchone()

            if not exists:
                logger.info("Database '%s' does not exist. Creating...", database_name)
                conn.execute(text('CREATE DATABASE "{}"'.format(database_name)))
                logger.info("Database '%s' created successfully.", database_name)
    except Exception as e:
        error_msg = str(e)
        if "permission denied" in error_msg.lower() or "insufficientprivilege" in error_msg.lower():
            logger.warning("Cannot create database '%s' - user lacks CREATEDB permission.", database_name)
            logger.warning("Create manually or grant CREATEDB permission to the user.")
        else:
            logger.error("Error checking/creating database: %s", e)
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
            logger.info("PostgreSQL extensions (postgis, uuid-ossp) created/verified successfully.")
    except Exception as e:
        error_msg = str(e)
        if "could not open extension control file" in error_msg.lower():
            logger.error("PostGIS extension is not installed on the PostgreSQL server.")
            raise
        elif "permission denied" in error_msg.lower():
            logger.warning("Cannot create extensions - user lacks permission.")
            raise
        else:
            logger.error("Error creating extensions: %s", e)
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


def seed_roles():
    """Seed all required roles if they don't exist."""
    from models.db_models import Role
    from datetime import datetime

    db = SessionLocal()
    try:
        required_roles = [
            "System Admin",
            "HR Admin",
            "Head of Department",
            "HR",
            "Accountant",
            "Principal Hospital Administrator",
            "System Administrator",
            "Staff"
        ]

        for role_name in required_roles:
            existing_role = db.query(Role).filter(Role.name == role_name).first()
            if not existing_role:
                new_role = Role(
                    name=role_name,
                    created_at=get_current_time(),
                    updated_at=get_current_time()
                )
                db.add(new_role)
                logger.info("Created role: %s", role_name)

        db.commit()
        logger.info("Role seeding completed successfully.")
    except Exception as e:
        logger.error("Error seeding roles: %s", e)
        db.rollback()
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

        logger.info("No users found. Creating default System Admin account...")

        # Create default Grade
        default_grade = db.query(Grade).filter(Grade.name == "Default").first()
        if not default_grade:
            default_grade = Grade(
                name="Default",
                annual_leave_days=21,
                created_at=get_current_time(),
                updated_at=get_current_time()
            )
            db.add(default_grade)
            db.commit()
            db.refresh(default_grade)

        # Get System Admin role (should already exist from seed_roles)
        admin_role = db.query(Role).filter(Role.name == "System Admin").first()
        if not admin_role:
            admin_role = Role(
                name="System Admin",
                created_at=get_current_time(),
                updated_at=get_current_time()
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
                created_at=get_current_time(),
                updated_at=get_current_time()
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
                created_at=get_current_time(),
                updated_at=get_current_time()
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
            created_at=get_current_time(),
            updated_at=get_current_time()
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        logger.info("DEFAULT SYSTEM ADMIN ACCOUNT CREATED")
        logger.info("Email: %s", admin_user.email)
        logger.info("Password: %s", default_password)
        logger.warning("IMPORTANT: Please change this password after first login!")

    except Exception as e:
        logger.error("Error creating default admin: %s", e)
        db.rollback()
    finally:
        db.close()


def run_database_migrations():
    """Run database migrations to add new columns if they don't exist."""
    try:
        with engine.connect() as conn:
            # Add late_reason column to attendance_logs
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'attendance_logs'
                        AND column_name = 'late_reason'
                    ) THEN
                        ALTER TABLE attendance_logs ADD COLUMN late_reason TEXT;
                        RAISE NOTICE 'Added late_reason column to attendance_logs';
                    END IF;
                END $$;
            """))

            # Add early_checkout_reason column to attendance_logs
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'attendance_logs'
                        AND column_name = 'early_checkout_reason'
                    ) THEN
                        ALTER TABLE attendance_logs ADD COLUMN early_checkout_reason TEXT;
                        RAISE NOTICE 'Added early_checkout_reason column to attendance_logs';
                    END IF;
                END $$;
            """))

            # Create shift_configurations table
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = 'shift_configurations'
                    ) THEN
                        CREATE TABLE IF NOT EXISTS public.shift_configurations (
                            shift_config_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                            shift_name VARCHAR(50) NOT NULL UNIQUE,
                            shift_type VARCHAR(20) NOT NULL CHECK (shift_type IN ('Day Shift', 'Night Shift')),
                            
                            -- Check-in time ranges
                            check_in_earliest TIME NOT NULL DEFAULT '06:00:00',
                            check_in_latest TIME NOT NULL DEFAULT '07:45:00',
                            official_start_time TIME NOT NULL DEFAULT '07:30:00',
                            
                            -- Check-out time ranges  
                            check_out_earliest TIME NOT NULL DEFAULT '16:00:00',
                            check_out_latest TIME NOT NULL DEFAULT '17:30:00',
                            official_end_time TIME NOT NULL DEFAULT '16:30:00',
                            
                            -- Extended shift threshold
                            extended_start_time TIME NOT NULL DEFAULT '17:30:00',
                            
                            -- Late check-in threshold (for requiring reasons)
                            late_threshold TIME NOT NULL DEFAULT '09:00:00',
                            
                            -- Status and metadata
                            is_active BOOLEAN NOT NULL DEFAULT true,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            created_by UUID REFERENCES public.users(user_id),
                            updated_by UUID REFERENCES public.users(user_id),
                            
                            -- Description for HR reference
                            description TEXT
                        );
                        
                        -- Create indexes
                        CREATE INDEX IF NOT EXISTS idx_shift_configurations_type ON public.shift_configurations(shift_type);
                        CREATE INDEX IF NOT EXISTS idx_shift_configurations_active ON public.shift_configurations(is_active);
                        
                        -- Add trigger for updated_at
                        CREATE TRIGGER update_shift_configurations_timestamp 
                            BEFORE UPDATE ON public.shift_configurations
                            FOR EACH ROW
                            EXECUTE FUNCTION public.update_timestamp();
                        
                        RAISE NOTICE 'Created shift_configurations table';
                    END IF;
                END $$;
            """))

            # Insert default shift configurations
            conn.execute(text("""
                INSERT INTO public.shift_configurations (
                    shift_config_id,
                    shift_name,
                    shift_type,
                    check_in_earliest,
                    check_in_latest,
                    official_start_time,
                    check_out_earliest,
                    check_out_latest,
                    official_end_time,
                    extended_start_time,
                    late_threshold,
                    is_active,
                    created_at,
                    updated_at,
                    created_by,
                    updated_by,
                    description
                ) VALUES 
                (
                    uuid_generate_v4(),
                    'Standard Day Shift',
                    'Day Shift',
                    '06:00:00',
                    '07:45:00',
                    '07:30:00',
                    '16:00:00',
                    '17:30:00',
                    '16:30:00',
                    '17:30:00',
                    '09:00:00',
                    true,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    NULL,
                    NULL,
                    'Standard day shift with flexible check-in/out times'
                ),
                (
                    uuid_generate_v4(),
                    'Standard Night Shift',
                    'Night Shift',
                    '16:30:00',
                    '23:59:59',
                    '16:30:00',
                    '06:00:00',
                    '08:00:00',
                    '07:30:00',
                    '08:00:00',
                    '18:00:00',
                    true,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    NULL,
                    NULL,
                    'Standard night shift spanning midnight'
                )
                ON CONFLICT (shift_name) DO NOTHING;
            """))

            # Add is_extended column to attendance_logs
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'attendance_logs'
                        AND column_name = 'is_extended'
                    ) THEN
                        ALTER TABLE attendance_logs ADD COLUMN is_extended BOOLEAN DEFAULT FALSE;
                        RAISE NOTICE 'Added is_extended column to attendance_logs';
                    END IF;
                END $$;
            """))

            # Backfill is_extended for existing records where shift_type contains 'Extended'
            conn.execute(text("""
                UPDATE attendance_logs
                SET is_extended = TRUE
                WHERE shift_type LIKE '%→ Extended%'
                  AND (is_extended IS NULL OR is_extended = FALSE)
            """))

            conn.commit()
            logger.info("Database migrations completed successfully.")
    except Exception as e:
        logger.warning("Database migration check failed: %s", e)