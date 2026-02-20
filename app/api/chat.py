from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from jose import jwt, JWTError
import json

from app.api import deps
from app.models.user import User, UserRole
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.crud.doctor_patient_chat import chat as crud_chat
from app.schemas.doctor_patient_chat import ChatMessageResponse, ChatContact, ChatMessageCreate
from app.core import security
from app.core.config import settings

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: str):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except:
                    pass

manager = ConnectionManager()

async def get_ws_user(token: str, db: AsyncSession) -> User | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
    except JWTError:
        return None
    from app.crud.user import user as crud_user
    user = await crud_user.get(db, id=user_id_str)
    return user

@router.websocket("/ws")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(deps.get_db)
):
    user = await get_ws_user(token, db)
    if not user:
        await websocket.close(code=1008) # Policy violation
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            receiver_id = message_data.get("receiver_id")
            message_text = message_data.get("message")
            
            if receiver_id and message_text:
                from app.models.doctor_patient_chat import DoctorPatientChat
                new_msg = DoctorPatientChat(
                    sender_id=user.id,
                    receiver_id=receiver_id,
                    message=message_text
                )
                db.add(new_msg)
                await db.commit()
                await db.refresh(new_msg)

                msg_response = {
                    "id": new_msg.id,
                    "sender_id": new_msg.sender_id,
                    "receiver_id": new_msg.receiver_id,
                    "message": new_msg.message,
                    "is_read": new_msg.is_read,
                    "created_at": new_msg.created_at.isoformat()
                }

                # Send strictly to receiver
                await manager.send_personal_message(msg_response, receiver_id)
                
                # Send back to sender to confirm receipt formatting
                await manager.send_personal_message(msg_response, user.id)
                
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)
    except Exception as e:
        manager.disconnect(user.id, websocket)


@router.get("/history/{contact_id}", response_model=List[ChatMessageResponse])
async def get_history(
    contact_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 100
) -> Any:
    # Authorization checks can be added here to guarantee they have an appointment
    messages = await crud_chat.get_chat_history(
        db, user1_id=current_user.id, user2_id=contact_id, skip=skip, limit=limit
    )
    return messages

@router.get("/contacts", response_model=List[ChatContact])
async def get_contacts(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    """
    Returns the list of specific contacts the user is allowed to chat with.
    Patients get doctors they booked. Doctors get patients who booked them.
    """
    contacts = []
    contact_user_ids = set()
    
    if current_user.role == UserRole.PATIENT:
        # Get patient profile
        query_patient = select(Patient).where(Patient.user_id == current_user.id)
        res_patient = await db.execute(query_patient)
        patient = res_patient.scalars().first()
        if patient:
            query_appts = select(Appointment).where(Appointment.patient_id == patient.id)
            res_appts = await db.execute(query_appts)
            appts = res_appts.scalars().all()
            
            doc_ids = list(set([a.doctor_id for a in appts]))
            if doc_ids:
                query_docs = select(Doctor).where(Doctor.id.in_(doc_ids))
                res_docs = await db.execute(query_docs)
                doctors = res_docs.scalars().all()
                for doc in doctors:
                    if doc.user_id:
                        contact_user_ids.add(doc.user_id)
                        
    elif current_user.role == UserRole.DOCTOR:
        # Get doctor profile
        query_doc = select(Doctor).where(Doctor.user_id == current_user.id)
        res_doc = await db.execute(query_doc)
        doctor = res_doc.scalars().first()
        if doctor:
            query_appts = select(Appointment).where(Appointment.doctor_id == doctor.id)
            res_appts = await db.execute(query_appts)
            appts = res_appts.scalars().all()
            
            pat_ids = list(set([a.patient_id for a in appts]))
            if pat_ids:
                query_pats = select(Patient).where(Patient.id.in_(pat_ids))
                res_pats = await db.execute(query_pats)
                patients = res_pats.scalars().all()
                for pat in patients:
                    if pat.user_id:
                        contact_user_ids.add(pat.user_id)
                        
    # For now, admins might see everyone or no one. Let's keep it empty for admin for simple MVP

    from app.models.hospital import Hospital
    
    if contact_user_ids:
        query_users = select(User).where(User.id.in_(list(contact_user_ids)))
        res_users = await db.execute(query_users)
        users = res_users.scalars().all()
        
        for u in users:
            # Check last message
            last_msg = await crud_chat.get_last_message(db, user1_id=current_user.id, user2_id=u.id)
            
            # Additional logic to fetch specialization / hospital if doctor
            specialization = None
            h_name = None
            if u.role == UserRole.DOCTOR:
                q_d = select(Doctor).where(Doctor.user_id == u.id)
                d_obj = (await db.execute(q_d)).scalars().first()
                if d_obj:
                    specialization = d_obj.specialization
                    if d_obj.hospital_id:
                        h = await db.get(Hospital, d_obj.hospital_id)
                        h_name = h.name if h else None
            
            contacts.append({
                "id": u.id,
                "full_name": u.full_name or "Unknown User",
                "role": u.role,
                "image": u.image,
                "hospital_name": h_name,
                "specialization": specialization,
                "last_message": last_msg
            })
            
    return contacts
