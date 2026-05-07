from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel
from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, RequestApproval, Notification, LeaveBalance, Role, Request
from fcm_service import send_push_notification
from mail_service import email_service
from notification_service import notification_service

router = APIRouter(prefix="/requests", tags=["requests"])


class RequestCreate(BaseModel):
    type: str
    start_date: str
    end_date: Optional[str] = None
    # Section A - Leave Request
    leave_grant_required: bool = False
    contact_address: Optional[str] = None
    # Section A - Trip Request
    reason_for_leaving: Optional[str] = None
    travel_date: Optional[str] = None
    travel_place: Optional[str] = None
    # Section B - Trip Costs
    cost_accommodation: Optional[float] = None
    cost_breakfast: Optional[float] = None
    cost_lunch: Optional[float] = None
    cost_supper: Optional[float] = None
    cost_public_transport: Optional[float] = None
    cost_fuel_lubricants: Optional[float] = None
    cost_total: Optional[float] = None


class ApprovalPayload(BaseModel):
    comment: Optional[str] = None
    # HOD fields (Section B - Leave)
    hod_recommended_from: Optional[date] = None
    hod_recommended_to: Optional[date] = None
    hod_not_recommended_reason: Optional[str] = None
    # HR fields (Section C - Leave)
    hr_annual_entitlement: Optional[float] = None
    hr_entitlement_taken_from: Optional[date] = None
    hr_entitlement_taken_to: Optional[date] = None
    hr_last_leave_from: Optional[date] = None
    hr_last_leave_to: Optional[date] = None
    hr_last_leave_days: Optional[float] = None
    hr_balance_if_approved: Optional[float] = None
    hr_leave_grant_status: Optional[str] = None
    # Admin fields (Section D - Leave)
    admin_granted_from: Optional[date] = None
    admin_granted_to: Optional[date] = None
    admin_total_days_approved: Optional[float] = None
    # Section C - Trip (Accountant)
    accountant_funds_available: Optional[bool] = None
    # Section D - Trip (HOD)
    hod_trip_recommendation: Optional[str] = None
    # Section E - Trip (Admin)
    admin_trip_approval_details: Optional[str] = None


