"""
Doctor Tools for AI Agent
Provides functions to retrieve doctor information, availability, and booked appointments.
"""
from typing import List, Dict, Any
from datetime import datetime, date, time, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.doctor import Doctor
from app.models.user import User
from app.models.availability import Availability
from app.models.appointment import Appointment


async def get_doctors_with_availability(
    hospital_id: str,
    db: AsyncSession,
    target_date: date = None
) -> List[Dict[str, Any]]:
    """
    Get list of doctors from a hospital with their availability and booked slots.
    
    Args:
        hospital_id: The hospital ID to filter doctors
        db: Database session
        target_date: Date to check availability (defaults to today)
    
    Returns:
        List of dictionaries containing:
        - doctor_id: Doctor's ID
        - name: Doctor's full name
        - specialization: Doctor's specialization
        - experience_years: Years of experience
        - availability: List of available time slots for the day
        - booked_slots: List of already booked appointment slots for today
        - available_slots: Slots that are available (not booked)
    """
    if target_date is None:
        target_date = date.today()
    
    # Get day of week (monday, tuesday, etc.)
    day_name = target_date.strftime("%A").lower()
    
    # Query doctors from the hospital
    doctor_query = select(Doctor, User).join(
        User, Doctor.user_id == User.id
    ).filter(
        Doctor.hospital_id == hospital_id,
        Doctor.is_available == True
    )
    
    result = await db.execute(doctor_query)
    doctors_data = result.all()
    
    doctors_list = []
    
    for doctor, user in doctors_data:
        # Get availability for this day
        # Note: We need to handle potential multiple availability records (e.g. split shifts)
        availability_query = select(Availability).filter(
            and_(
                Availability.staff_type == "doctor",
                Availability.staff_id == doctor.id,
                Availability.day_of_week == day_name
            )
        )
        availability_result = await db.execute(availability_query)
        availabilities = availability_result.scalars().all()
        
        # If doctor has no availability defined for this day, skip them
        if not availabilities:
            continue
            
        # Get booked appointments for today
        appointments_query = select(Appointment).filter(
            and_(
                Appointment.doctor_id == doctor.id,
                Appointment.date == target_date
            )
        )
        appointments_result = await db.execute(appointments_query)
        booked_appointments = appointments_result.scalars().all()
        
        # Extract booked slots
        booked_slots = set(apt.slot for apt in booked_appointments)
        
        # Generate available time slots based on availability
        available_time_slots = []
        for avail in availabilities:
            slots = generate_time_slots(avail.start_time, avail.end_time)
            available_time_slots.extend(slots)
            
        # Remove duplicates if any (e.g. overlapping availability)
        available_time_slots = sorted(list(set(available_time_slots)))
        
        # Filter out booked slots
        free_slots = [slot for slot in available_time_slots if slot not in booked_slots]
        
        # If doctor has no free slots, skip them (AI shouldn't suggest fully booked doctors)
        if not free_slots:
            continue
        
        doctor_info = {
            "doctor_id": doctor.id,
            "name": user.full_name,
            "specialization": doctor.specialization,
            "experience_years": doctor.experience_years,
            "available_slots": free_slots, # Only send available slots to AI
            "free_count": len(free_slots)
        }
        
        doctors_list.append(doctor_info)
    
    return doctors_list


def generate_time_slots(start_time: time, end_time: time, slot_duration: int = 30) -> List[str]:
    """
    Generate time slots between start and end time.
    
    Args:
        start_time: Start time
        end_time: End time
        slot_duration: Duration of each slot in minutes (default: 30)
    
    Returns:
        List of time slots as strings (e.g., ["10:00", "10:30", "11:00"])
    """
    slots = []
    current_time = datetime.combine(date.today(), start_time)
    end_datetime = datetime.combine(date.today(), end_time)
    
    while current_time < end_datetime:
        slots.append(current_time.strftime("%H:%M"))
        current_time += timedelta(minutes=slot_duration)
    
    return slots


async def get_doctor_by_id(
    doctor_id: str,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get detailed information about a specific doctor.
    
    Args:
        doctor_id: The doctor's ID
        db: Database session
    
    Returns:
        Dictionary with doctor details
    """
    query = select(Doctor, User).join(
        User, Doctor.user_id == User.id
    ).filter(Doctor.id == doctor_id)
    
    result = await db.execute(query)
    doctor_data = result.first()
    
    if not doctor_data:
        return None
    
    doctor, user = doctor_data
    
    return {
        "doctor_id": doctor.id,
        "name": user.full_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "specialization": doctor.specialization,
        "license_number": doctor.license_number,
        "experience_years": doctor.experience_years,
        "tags": doctor.tags,
        "is_available": doctor.is_available,
        "hospital_id": doctor.hospital_id
    }


async def check_doctor_slot_availability(
    doctor_id: str,
    appointment_date: date,
    slot: str,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Check if a specific slot is available for a doctor on a given date.
    
    Args:
        doctor_id: The doctor's ID
        appointment_date: Date of the appointment
        slot: Time slot (e.g., "10:30")
        db: Database session
    
    Returns:
        Dictionary with availability status
    """
    # Check if slot is already booked
    query = select(Appointment).filter(
        and_(
            Appointment.doctor_id == doctor_id,
            Appointment.date == appointment_date,
            Appointment.slot == slot
        )
    )
    
    result = await db.execute(query)
    existing_appointment = result.first()
    
    is_available = existing_appointment is None
    
    return {
        "doctor_id": doctor_id,
        "date": appointment_date.isoformat(),
        "slot": slot,
        "is_available": is_available,
        "message": "Slot is available" if is_available else "Slot is already booked"
    }
