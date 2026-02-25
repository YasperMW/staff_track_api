from sqlalchemy import Column, String, Boolean, DateTime, Text, Numeric, Integer, Date, ForeignKey, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base
import uuid

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_number = Column(String(50), nullable=False, unique=True)
    national_id = Column(String(50), unique=True)
    first_name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    other_names = Column(String(150))
    suffix = Column(String(20))
    date_of_birth = Column(Date)
    gender = Column(String(10))
    home_of_origin = Column(String(150))
    traditional_authority = Column(String(100))
    district = Column(String(100))
    current_address = Column(Text)
    contact_number = Column(String(30), unique=True)
    email = Column(String(255), unique=True)
    marital_status = Column(String(20))
    spouse_name = Column(String(150))
    spouse_contact = Column(String(30))
    date_of_employment = Column(Date)
    designation_id = Column(UUID(as_uuid=True), ForeignKey("designations.designation_id"))
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.department_id"))
    is_head_of_department = Column(Boolean, default=False)
    phone = Column(String(30), unique=True)
    password_hash = Column(Text, nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.role_id"), nullable=False)
    status = Column(String(30), nullable=False, default="pending")
    profile_photo_url = Column(Text)
    blacklisted_at = Column(DateTime(timezone=True))
    blacklisted_reason = Column(Text)
    registration_timestamp = Column(DateTime(timezone=True))
    selfie_verified = Column(Boolean, default=False)
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    
    # Relationships
    role = relationship("Role", back_populates="users", foreign_keys=[role_id])
    department = relationship("Department", back_populates="users", foreign_keys=[department_id])
    designation = relationship("Designation", back_populates="users", foreign_keys=[designation_id])

class Designation(Base):
    __tablename__ = "designations"
    
    designation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.department_id"))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    
    # Relationships
    department = relationship("Department", back_populates="designations", foreign_keys=[department_id])
    users = relationship("User", back_populates="designation", foreign_keys="User.designation_id")

class Role(Base):
    __tablename__ = "roles"
    
    role_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    
    # Relationships
    users = relationship("User", back_populates="role", foreign_keys="User.role_id")

class Department(Base):
    __tablename__ = "departments"
    
    department_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(150), nullable=False, unique=True)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    
    # Relationships
    users = relationship("User", back_populates="department", foreign_keys="User.department_id")
    designations = relationship("Designation", back_populates="department", foreign_keys="Designation.department_id")

class AttendanceLog(Base):
    __tablename__ = "attendance_logs"
    
    attendance_log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    check_in_time = Column(DateTime(timezone=True))
    check_out_time = Column(DateTime(timezone=True))
    location = Column(String)  # This will store the geography as text for simplicity
    accuracy = Column(Numeric(6, 2))
    device_id = Column(String(100))
    offline_flag = Column(Boolean, default=False)
    sync_time = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])

class Notification(Base):
    __tablename__ = "notifications"
    
    notification_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), nullable=False)  # attendance, request, system, reminder
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])

class EmailVerification(Base):
    __tablename__ = "email_verifications"
    
    verification_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, index=True)
    otp_code = Column(String(6), nullable=False)
    purpose = Column(String(20), nullable=False)  # registration, password_reset
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