@router.get("")
async def get_all_requests(
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all requests with optional filtering and pagination
    """
    print(f"Get all requests called by user: {current_user.user_id}, role: {current_user.role}")
    
    # Check if user is admin/HR to see all requests
    is_admin = current_user.role and current_user.role.name.lower() in ['admin', 'administrator', 'hr', 'system admin', 'principal hospital administrator']
    
    where_clauses = ["r.deleted_at IS NULL"]
    params = {}
    
    # For non-admin users, only show their own requests
    if not is_admin:
        where_clauses.append("r.user_id = :user_id")
        params["user_id"] = current_user.user_id
    
    # Status filter
    if status_filter and status_filter.lower() in ["pending", "approved", "rejected", "denied"]:
        where_clauses.append("r.status = :status")
        params["status"] = status_filter.lower()
    
    # Type filter
    if type_filter:
        where_clauses.append("LOWER(r.type) LIKE :type")
        params["type"] = f"%{type_filter.lower()}%"
    
    query = f"""
        SELECT 
            r.request_id,
            r.type,
            r.start_date,
            r.end_date,
            r.status,
            r.created_at,
            r.updated_at,
            u.first_name,
            u.surname,
            u.user_id,
            u.employee_number,
            d.name as department_name,
            r.leave_grant_required,
            r.contact_address,
            r.reason_for_leaving,
            r.travel_place
        FROM requests r
        JOIN users u ON u.user_id = r.user_id
        LEFT JOIN departments d ON d.department_id = u.department_id
        WHERE {' AND '.join(where_clauses)}
    """
    
    sort_map = {
        "created_at": "r.created_at", 
        "start_date": "r.start_date", 
        "end_date": "r.end_date",
        "type": "r.type",
        "status": "r.status"
    }
    sort_col = sort_map.get((sort_by or "created_at").lower(), "r.created_at")
    sort_dir = "ASC" if (sort_order or "desc").lower() == "asc" else "DESC"
    limit = max(1, min(page_size, 200))
    offset = max(0, (max(1, page) - 1) * limit)
    
    query = f"{query} ORDER BY {sort_col} {sort_dir} LIMIT :limit OFFSET :offset"
    params.update({"limit": limit, "offset": offset})
    
    result = db.execute(text(query), params).fetchall()
    print(f"Found {len(result)} requests for user {current_user.user_id}")
    
    requests = []
    
    for row in result:
        start_date = row[2]
        end_date = row[3]
        created_at = row[5]
        updated_at = row[6]
        
        # Calculate duration
        if end_date and end_date != start_date:
            duration_days = (end_date - start_date).days + 1
            duration = duration_days
        else:
            duration = 1
        
        # Determine request title and description
        request_type = row[1]
        if request_type.lower() == "leave duty station":
            title = "Travel Request"
            description = row[14] or f"Travel to {row[14] or 'destination'}"
        else:
            title = f"{request_type} Request"
            description = f"{request_type} request for {duration} day{'s' if duration > 1 else ''}"
        
        requests.append({
            "id": str(row[0]),
            "user_id": str(row[9]),
            "user_name": f"{row[7] or ''} {row[8] or ''}".strip(),
            "employee_number": row[10] or "",
            "department": row[11] or "Unknown",
            "type": request_type.lower().replace(" ", "_"),
            "status": row[4].lower(),
            "title": title,
            "description": description,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date and end_date != start_date else None,
            "duration": duration,
            "reason": row[12] or row[13] or None,
            "created_at": created_at.isoformat() if created_at else None,
            "updated_at": updated_at.isoformat() if updated_at else None,
        })
    
    return {"requests": requests}


@router.get("/summary")
async def get_requests_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        text(
            """
            SELECT type, COUNT(*) AS count
            FROM requests
            WHERE status = 'pending' AND deleted_at IS NULL
            GROUP BY type
            """
        )
    ).fetchall()

    total_pending = 0
    by_type = []

    for row in result:
        request_type = row[0]
        count = int(row[1] or 0)
        total_pending += count
        by_type.append(
            {
                "type": request_type,
                "count": count,
            }
        )

    return {
        "total_pending": total_pending,
        "by_type": by_type,
    }


@router.post("")
async def create_request(
    payload: RequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        start_date = date.fromisoformat(payload.start_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid start_date format. Use YYYY-MM-DD.",
        )

    end_date_value = payload.end_date or payload.start_date
    try:
        end_date = date.fromisoformat(end_date_value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid end_date format. Use YYYY-MM-DD.",
        )

    # Validate Annual Leave days against Grade
    if payload.type.lower() == "annual leave":
        requested_days = (end_date - start_date).days + 1
        if current_user.grade:
            max_days = current_user.grade.annual_leave_days
            if requested_days > max_days:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Annual leave request exceeds your grade limit of {max_days} days. You requested {requested_days} days."
                )
        else:
            # If no grade is assigned, use a default or allow for now? 
            # The user said grade selection is added during registration, so new users will have it.
            pass

    now = datetime.utcnow()
    # Determine initial approver - always start with HOD
    # Approval chain: HOD (Level 1) -> HR (Level 2) -> Admin (Level 3) -> Accountant (Level 4)
    approver_id = None

    # First approver is always the HOD of the user's department
    hod = db.query(User).filter(
        User.department_id == current_user.department_id,
        User.is_head_of_department == True,
        User.deleted_at.is_(None)
    ).first()
    if hod:
        approver_id = hod.user_id
    else:
        # Fallback to HR if no HOD found
        hr = db.query(User).join(Role, User.role_id == Role.role_id).filter(
            Role.name == "HR",
            User.deleted_at.is_(None)
        ).first()
        if hr:
            approver_id = hr.user_id
        else:
            # Fallback to Admin if no HR found
            principal = db.query(User).join(Role, User.role_id == Role.role_id).filter(
                Role.name == "Principal Hospital Administrator",
                User.deleted_at.is_(None)
            ).first()
            if principal:
                approver_id = principal.user_id
            else:
                # Final fallback to Accountant
                accountant = db.query(User).join(Role, User.role_id == Role.role_id).filter(
                    Role.name == "Accountant",
                    User.deleted_at.is_(None)
                ).first()
                if accountant:
                    approver_id = accountant.user_id

    new_request = Request(
        user_id=current_user.user_id,
        type=payload.type,
        start_date=start_date,
        end_date=end_date,
        status='pending',
        current_approver_id=approver_id,
        approval_level=1,
        leave_grant_required=payload.leave_grant_required,
        contact_address=payload.contact_address,
        # Trip fields
        reason_for_leaving=payload.reason_for_leaving,
        travel_date=date.fromisoformat(payload.travel_date) if payload.travel_date else None,
        travel_place=payload.travel_place,
        cost_accommodation=payload.cost_accommodation,
        cost_breakfast=payload.cost_breakfast,
        cost_lunch=payload.cost_lunch,
        cost_supper=payload.cost_supper,
        cost_public_transport=payload.cost_public_transport,
        cost_fuel_lubricants=payload.cost_fuel_lubricants,
        cost_total=payload.cost_total,
        created_at=now,
        updated_at=now
    )
    
    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    # Send enhanced notification to approver using NotificationService
    if approver_id:
        try:
            await notification_service.send_notification(
                db=db,
                user_id=approver_id,
                title="New Request Submitted",
                message=f"{current_user.first_name} {current_user.surname} submitted a {payload.type} request for your approval",
                notification_type="request_submitted",
                data={
                    "request_id": str(new_request.request_id),
                    "requester_name": f"{current_user.first_name} {current_user.surname}",
                    "request_type": payload.type
                },
                email_data={
                    "requester_name": f"{current_user.first_name} {current_user.surname}",
                    "request_type": payload.type,
                    "start_date": start_date.strftime('%B %d, %Y'),
                    "end_date": end_date.strftime('%B %d, %Y') if end_date != start_date else None
                },
                force_send=True
            )
        except Exception as e:
            # Log error but don't fail the request creation
            print(f"Failed to send notification to approver: {e}")

    return {"success": True, "id": str(new_request.request_id)}


@router.get("/{request_id}/approvals")
async def get_request_approvals(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    approvals = db.query(RequestApproval).filter(RequestApproval.request_id == request_id).order_by(RequestApproval.timestamp.asc()).all()
    
    return [
        {
            "approver_name": f"{a.approver.first_name} {a.approver.surname}" if a.approver else "Unknown",
            "level": a.level,
            "action": a.action,
            "comment": a.comment,
            "timestamp": a.timestamp.isoformat() if a.timestamp else None,
            # Leave Stage 1 (HOD)
            "hod_recommended_from": a.hod_recommended_from.isoformat() if a.hod_recommended_from else None,
            "hod_recommended_to": a.hod_recommended_to.isoformat() if a.hod_recommended_to else None,
            "hod_not_recommended_reason": a.hod_not_recommended_reason,
            # Leave Stage 2 (HR)
            "hr_annual_entitlement": float(a.hr_annual_entitlement) if a.hr_annual_entitlement else None,
            "hr_entitlement_taken_from": a.hr_entitlement_taken_from.isoformat() if a.hr_entitlement_taken_from else None,
            "hr_entitlement_taken_to": a.hr_entitlement_taken_to.isoformat() if a.hr_entitlement_taken_to else None,
            "hr_last_leave_from": a.hr_last_leave_from.isoformat() if a.hr_last_leave_from else None,
            "hr_last_leave_to": a.hr_last_leave_to.isoformat() if a.hr_last_leave_to else None,
            "hr_last_leave_days": float(a.hr_last_leave_days) if a.hr_last_leave_days else None,
            "hr_balance_if_approved": float(a.hr_balance_if_approved) if a.hr_balance_if_approved else None,
            "hr_leave_grant_status": a.hr_leave_grant_status,
            # Leave Stage 3 (Admin)
            "admin_granted_from": a.admin_granted_from.isoformat() if a.admin_granted_from else None,
            "admin_granted_to": a.admin_granted_to.isoformat() if a.admin_granted_to else None,
            "admin_total_days_approved": float(a.admin_total_days_approved) if a.admin_total_days_approved else None,
            # Trip Stage 1 (Accountant)
            "accountant_funds_available": a.accountant_funds_available,
            "accountant_signed_date": a.accountant_signed_date.isoformat() if a.accountant_signed_date else None,
            # Trip Stage 2 (HOD)
            "hod_trip_recommendation": a.hod_trip_recommendation,
            # Trip Stage 3 (Admin)
            "admin_trip_approval_details": a.admin_trip_approval_details,
        }
        for a in approvals
    ]


@router.get("/admin/my-requests")
async def get_my_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print(f"My requests called by user: {current_user.user_id}")
    
    result = db.execute(
        text(
            """
            SELECT 
                r.request_id,
                r.type,
                r.start_date,
                r.end_date,
                r.status,
                u.first_name,
                u.surname,
                u.user_id,
                r.created_at,
                r.approval_level,
                r.leave_grant_required,
                r.contact_address
            FROM requests r
            JOIN users u ON u.user_id = r.user_id
            WHERE r.status = 'pending'
              AND r.deleted_at IS NULL
              AND r.user_id = :user_id
            ORDER BY r.created_at DESC
            """
        ),
        {"user_id": current_user.user_id},
    ).fetchall()
    
    print(f"Found {len(result)} my requests for user {current_user.user_id}")

    requests = []

    for row in result:
        start_date = row[2]
        end_date = row[3]
        created_at = row[8]
        
        if end_date and end_date != start_date:
            date_range = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d')}"
        else:
            date_range = start_date.strftime("%b %d")
        
        # Calculate duration - for leave duty station, show "travelling day" instead of duration
        if row[1].lower() == "leave duty station":
            duration = "travelling day"
        else:
            duration = 1
            if end_date and end_date != start_date:
                duration = (end_date - start_date).days + 1
            duration = f"{duration} day{'s' if duration > 1 else ''}"
        
        requests.append({
            "id": str(row[0]),
            "type": row[1],
            "date_range": date_range,
            "duration": duration,
            "description": f"{row[1]} request for {duration}",
            "created_at": created_at.isoformat() if created_at else None,
            "user_id": str(row[7]),
            "user_name": f"{row[5] or ''} {row[6] or ''}".strip(),
            "approval_level": row[9],
            "leave_grant_required": row[10],
            "contact_address": row[11],
        })

    return requests


@router.get("/admin/all-pending-debug")
async def get_all_pending_requests_debug(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print(f"Debug: All pending requests called by user: {current_user.user_id}")
    
    result = db.execute(
        text(
            """
            SELECT 
                r.request_id,
                r.type,
                r.start_date,
                r.end_date,
                r.status,
                r.current_approver_id,
                u.first_name,
                u.surname,
                u.user_id
            FROM requests r
            JOIN users u ON u.user_id = r.user_id
            WHERE r.status = 'pending'
              AND r.deleted_at IS NULL
            ORDER BY r.created_at DESC
            """
        )
    ).fetchall()
    
    print(f"Debug: Found {len(result)} total pending requests")
    
    requests = []
    for row in result:
        requests.append({
            "id": str(row[0]),
            "type": row[1],
            "start_date": str(row[2]),
            "end_date": str(row[3]),
            "status": row[4],
            "current_approver_id": str(row[5]) if row[5] else None,
            "user_name": f"{row[6] or ''} {row[7] or ''}".strip(),
            "user_id": str(row[8]),
        })
    
    return requests


@router.get("/admin/pending-list")
async def get_admin_pending_requests_list(
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    department_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print(f"Admin pending requests called by user: {current_user.user_id}, role: {current_user.role}")
    if not current_user.role or not current_user.role.name:
        pass

    # For admins, show all pending requests (not just assigned ones)
    # For non-admins, show only their assigned requests
    is_admin = current_user.role.name.lower() in ['admin', 'administrator', 'hr', 'system admin']
    
    where_clauses = ["r.deleted_at IS NULL"]
    params = {}
    if is_admin:
        if status_filter and status_filter.lower() in ["pending", "approved", "denied"]:
            where_clauses.append("r.status = :status")
            params["status"] = status_filter.lower()
        else:
            where_clauses.append("r.status = 'pending'")
        if type_filter:
            where_clauses.append("LOWER(r.type) LIKE :type")
            params["type"] = f"%{type_filter.lower()}%"
        if department_id:
            where_clauses.append("u.department_id = :dept")
            params["dept"] = department_id
        query = f"""
            SELECT 
                r.request_id,
                r.type,
                r.start_date,
                r.end_date,
                r.status,
                u.first_name,
                u.surname,
                u.user_id,
                r.approval_level,
                r.leave_grant_required,
                r.contact_address
            FROM requests r
            JOIN users u ON u.user_id = r.user_id
            WHERE {' AND '.join(where_clauses)}
        """
    else:
        where_clauses.append("(r.current_approver_id IS NULL OR r.current_approver_id = :approver_id)")
        params["approver_id"] = current_user.user_id
        if status_filter and status_filter.lower() in ["pending", "approved", "denied"]:
            where_clauses.append("r.status = :status")
            params["status"] = status_filter.lower()
        else:
            where_clauses.append("r.status = 'pending'")
        if type_filter:
            where_clauses.append("LOWER(r.type) LIKE :type")
            params["type"] = f"%{type_filter.lower()}%"
        if department_id:
            where_clauses.append("u.department_id = :dept")
            params["dept"] = department_id
        query = f"""
            SELECT 
                r.request_id,
                r.type,
                r.start_date,
                r.end_date,
                r.status,
                u.first_name,
                u.surname,
                u.user_id,
                r.approval_level,
                r.leave_grant_required,
                r.contact_address
            FROM requests r
            JOIN users u ON u.user_id = r.user_id
            WHERE {' AND '.join(where_clauses)}
        """

    sort_map = {"created_at": "r.created_at", "start_date": "r.start_date", "end_date": "r.end_date"}
    sort_col = sort_map.get((sort_by or "created_at").lower(), "r.created_at")
    sort_dir = "ASC" if (sort_order or "desc").lower() == "asc" else "DESC"
    limit = max(1, min(page_size, 200))
    offset = max(0, (max(1, page) - 1) * limit)
    query = f"{query} ORDER BY {sort_col} {sort_dir} LIMIT :limit OFFSET :offset"
    params.update({"limit": limit, "offset": offset})
    result = db.execute(text(query), params).fetchall()
    print(f"Found {len(result)} pending requests for admin {current_user.user_id} (is_admin: {is_admin})")

    requests = []

    for row in result:
        start_date = row[2]
        end_date = row[3]
        if end_date and end_date != start_date:
            date_range = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d')}"
        else:
            date_range = start_date.strftime("%b %d")

        # Calculate duration - for leave duty station, show "travelling day" instead of duration
        if row[1].lower() == "leave duty station":
            duration = "travelling day"
        else:
            if end_date and end_date != start_date:
                duration_days = (end_date - start_date).days + 1
                duration = f"{duration_days} days"
            else:
                duration = "1 day"

        full_name = f"{row[5] or ''} {row[6] or ''}".strip()

        # Check if current user already approved/denied this request at this level
        request_id = row[0]
        current_level = row[8]
        existing_approval = db.query(RequestApproval).filter(
            RequestApproval.request_id == request_id,
            RequestApproval.approver_id == current_user.user_id,
            RequestApproval.level == current_level
        ).first()
        
        user_has_acted = existing_approval is not None

        requests.append(
            {
                "id": str(row[0]),
                "type": row[1],
                "status": row[4],
                "date_range": date_range,
                "duration": duration,
                "user_name": full_name,
                "user_id": str(row[7]),
                "approval_level": row[8],
                "leave_grant_required": row[9],
                "contact_address": row[10],
                "user_has_acted": user_has_acted,
            }
        )

    return requests


@router.post("/admin/{request_id}/approve")
async def approve_request(
    request_id: str,
    payload: ApprovalPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(Request).filter(Request.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    
    if req.current_approver_id and str(req.current_approver_id) != str(current_user.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not current approver")

    now = datetime.utcnow()
    next_approver_id = None
    
    # Create the approval record with common fields
    approval = RequestApproval(
        request_id=req.request_id,
        approver_id=current_user.user_id,
        action="approve",
        comment=payload.comment,
        timestamp=now
    )
    
    # Trip/Duty Station Request Approval Chain (HOD -> HR -> Admin -> Accountant)
    if req.type.lower() == "leave duty station":
        # Stage 1: HOD (Section B)
        if req.approval_level == 1:
            approval.hod_trip_recommendation = payload.hod_trip_recommendation
            approval.level = 1
            req.approval_level = 2

            # Next: HR
            hr = db.query(User).join(Role, User.role_id == Role.role_id).filter(
                Role.name == "HR",
                User.deleted_at.is_(None)
            ).first()
            next_approver_id = hr.user_id if hr else None
            req.current_approver_id = next_approver_id

        # Stage 2: HR (Section C)
        elif req.approval_level == 2:
            # HR reviews and confirms leave entitlement
            approval.hr_annual_entitlement = payload.hr_annual_entitlement
            approval.hr_balance_if_approved = payload.hr_balance_if_approved
            approval.level = 2
            req.approval_level = 3

            # Next: Administrator
            admin = db.query(User).join(Role, User.role_id == Role.role_id).filter(
                Role.name == "Principal Hospital Administrator",
                User.deleted_at.is_(None)
            ).first()
            next_approver_id = admin.user_id if admin else None
            req.current_approver_id = next_approver_id

        # Stage 3: Admin (Section D)
        elif req.approval_level == 3:
            approval.admin_trip_approval_details = payload.admin_trip_approval_details
            approval.level = 3
            req.approval_level = 4

            # Next: Accountant (Final - budget check)
            accountant = db.query(User).join(Role, User.role_id == Role.role_id).filter(
                Role.name == "Accountant",
                User.deleted_at.is_(None)
            ).first()
            next_approver_id = accountant.user_id if accountant else None
            req.current_approver_id = next_approver_id

        # Stage 4: Accountant (Final approval)
        elif req.approval_level == 4:
            approval.accountant_funds_available = payload.accountant_funds_available
            approval.accountant_signed_date = now.date()
            approval.level = 4
            req.status = 'approved'
            req.current_approver_id = None
            
    # Standard Leave Request Chain (HOD -> HR -> Admin)
    else:
        # Stage 1: HOD (Section B)
        if req.approval_level == 1:
            approval.hod_recommended_from = payload.hod_recommended_from
            approval.hod_recommended_to = payload.hod_recommended_to
            approval.hod_not_recommended_reason = payload.hod_not_recommended_reason
            approval.level = 1
            req.approval_level = 2
            
            # Next: HR
            hr = db.query(User).join(Role, User.role_id == Role.role_id).filter(Role.name == "HR", User.deleted_at.is_(None)).first()
            next_approver_id = hr.user_id if hr else None
            req.current_approver_id = next_approver_id
            
        # Stage 2: HR (Section C)
        elif req.approval_level == 2:
            approval.hr_annual_entitlement = payload.hr_annual_entitlement
            approval.hr_entitlement_taken_from = payload.hr_entitlement_taken_from
            approval.hr_entitlement_taken_to = payload.hr_entitlement_taken_to
            approval.hr_last_leave_from = payload.hr_last_leave_from
            approval.hr_last_leave_to = payload.hr_last_leave_to
            approval.hr_last_leave_days = payload.hr_last_leave_days
            approval.hr_balance_if_approved = payload.hr_balance_if_approved
            approval.hr_leave_grant_status = payload.hr_leave_grant_status
            approval.level = 2
            req.approval_level = 3
            
            # Next: Administrator
            admin = db.query(User).join(Role, User.role_id == Role.role_id).filter(Role.name == "Principal Hospital Administrator", User.deleted_at.is_(None)).first()
            next_approver_id = admin.user_id if admin else None
            req.current_approver_id = next_approver_id
            
        # Stage 3: Admin (Section D)
        elif req.approval_level == 3:
            approval.admin_granted_from = payload.admin_granted_from
            approval.admin_granted_to = payload.admin_granted_to
            approval.admin_total_days_approved = payload.admin_total_days_approved
            approval.level = 3
            req.approval_level = 4

            # Next: Accountant (Level 4)
            accountant = db.query(User).join(Role, User.role_id == Role.role_id).filter(
                Role.name == "Accountant",
                User.deleted_at.is_(None)
            ).first()
            next_approver_id = accountant.user_id if accountant else None
            req.current_approver_id = next_approver_id

        # Stage 4: Accountant (Final approval)
        elif req.approval_level == 4:
            approval.level = 4
            req.status = 'approved'
            req.current_approver_id = None

            # Update Leave Balance only after final approval
            duration = payload.admin_total_days_approved or 0
            if req.type in ["annual_leave", "compassionate_leave", "maternity", "paternity", "unpaid_leave"]:
                lb = db.query(LeaveBalance).filter(LeaveBalance.user_id == req.user_id, LeaveBalance.leave_type == req.type).first()
                if not lb:
                    lb = LeaveBalance(user_id=req.user_id, leave_type=req.type, allocated_days=0, bonus_days=0, used_days=0, remaining_days=0, year=now.year)
                    db.add(lb)
                    db.commit()
                    db.refresh(lb)
                lb.used_days = (lb.used_days or 0) + duration
                lb.updated_at = now
                db.commit()

    req.updated_at = now
    db.add(approval)
    db.commit()

    # Notify next approver or requester using enhanced NotificationService
    requester = db.query(User).filter(User.user_id == req.user_id).first()
    if next_approver_id:
        # Send notification to next approver
        try:
            await notification_service.send_notification(
                db=db,
                user_id=next_approver_id,
                title="Request Pending Approval",
                message=f"{req.type} requires your approval",
                notification_type="request_escalated",
                data={
                    "request_id": str(req.request_id),
                    "request_type": req.type
                },
                force_send=True
            )
        except Exception as e:
            print(f"Failed to send escalation notification: {e}")
    else:
        # Final approval notification to requester
        if requester:
            try:
                await notification_service.send_notification(
                    db=db,
                    user_id=requester.user_id,
                    title="Request Approved",
                    message=f"Your {req.type} request has been approved",
                    notification_type="request_approved",
                    data={
                        "request_id": str(req.request_id),
                        "request_type": req.type
                    },
                    email_data={
                        "requester_name": f"{requester.first_name} {requester.surname}",
                        "request_type": req.type,
                        "start_date": req.start_date.strftime('%B %d, %Y'),
                        "end_date": req.end_date.strftime('%B %d, %Y') if req.end_date != req.start_date else None,
                        "approver_name": f"{current_user.first_name} {current_user.surname}",
                        "comment": payload.comment
                    },
                    force_send=True
                )
            except Exception as e:
                print(f"Failed to send approval notification: {e}")

    return {"success": True}


@router.get("/my-requests")
async def get_my_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        text(
            """
            SELECT 
                r.request_id,
                r.type,
                r.start_date,
                r.end_date,
                r.status,
                r.created_at
            FROM requests r
            WHERE r.user_id = :user_id
              AND r.deleted_at IS NULL
            ORDER BY r.created_at DESC
            """
        ),
        {"user_id": current_user.user_id},
    ).fetchall()

    requests = []

    for row in result:
        start_date = row[2]
        end_date = row[3]
        if end_date and end_date != start_date:
            date_range = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d')}"
        else:
            date_range = start_date.strftime("%b %d")

        # Calculate duration - for leave duty station, show "travelling day" instead of duration
        if row[1].lower() == "leave duty station":
            duration = "travelling day"
        else:
            if end_date and end_date != start_date:
                duration_days = (end_date - start_date).days + 1
                duration = f"{duration_days} days"
            else:
                duration = "1 day"

        requests.append(
            {
                "id": str(row[0]),
                "type": row[1],
                "status": row[4].capitalize(),
                "date_range": date_range,
                "duration": duration,
                "description": f"{row[1]} request for {duration}",
                "created_at": row[5].isoformat() if row[5] else None,
            }
        )

    return requests


@router.post("/admin/{request_id}/withdraw")
async def withdraw_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        text(
            """
            UPDATE requests
            SET status = 'withdrawn',
                updated_at = NOW()
            WHERE request_id = :request_id
              AND user_id = :user_id
              AND status = 'pending'
              AND deleted_at IS NULL
            RETURNING request_id
            """
        ),
        {"request_id": request_id, "user_id": current_user.user_id},
    ).fetchone()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found or cannot be withdrawn",
        )

    db.commit()

    return {"success": True}


@router.get("/admin/team-requests")
async def get_team_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get requests from all team members except the current user"""
    result = db.execute(
        text(
            """
            SELECT 
                r.request_id,
                r.type,
                r.start_date,
                r.end_date,
                r.status,
                u.first_name,
                u.surname,
                u.user_id,
                r.created_at
            FROM requests r
            JOIN users u ON u.user_id = r.user_id
            WHERE r.user_id != :user_id
              AND r.deleted_at IS NULL
            ORDER BY r.created_at DESC
            """
        ),
        {"user_id": current_user.user_id},
    ).fetchall()
    
    print(f"Found {len(result)} team requests for user {current_user.user_id}")

    requests = []

    for row in result:
        start_date = row[2]
        end_date = row[3]
        created_at = row[8]
        
        if end_date and end_date != start_date:
            date_range = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d')}"
        else:
            date_range = start_date.strftime("%b %d")
        
        # Calculate duration - for leave duty station, show "travelling day" instead of duration
        if row[1].lower() == "leave duty station":
            duration = "travelling day"
        else:
            duration = 1
            if end_date and end_date != start_date:
                duration = (end_date - start_date).days + 1
            duration = f"{duration} day{'s' if duration > 1 else ''}"
        
        requests.append({
            "id": str(row[0]),
            "type": row[1],
            "date_range": date_range,
            "duration": duration,
            "description": f"{row[1]} request for {duration}",
            "created_at": created_at.isoformat() if created_at else None,
            "user_id": str(row[7]),
            "user_name": f"{row[5] or ''} {row[6] or ''}".strip(),
            "status": row[4].capitalize() if row[4] else "Unknown"
        })

    return requests


@router.post("/admin/{request_id}/deny")
async def deny_request(
    request_id: str,
    payload: ApprovalPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(Request).filter(Request.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    
    if req.current_approver_id and str(req.current_approver_id) != str(current_user.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not current approver")

    now = datetime.utcnow()
    req.status = 'denied'
    req.updated_at = now
    req.current_approver_id = None
    
    # Create denial record
    approval = RequestApproval(
        request_id=req.request_id,
        approver_id=current_user.user_id,
        level=req.approval_level,
        action="deny",
        comment=payload.comment,
        timestamp=now
    )
    
    db.add(approval)
    db.commit()

    # Send enhanced notification to requester using NotificationService
    requester = db.query(User).filter(User.user_id == req.user_id).first()
    if requester:
        try:
            await notification_service.send_notification(
                db=db,
                user_id=requester.user_id,
                title="Request Denied",
                message=f"Your {req.type} request has been denied",
                notification_type="request_denied",
                data={
                    "request_id": str(req.request_id),
                    "request_type": req.type
                },
                email_data={
                    "requester_name": f"{requester.first_name} {requester.surname}",
                    "request_type": req.type,
                    "start_date": req.start_date.strftime('%B %d, %Y'),
                    "end_date": req.end_date.strftime('%B %d, %Y') if req.end_date != req.start_date else None,
                    "approver_name": f"{current_user.first_name} {current_user.surname}",
                    "comment": payload.comment
                },
                force_send=True
            )
        except Exception as e:
            print(f"Failed to send denial notification: {e}")

    return {"success": True}


class SimpleApprovalPayload(BaseModel):
    reason: Optional[str] = None


@router.put("/{request_id}/approve")
async def simple_approve_request(
    request_id: str,
    payload: SimpleApprovalPayload = SimpleApprovalPayload(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Simple approve endpoint for frontend compatibility
    """
    # Use the existing approve endpoint logic but with simplified payload
    approval_payload = ApprovalPayload(comment=payload.reason)
    
    # Call the existing approve function
    return await approve_request(request_id, approval_payload, db, current_user)


@router.put("/{request_id}/reject")
async def simple_reject_request(
    request_id: str,
    payload: SimpleApprovalPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Simple reject endpoint for frontend compatibility
    """
    req = db.query(Request).filter(Request.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    
    if req.current_approver_id and str(req.current_approver_id) != str(current_user.user_id):
        # Allow admins to reject any request
        is_admin = current_user.role and current_user.role.name.lower() in ['admin', 'administrator', 'hr', 'system admin', 'principal hospital administrator']
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not current approver")

    now = datetime.utcnow()
    
    # Create rejection approval record
    approval = RequestApproval(
        request_id=req.request_id,
        approver_id=current_user.user_id,
        action="reject",
        comment=payload.reason,
        timestamp=now,
        level=req.approval_level
    )
    
    # Update request status
    req.status = 'rejected'
    req.current_approver_id = None
    req.updated_at = now
    
    db.add(approval)
    db.commit()

    # Send enhanced notification to requester using NotificationService
    requester = db.query(User).filter(User.user_id == req.user_id).first()
    if requester:
        try:
            await notification_service.send_notification(
                db=db,
                user_id=requester.user_id,
                title="Request Rejected",
                message=f"Your {req.type} request has been rejected",
                notification_type="request_denied",
                data={
                    "request_id": str(req.request_id),
                    "request_type": req.type
                },
                email_data={
                    "requester_name": f"{requester.first_name} {requester.surname}",
                    "request_type": req.type,
                    "start_date": req.start_date.strftime('%B %d, %Y'),
                    "end_date": req.end_date.strftime('%B %d, %Y') if req.end_date != req.start_date else None,
                    "approver_name": f"{current_user.first_name} {current_user.surname}",
                    "comment": payload.reason
                },
                force_send=True
            )
        except Exception as e:
            print(f"Failed to send rejection notification: {e}")

    return {"success": True}
