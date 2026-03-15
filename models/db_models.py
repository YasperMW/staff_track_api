from sqlalchemy import Column, String, Boolean, DateTime, Text, Numeric, Integer, Date, ForeignKey, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from geoalchemy2 import Geography
from database import Base
import uuid
from datetime import datetime

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
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.grade_id"))
    status = Column(String(30), nullable=False, default="pending")
    profile_photo_url = Column(Text)
    blacklisted_at = Column(DateTime(timezone=True))
    blacklisted_reason = Column(Text)
    registration_timestamp = Column(DateTime(timezone=True))
    selfie_verified = Column(Boolean, default=False)
    last_login_at = Column(DateTime(timezone=True))
    failed_login_attempts = Column(Integer, default=0)  # Track consecutive failed login attempts
    locked_until = Column(DateTime(timezone=True))  # Temporary lock until this time
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    
    # Relationships
    role = relationship("Role", back_populates="users", foreign_keys=[role_id])
    grade = relationship("Grade", back_populates="users", foreign_keys=[grade_id])
    department = relationship("Department", back_populates="users", foreign_keys=[department_id])
    designation = relationship("Designation", back_populates="users", foreign_keys=[designation_id])
    fcm_tokens = relationship("UserFCMToken", back_populates="user", cascade="all, delete-orphan")

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

class Grade(Base):
    __tablename__ = "grades"
    
    grade_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False, unique=True)
    annual_leave_days = Column(Integer, nullable=False, default=21)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    
    # Relationships
    users = relationship("User", back_populates="grade", foreign_keys="User.grade_id")

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
    location = Column(Geography('POINT', srid=4326))  # PostGIS geography for spatial data
    accuracy = Column(Numeric(6, 2))
    device_id = Column(String(100))
    shift_type = Column(String(50))  # New field for shift tracking
    work_hours = Column(Numeric(5, 2))  # Pre-calculated work hours
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

class UserFCMToken(Base):
    __tablename__ = "user_fcm_tokens"
    
    token_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    fcm_token = Column(Text, nullable=False, unique=True)
    device_id = Column(String(100))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="fcm_tokens", foreign_keys=[user_id])

class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    
    preference_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    category = Column(String(50), nullable=False)  # requests, announcements, policies, security, reminders, system
    email_enabled = Column(Boolean, default=True)
    push_enabled = Column(Boolean, default=True)
    in_app_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    
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

class Announcement(Base):
    __tablename__ = "announcements"
    
    announcement_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), nullable=False)  # general, policy, urgent, event
    target_audience = Column(String(100), nullable=False)  # All Staff, department name, etc.
    target_department_id = Column(UUID(as_uuid=True), ForeignKey("departments.department_id"))
    target_role_id = Column(UUID(as_uuid=True), ForeignKey("roles.role_id"))
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True))
    attachment_url = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    
    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    target_department = relationship("Department", foreign_keys=[target_department_id])
    target_role = relationship("Role", foreign_keys=[target_role_id])
    target_departments = relationship("AnnouncementDepartment", back_populates="announcement")

class AnnouncementDepartment(Base):
    __tablename__ = "announcement_departments"
    
    announcement_id = Column(UUID(as_uuid=True), ForeignKey("announcements.announcement_id"), primary_key=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.department_id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now)
    
    # Relationships
    announcement = relationship("Announcement", back_populates="target_departments")
    department = relationship("Department")

class Holiday(Base):
    __tablename__ = "holidays"
    
    holiday_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    date = Column(Date, nullable=False)
    description = Column(Text)
    type = Column(String(50), nullable=False)  # Public Holiday, Religious, National, Institutional
    category = Column(String(20), nullable=False, default="institutional")  # 'public' or 'institutional'
    source = Column(String(100))  # Source for public holidays (e.g., 'government_api', 'manual')
    country_code = Column(String(2), default="MW")  # ISO country code for public holidays
    is_recurring = Column(Boolean, default=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    
    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

class AuditLog(Base):
    __tablename__ = "audit_logs"
    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    action = Column(String(100), nullable=False)
    entity = Column(String(100))
    details = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.now)

class Request(Base):
    __tablename__ = "requests"
    request_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    type = Column(String(50), nullable=False)
    reason = Column(Text)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    status = Column(String(20), default="pending", nullable=False)
    current_approver_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    approval_level = Column(Integer, default=1, nullable=False)
    approval_comments = Column(JSONB)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))

    # Section A - Applicant
    leave_grant_required = Column(Boolean, default=False)
    contact_address = Column(Text)

    # Second Form - Leave Duty Station (Applicant fields stay here)
    reason_for_leaving = Column(Text)
    travel_date = Column(Date)
    travel_place = Column(String(255))
    
    cost_accommodation = Column(Numeric(12, 2))
    cost_breakfast = Column(Numeric(12, 2))
    cost_lunch = Column(Numeric(12, 2))
    cost_supper = Column(Numeric(12, 2))
    cost_public_transport = Column(Numeric(12, 2))
    cost_fuel_lubricants = Column(Numeric(12, 2))
    cost_total = Column(Numeric(12, 2))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    current_approver = relationship("User", foreign_keys=[current_approver_id])
    approvals = relationship("RequestApproval", back_populates="request")

class RequestApproval(Base):
    __tablename__ = "request_approvals"
    approval_id = Column("request_approval_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.request_id"), nullable=False)
    approver_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    level = Column(Integer, default=1)
    action = Column(String(20), nullable=False)
    comment = Column(Text)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.now)

    # Move stage-specific fields here
    # Section B - HOD (Leave)
    hod_recommended_from = Column(Date)
    hod_recommended_to = Column(Date)
    hod_not_recommended_reason = Column(Text)

    # Section C - HR (Leave)
    hr_annual_entitlement = Column(Numeric(5, 2))
    hr_entitlement_taken_from = Column(Date)
    hr_entitlement_taken_to = Column(Date)
    hr_last_leave_from = Column(Date)
    hr_last_leave_to = Column(Date)
    hr_last_leave_days = Column(Numeric(5, 2))
    hr_balance_if_approved = Column(Numeric(5, 2))
    hr_leave_grant_status = Column(String(30))

    # Section D - Administrator (Leave)
    admin_granted_from = Column(Date)
    admin_granted_to = Column(Date)
    admin_total_days_approved = Column(Numeric(5, 2))

    # Section C - Accountant (Trip)
    accountant_funds_available = Column(Boolean)
    accountant_signed_date = Column(Date)
    
    # Section D - HOD (Trip)
    hod_trip_recommendation = Column(Text)
    
    # Section E - Admin (Trip)
    admin_trip_approval_details = Column(Text)
    
    # Relationships
    request = relationship("Request", back_populates="approvals")
    approver = relationship("User", foreign_keys=[approver_id])

class LeaveBalance(Base):
    __tablename__ = "leave_balances"
    leave_balance_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    leave_type = Column(String(50), nullable=False)
    allocated_days = Column(Numeric(5,2), default=0)
    used_days = Column(Numeric(5,2), default=0)
    bonus_days = Column(Numeric(5,2), default=0)
    remaining_days = Column(Numeric(5,2))
    year = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    user = relationship("User", foreign_keys=[user_id])

class EmployeeFile(Base):
    __tablename__ = "employee_files"
    employee_file_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_url = Column(Text, nullable=False)
    original_filename = Column(String(255))
    upload_date = Column(DateTime(timezone=True), nullable=False, default=datetime.now)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    user = relationship("User", foreign_keys=[user_id])
