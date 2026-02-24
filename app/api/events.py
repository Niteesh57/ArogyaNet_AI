from typing import Any, List, Optional, Set, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.api import deps
from app.models.user import User, UserRole
from app.models.event import Event
from app.schemas.event import EventCreate, Event as EventSchema, EventDataAppend, EventUpdate, EventStatsFilters


router = APIRouter()

@router.get("/stats/filters", response_model=EventStatsFilters)
async def get_event_filters(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get unique filter options (places and keys) for dashboard graphs.
    """
    query = select(Event)
    if current_user.role != UserRole.SUPER_ADMIN.value:
        if current_user.hospital_id:
            query = query.join(User, Event.created_by_id == User.id).filter(User.hospital_id == current_user.hospital_id)
        else:
            query = query.filter(Event.id == "0") # No access
            
    result = await db.execute(query)
    events = result.scalars().all()
    
    unique_places = set()
    all_keys = set()
    
    for event in events:
        if event.keys:
            all_keys.update(event.keys)
        
        if event.json_data:
            for entry in event.json_data:
                place = entry.get("place_name")
                if place:
                    unique_places.add(place)
                    
    return {
        "places": sorted(list(unique_places)),
        "available_keys": sorted(list(all_keys))
    }

@router.get("/stats/graph-data", response_model=List[Dict[str, Any]])
async def get_event_graph_data(
    place_name: Optional[str] = Query(None),
    event_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get detailed entries filtered by place or event for graphical representation.
    """
    query = select(Event)
    if event_id:
        query = query.where(Event.id == event_id)
        
    if current_user.role != UserRole.SUPER_ADMIN.value:
        if current_user.hospital_id:
            query = query.join(User, Event.created_by_id == User.id).filter(User.hospital_id == current_user.hospital_id)
        else:
            query = query.filter(Event.id == "0") # No access
            
    result = await db.execute(query)
    events = result.scalars().all()
    
    filtered_data = []
    for event in events:
        if event.json_data:
            for entry in event.json_data:
                # Apply place filter if provided
                if place_name and entry.get("place_name") != place_name:
                    continue
                
                # Include entry
                entry_copy = entry.copy()
                entry_copy["_event_name"] = event.event_name
                entry_copy["_event_id"] = event.id
                filtered_data.append(entry_copy)
                
    return filtered_data

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
    query = select(Event)
    if current_user.role != UserRole.SUPER_ADMIN.value:
        if current_user.hospital_id:
            query = query.join(User, Event.created_by_id == User.id).filter(User.hospital_id == current_user.hospital_id)
        else:
            query = query.filter(Event.id == "0") # No access
            
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
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
