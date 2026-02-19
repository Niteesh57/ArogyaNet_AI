from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.api import deps
from app.models.user import User, UserRole
from app.models.event import Event
from app.schemas.event import EventCreate, Event as EventSchema, EventDataAppend, EventUpdate


router = APIRouter()

@router.get("/", response_model=List[EventSchema])
async def read_events(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Retrieve events.
    """
    result = await db.execute(select(Event).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("/", response_model=EventSchema)
async def create_event(
    *,
    db: AsyncSession = Depends(deps.get_db),
    event_in: EventCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Create new event.
    """
    # Any active user can create an event? Or restrict? 
    # User didn't specify creation restriction, only append restriction.
    # Let's allow any authenticated user to create.
    
    event = Event(
        event_name=event_in.event_name,
        json_data=[], # Initialize empty list
        keys=event_in.keys, # Initialize keys
        created_by_id=current_user.id,
        updated_by_id=current_user.id
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event

@router.get("/{event_id}", response_model=EventSchema)
async def get_event(
    *,
    db: AsyncSession = Depends(deps.get_db),
    event_id: str,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get event by ID.
    """
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalars().first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event

@router.patch("/{event_id}/append", response_model=EventSchema)
async def append_event_data(
    *,
    db: AsyncSession = Depends(deps.get_db),
    event_id: str,
    data_in: EventDataAppend,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Append data to event JSON. (NURSE ONLY)
    """
    if current_user.role != UserRole.NURSE.value and current_user.role != UserRole.SUPER_ADMIN.value:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only nurses can append data to events"
        )
        
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalars().first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Append new data
    # We must create a new list to ensure SQLAlchemy detects the change (mutation tracking on JSON is tricky)
    current_data = list(event.json_data) if event.json_data else []
    
    # Add metadata to the append
    new_entry = data_in.data.copy()
    new_entry["_appended_by"] = current_user.id
    new_entry["_appended_at"] = datetime.now(timezone.utc).isoformat()
    
    current_data.append(new_entry)
    
    event.json_data = current_data
    event.updated_by_id = current_user.id
    
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event

@router.put("/{event_id}", response_model=EventSchema)
async def update_event(
    *,
    db: AsyncSession = Depends(deps.get_db),
    event_id: str,
    event_in: EventUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Update an event (Name and Keys/JSON Data).
    """
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalars().first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    # Update fields
    if event_in.event_name is not None:
        event.event_name = event_in.event_name
        
    if event_in.json_data is not None:
        event.json_data = event_in.json_data

    if event_in.keys is not None:
        event.keys = event_in.keys
    event.updated_by_id = current_user.id
    
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event
