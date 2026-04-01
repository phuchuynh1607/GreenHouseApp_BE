from fastapi import APIRouter, HTTPException, status
from typing import List

from sqlalchemy.orm import selectinload

from ..models.feedback_model import FeedbackTicket, FeedbackMessage
from ..schemas.feedback_schema import (
    TicketCreate,
    MessageCreate, TicketResponse
)
from .auth import db_dependency, user_dependency

router = APIRouter(
    prefix='/feedback',
    tags=['feedback']
)


# --- 1. USER: TẠO TICKET MỚI (KÈM TIN NHẮN ĐẦU TIÊN) ---
@router.post("/tickets", status_code=status.HTTP_201_CREATED)
async def create_new_ticket(req: TicketCreate, db: db_dependency, user: user_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # Bước 1: Tạo Ticket (Vỏ bọc)
    new_ticket = FeedbackTicket(
        user_id=user.get('id'),
        subject=req.subject,
        status="pending"
    )
    db.add(new_ticket)
    db.flush()  # flush để lấy ID của ticket vừa tạo mà chưa commit

    # Bước 2: Tạo Message đầu tiên (Nội dung câu hỏi)
    first_message = FeedbackMessage(
        ticket_id=new_ticket.id,
        sender_id=user.get('id'),
        message_content=req.initial_message
    )
    db.add(first_message)
    db.commit()

    return {"message": "Ticket created successfully", "ticket_id": new_ticket.id}


# --- 2. CẢ 2: GỬI THÊM TIN NHẮN VÀO TICKET ĐÃ CÓ ---
@router.post("/tickets/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(ticket_id: int, req: MessageCreate, db: db_dependency, user: user_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    ticket = db.query(FeedbackTicket).filter(FeedbackTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Nếu Admin trả lời, tự động chuyển trạng thái sang "processing"
    if user.get('user_role') == 'admin':
        ticket.status = "processing"

    new_message = FeedbackMessage(
        ticket_id=ticket_id,
        sender_id=user.get('id'),
        message_content=req.message_content
    )
    db.add(new_message)
    db.commit()
    return {"message": "Message sent"}


# --- 3. CẢ 2: LẤY CHI TIẾT 1 TICKET (GỒM TOÀN BỘ TIN NHẮN) ---
@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket_details(ticket_id: int, db: db_dependency, user: user_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    ticket = db.query(FeedbackTicket).filter(FeedbackTicket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Bảo mật: User chỉ được xem ticket của chính mình, Admin xem được hết
    if user.get('user_role') != 'admin' and ticket.user_id != user.get('id'):
        raise HTTPException(status_code=403, detail="Forbidden")

    return ticket


# --- 4. ADMIN: LẤY TẤT CẢ TICKET (ĐỂ QUẢN LÝ) ---
@router.get("/admin/all-tickets")
async def admin_get_all_tickets(db: db_dependency, user: user_dependency):
    # Kiểm tra quyền Admin
    if user.get('user_role') != 'admin':
        raise HTTPException(status_code=403, detail="Admin only")
    # Query lấy dữ liệu kèm Join
    # Dùng selectinload thay vì joinedload nếu có nhiều messages (tránh duplicate rows)
    tickets = db.query(FeedbackTicket) \
        .options(
        selectinload(FeedbackTicket.user),
        selectinload(FeedbackTicket.messages)
    ) \
        .order_by(FeedbackTicket.created_at.desc()) \
        .all()
    result = []
    for t in tickets:
        initial_message = None
        if t.messages:
            sorted_messages = sorted(t.messages, key=lambda x: x.created_at)
            initial_message = sorted_messages[0].message_content
        result.append({
            "id": t.id,
            "user_id": t.user_id,
            "subject": t.subject,
            "status": t.status,
            "created_at": t.created_at,
            "user_name": t.user.username if t.user else "Người dùng ẩn danh",
            "initial_message": initial_message or "Không có nội dung"
        })

    return result


# --- 5. USER: LẤY DANH SÁCH TICKET CỦA TÔI ---
@router.get("/my-tickets")
async def get_my_tickets(db: db_dependency, user: user_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')
    tickets = db.query(FeedbackTicket).options(
        selectinload(FeedbackTicket.messages)
    ).filter(
        FeedbackTicket.user_id == user.get('id')
    ).order_by(FeedbackTicket.created_at.desc()).all()
    result = []
    for ticket in tickets:
        initial_message = None
        if ticket.messages:
            sorted_messages = sorted(ticket.messages, key=lambda x: x.created_at)
            initial_message = sorted_messages[0].message_content
        result.append({
            "id": ticket.id,
            "subject": ticket.subject,
            "status": ticket.status,
            "created_at": ticket.created_at,
            "initial_message": initial_message or "Không có nội dung"
        })

    return result


# --- 6. ADMIN/USER: CẬP NHẬT TRẠNG THÁI TICKET (RESOLVE/CLOSE) ---
@router.patch("/tickets/{ticket_id}/status")
async def update_ticket_status(
        ticket_id: int,
        new_status: str,  # Có thể dùng Enum hoặc Check list: resolved, closed
        db: db_dependency,
        user: user_dependency
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    ticket = db.query(FeedbackTicket).filter(FeedbackTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Kiểm tra quyền:
    # - Admin có quyền chuyển sang bất cứ trạng thái nào.
    # - User có thể có quyền tự 'close' ticket của mình nếu họ thấy đã ok.
    if user.get('user_role') != 'admin' and ticket.user_id != user.get('id'):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Validate trạng thái hợp lệ
    valid_statuses = ["pending", "processing", "resolved", "closed"]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")

    ticket.status = new_status
    db.commit()

    return {"message": f"Ticket status updated to {new_status}"}