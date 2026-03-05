from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel
from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, RequestApproval, Notification, LeaveBalance, Role
from fcm_service import send_push_notification
from mail_service import email_service

router = APIRouter(prefix="/requests", tags=["requests"])


class RequestCreate(BaseModel):
    type: str
    start_date: str
    end_date: Optional[str] = None


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

    now = datetime.utcnow()
    # Determine initial approver: HOD -> HR Admin -> Accountant -> Principal Hospital Administrator
    approver_id = None
    hod = db.query(User).filter(
        User.department_id == current_user.department_id,
        User.is_head_of_department == True,
        User.deleted_at.is_(None)
    ).first()
    if hod:
        approver_id = hod.user_id
    else:
        hr = db.query(User).join(Role).filter(Role.name.in_(["HR Admin", "HR"]), User.deleted_at.is_(None)).first()
        if hr:
            approver_id = hr.user_id
        else:
            accountant = db.query(User).join(Role).filter(Role.name == "Accountant", User.deleted_at.is_(None)).first()
            if accountant:
                approver_id = accountant.user_id
            else:
                principal = db.query(User).join(Role).filter(Role.name == "Principal Hospital Administrator", User.deleted_at.is_(None)).first()
                if principal:
                    approver_id = principal.user_id

    result = db.execute(
        text(
            """
            INSERT INTO requests (
                request_id,
                user_id,
                type,
                start_date,
                end_date,
                status,
                current_approver_id,
                created_at,
                updated_at,
                deleted_at
            )
            VALUES (
                gen_random_uuid(),
                :user_id,
                :type,
                :start_date,
                :end_date,
                'pending',
                :current_approver_id,
                :created_at,
                :updated_at,
                NULL
            )
            RETURNING request_id
            """
        ),
        {
            "user_id": current_user.user_id,
            "type": payload.type,
            "start_date": start_date,
            "end_date": end_date,
            "current_approver_id": approver_id,
            "created_at": now,
            "updated_at": now,
        },
    ).fetchone()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create request",
        )

    db.commit()

    # Send email and push notification to approver
    if approver_id:
        approver = db.query(User).filter(User.user_id == approver_id).first()
        if approver and approver.email:
            try:
                # Send email notification to approver
                await email_service.send_request_submitted_email(
                    email=approver.email,
                    approver_name=approver.first_name,
                    requester_name=f"{current_user.first_name} {current_user.surname}",
                    request_type=payload.type,
                    start_date=start_date.strftime('%B %d, %Y'),
                    end_date=end_date.strftime('%B %d, %Y') if end_date != start_date else None
                )
                
                # Send push notification if approver has FCM token
                if hasattr(approver, 'fcm_token') and approver.fcm_token:
                    await send_push_notification(
                        token=approver.fcm_token,
                        title="New Request Submitted",
                        body=f"{current_user.first_name} {current_user.surname} submitted a {payload.type} request for your approval",
                        data={
                            "type": "new_request",
                            "request_id": str(result[0]),
                            "requester_name": f"{current_user.first_name} {current_user.surname}"
                        }
                    )
            except Exception as e:
                # Log error but don't fail the request creation
                print(f"Failed to send notification to approver: {e}")

    return {"success": True, "id": str(result[0])}


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
                r.created_at
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
        
        duration = 1
        if end_date and end_date != start_date:
            duration = (end_date - start_date).days + 1
        
        requests.append({
            "id": str(row[0]),
            "type": row[1],
            "date_range": date_range,
            "duration": f"{duration} day{'s' if duration > 1 else ''}",
            "description": f"{row[1]} request for {duration}",
            "created_at": created_at.isoformat() if created_at else None,
            "user_id": str(row[7]),
            "user_name": f"{row[5] or ''} {row[6] or ''}".strip(),
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
                u.user_id
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
                u.user_id
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

        if end_date and end_date != start_date:
            duration_days = (end_date - start_date).days + 1
            duration = f"{duration_days} days"
        else:
            duration = "1 day"

        full_name = f"{row[5] or ''} {row[6] or ''}".strip()

        requests.append(
            {
                "id": str(row[0]),
                "type": row[1],
                "status": row[4],
                "date_range": date_range,
                "duration": duration,
                "user_name": full_name,
                "user_id": str(row[7]),
            }
        )

    return requests


@router.post("/admin/{request_id}/approve")
async def approve_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    comment: Optional[str] = None,
):
    req_row = db.execute(text("SELECT user_id, current_approver_id, type, start_date, end_date FROM requests WHERE request_id = :rid"), {"rid": request_id}).fetchone()
    if not req_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if req_row[1] and str(req_row[1]) != str(current_user.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not current approver")
    # Determine next approver in chain
    user_id = req_row[0]
    rtype = req_row[2]
    sd = req_row[3]
    ed = req_row[4] or req_row[3]
    next_approver_id = None
    # Chain: HOD -> HR Admin -> Accountant -> Principal Hospital Administrator
    # Identify current user's position and pick next by role
    # Simple role-based ordering
    role_name = current_user.role.name if current_user.role else ""
    if role_name and role_name.lower() in ["head of department", "hod"]:
        hr = db.query(User).join(Role).filter(Role.name.in_(["HR Admin", "HR"]), User.deleted_at.is_(None)).first()
        next_approver_id = hr.user_id if hr else None
    elif role_name and role_name.lower() in ["hr admin", "hr"]:
        accountant = db.query(User).join(Role).filter(Role.name == "Accountant", User.deleted_at.is_(None)).first()
        next_approver_id = accountant.user_id if accountant else None
    elif role_name and role_name.lower() == "accountant":
        principal = db.query(User).join(Role).filter(Role.name == "Principal Hospital Administrator", User.deleted_at.is_(None)).first()
        next_approver_id = principal.user_id if principal else None
    else:
        # If initial approver wasn't set or current approver is not in chain, start from HOD
        hod = db.query(User).filter(User.department_id == current_user.department_id, User.is_head_of_department == True, User.deleted_at.is_(None)).first()
        next_approver_id = hod.user_id if hod and hod.user_id != current_user.user_id else None
    result = None
    if next_approver_id:
        result = db.execute(
            text(
                """
                UPDATE requests
                SET current_approver_id = :next_id,
                    updated_at = NOW()
                WHERE request_id = :request_id
                  AND status = 'pending'
                  AND deleted_at IS NULL
                  AND (current_approver_id IS NULL OR current_approver_id = :approver_id)
                RETURNING request_id
                """
            ),
            {"request_id": request_id, "approver_id": current_user.user_id, "next_id": next_approver_id},
        ).fetchone()
    else:
        result = db.execute(
            text(
                """
                UPDATE requests
                SET status = 'approved',
                    current_approver_id = NULL,
                    updated_at = NOW()
                WHERE request_id = :request_id
                  AND status = 'pending'
                  AND deleted_at IS NULL
                  AND (current_approver_id IS NULL OR current_approver_id = :approver_id)
                RETURNING request_id
                """
            ),
            {"request_id": request_id, "approver_id": current_user.user_id},
        ).fetchone()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found or not eligible for approval",
        )

    db.commit()
    # Notify initial approver
    if approver_id:
        db.add(Notification(
            user_id=approver_id,
            title="New Request Pending",
            message=f"{payload.type} requires your approval",
            type="request",
            is_read=False,
            created_at=now,
            updated_at=now
        ))
        db.commit()
        approver_user = db.query(User).filter(User.user_id == approver_id).first()
        if approver_user and approver_user.fcm_tokens:
            for tok in approver_user.fcm_tokens:
                try:
                    await send_push_notification(
                        token=tok.fcm_token,
                        title="New Request Pending",
                        body=f"{payload.type} requires your approval",
                        data={"request_id": str(result[0]), "type": "request"}
                    )
                except Exception:
                    pass
    db.add(RequestApproval(request_id=result[0], approver_id=current_user.user_id, level=1, action="approved", comment=comment, timestamp=datetime.utcnow()))
    db.commit()
    # Notify next approver or finalize
    if next_approver_id:
        # Get requester details for email
        requester = db.query(User).filter(User.user_id == user_id).first()
        
        # Send email and push notification to next approver
        next_user = db.query(User).filter(User.user_id == next_approver_id).first()
        if next_user and next_user.email:
            try:
                # Send email notification to next approver
                await email_service.send_request_reassigned_email(
                    email=next_user.email,
                    new_approver_name=f"{next_user.first_name} {next_user.surname}",
                    requester_name=f"{requester.first_name} {requester.surname}" if requester else "Unknown",
                    request_type=rtype,
                    start_date=sd.strftime('%B %d, %Y'),
                    end_date=ed.strftime('%B %d, %Y') if ed != sd else None,
                    previous_approver_name=f"{current_user.first_name} {current_user.surname}"
                )
                
                # Send push notification if next approver has FCM token
                if hasattr(next_user, 'fcm_token') and next_user.fcm_token:
                    await send_push_notification(
                        token=next_user.fcm_token,
                        title="Request Escalated",
                        body=f"{rtype} request has been escalated to you for approval",
                        data={
                            "type": "request_escalated",
                            "request_id": request_id,
                            "request_type": rtype,
                            "escalated_by": f"{current_user.first_name} {current_user.surname}"
                        }
                    )
            except Exception as e:
                # Log error but don't fail the approval
                print(f"Failed to send escalation notification to next approver: {e}")
        
        db.add(Notification(
            user_id=next_approver_id,
            title="Request Pending Approval",
            message=f"{rtype} requires your approval",
            type="request",
            is_read=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ))
        db.commit()
        next_user = db.query(User).filter(User.user_id == next_approver_id).first()
        if next_user and next_user.fcm_tokens:
            for tok in next_user.fcm_tokens:
                try:
                    await send_push_notification(token=tok.fcm_token, title="Request Pending Approval", body=f"{rtype} requires your approval", data={"request_id": request_id, "type": "request"})
                except Exception:
                    pass
    else:
        duration = (ed - sd).days + 1
        if rtype in ["annual_leave", "compassionate_leave", "maternity", "paternity", "unpaid_leave"]:
            lb = db.query(LeaveBalance).filter(LeaveBalance.user_id == user_id, LeaveBalance.leave_type == rtype).first()
            if not lb:
                lb = LeaveBalance(user_id=user_id, leave_type=rtype, allocated_days=0, bonus_days=0, used_days=0, remaining_days=0)
                db.add(lb)
                db.commit()
                db.refresh(lb)
            lb.used_days = (lb.used_days or 0) + duration
            total = (lb.allocated_days or 0) + (lb.bonus_days or 0)
            lb.remaining_days = max(total - (lb.used_days or 0), 0)
            lb.updated_at = datetime.utcnow()
            db.commit()
        
        # Send email and push notification to requester
        requester = db.query(User).filter(User.user_id == user_id).first()
        if requester and requester.email:
            try:
                # Send email notification to requester
                await email_service.send_request_approved_email(
                    email=requester.email,
                    requester_name=f"{requester.first_name} {requester.surname}",
                    request_type=rtype,
                    start_date=sd.strftime('%B %d, %Y'),
                    end_date=ed.strftime('%B %d, %Y') if ed != sd else None,
                    approver_name=f"{current_user.first_name} {current_user.surname}",
                    comment=comment
                )
                
                # Send push notification if requester has FCM token
                if hasattr(requester, 'fcm_token') and requester.fcm_token:
                    await send_push_notification(
                        token=requester.fcm_token,
                        title="Request Approved",
                        body=f"Your {rtype} request for {duration} day(s) has been approved",
                        data={
                            "type": "request_approved",
                            "request_id": request_id,
                            "request_type": rtype
                        }
                    )
            except Exception as e:
                # Log error but don't fail the approval
                print(f"Failed to send approval notification to requester: {e}")
        
        db.add(Notification(user_id=user_id, title="Request Approved", message=f"{rtype} approved for {duration} day(s)", type="request", is_read=False, created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        db.commit()
        user = db.query(User).filter(User.user_id == user_id).first()
        if user and user.fcm_tokens:
            for tok in user.fcm_tokens:
                try:
                    await send_push_notification(token=tok.fcm_token, title="Request Approved", body=f"{rtype} approved for {duration} day(s)", data={"request_id": request_id, "type": "request"})
                except Exception:
                    pass

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
        
        duration = 1
        if end_date and end_date != start_date:
            duration = (end_date - start_date).days + 1
        
        requests.append({
            "id": str(row[0]),
            "type": row[1],
            "date_range": date_range,
            "duration": f"{duration} day{'s' if duration > 1 else ''}",
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    comment: Optional[str] = None,
):
    result = db.execute(
        text(
            """
            UPDATE requests
            SET status = 'denied',
                updated_at = NOW()
            WHERE request_id = :request_id
              AND status = 'pending'
              AND deleted_at IS NULL
              AND (current_approver_id IS NULL OR current_approver_id = :approver_id)
            RETURNING request_id
            """
        ),
        {"request_id": request_id, "approver_id": current_user.user_id},
    ).fetchone()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found or not eligible for denial",
        )

    db.commit()
    db.add(RequestApproval(request_id=result[0], approver_id=current_user.user_id, level=1, action="denied", comment=comment, timestamp=datetime.utcnow()))
    db.commit()
    req = db.execute(text("SELECT user_id, type, start_date, end_date FROM requests WHERE request_id = :rid"), {"rid": request_id}).fetchone()
    if req:
        uid = req[0]
        rtype = req[1]
        sd = req[2]
        ed = req[3] or req[2]
        
        # Send email and push notification to requester
        requester = db.query(User).filter(User.user_id == uid).first()
        if requester and requester.email:
            try:
                # Send email notification to requester
                await email_service.send_request_denied_email(
                    email=requester.email,
                    requester_name=f"{requester.first_name} {requester.surname}",
                    request_type=rtype,
                    start_date=sd.strftime('%B %d, %Y'),
                    end_date=ed.strftime('%B %d, %Y') if ed != sd else None,
                    approver_name=f"{current_user.first_name} {current_user.surname}",
                    comment=comment
                )
                
                # Send push notification if requester has FCM token
                if hasattr(requester, 'fcm_token') and requester.fcm_token:
                    await send_push_notification(
                        token=requester.fcm_token,
                        title="Request Denied",
                        body=f"Your {rtype} request has been denied",
                        data={
                            "type": "request_denied",
                            "request_id": request_id,
                            "request_type": rtype
                        }
                    )
            except Exception as e:
                # Log error but don't fail the denial
                print(f"Failed to send denial notification to requester: {e}")
        
        n = Notification(user_id=uid, title="Request Denied", message=f"{rtype} denied", type="request", is_read=False, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.add(n)
        db.commit()
        user = db.query(User).filter(User.user_id == uid).first()
        if user and user.fcm_tokens:
            for tok in user.fcm_tokens:
                try:
                    await send_push_notification(token=tok.fcm_token, title="Request Denied", body=f"{rtype} denied", data={"request_id": request_id, "type": "request"})
                except Exception:
                    pass

@router.get("/{request_id}/approvals")
async def get_request_approvals(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.query(RequestApproval).filter(RequestApproval.request_id == request_id).order_by(RequestApproval.timestamp.asc()).all()
    return [{"approval_id": str(r.approval_id), "approver_id": str(r.approver_id), "level": r.level, "action": r.action, "comment": r.comment, "timestamp": r.timestamp.isoformat() if r.timestamp else None} for r in rows]

    return {"success": True}
