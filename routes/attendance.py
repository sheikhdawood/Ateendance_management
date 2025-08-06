from fastapi import APIRouter, HTTPException, Query, UploadFile, Form, File, Body
from models.schemas import AttendanceUpdate, UpdateWorkingDays, LeaveRequest, LeaveAction, AttendanceQuery, CreateTeamRequest, UpdateTeamMembersRequest
from datetime import datetime
from Ateendance_management.functions import haversine_distance, save_image, get_current_ist_time, calculate_stats, clean_mongo_doc, extract_time, send_email, format_time, format_time_stat
import os
from typing import Optional
from datetime import datetime, date, timedelta, time
import io
from fastapi.responses import StreamingResponse
from bson import ObjectId
import csv
from io import StringIO
from config.db import employee_collection, attendance_collection, teams_collection
from pytz import timezone
from pymongo import DESCENDING
import math
import pytz
import bcrypt
from dateutil import parser
import logging
from Ateendance_management.functions import is_late
from utils.auth1 import get_current_user
from fastapi import Depends
from utils.auth1 import get_current_user
from collections import defaultdict
from fastapi import Query
from typing import Optional
from datetime import date, datetime
from pymongo import DESCENDING
from fastapi import Query
from math import ceil
from collections import defaultdict
from fastapi import Query
from typing import Optional
from datetime import datetime, date
from models.schemas import LeaveResponse  # Import your Pydantic model
from fastapi import Query
from typing import List, Optional, Literal
from models.schemas import FeedbackInput
from config.db import feedback_collection
from fastapi import APIRouter, Query, HTTPException
from fastapi import status
from datetime import datetime, time
from pytz import timezone, utc
import os
from bson.objectid import ObjectId


 # Replace with your actual DB imports


# Default annual leave quota for each type
LEAVE_QUOTA = {
    "casual": 12,
    "Sick/Personal": 8,
    "earned": 10,
    "bereavement": 3,
    "festival": 5,
    "compensatory_festival": 3
}




router = APIRouter(
    #prefix="/secure",
   # dependencies=[Depends(get_current_user)]
)


IST = timezone("Asia/Kolkata")

@router.post("/log-arrival/")
async def log_arrival(
    Email: str = Form(...),
    date_str: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    photo: UploadFile = File(...),
):
    user = employee_collection.find_one({"Email": Email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    is_hybrid = user.get("is_hybrid", False)
    user_role = user.get("role", "user")
    location_override = user.get("location_override", False)

    if user_role.lower() != "admin" and not location_override:
        from Ateendance_management.functions import is_within_allowed_location
        if not is_within_allowed_location(latitude, longitude):
            raise HTTPException(status_code=403, detail="Access denied: Outside allowed location")

    try:
        naive_date = datetime.strptime(date_str, "%Y-%m-%d")
        date_parsed = datetime.combine(naive_date.date(), time.min)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    now_ist = datetime.now(IST)
    arrival_time_str = now_ist.strftime("%I:%M:%S %p %Z")

    os.makedirs("photo_arrival", exist_ok=True)
    timestamp = now_ist.strftime("%Y%m%d_%H%M%S")
    filename = f"{Email}_{timestamp}.png"
    file_path = os.path.join("photo_arrival", filename)
    with open(file_path, "wb") as f:
        f.write(await photo.read())

    attendance_record = attendance_collection.find_one({
        "email": Email.lower(),
        "date": date_parsed
    })

    if attendance_record:
        if is_hybrid:
            # Append to multiple_logs
            attendance_collection.update_one(
                {"_id": attendance_record["_id"]},
                {"$push": {"multiple_logs": {
                    "arrival_time": arrival_time_str,
                    "arrival_photo": file_path,
                    "latitude": latitude,
                    "longitude": longitude,
                    "leaving_time": None,
                    "leaving_photo": None,
                    "hours_present": None
                }}}
            )
        else:
            if attendance_record.get("is_submitted", False):
                raise HTTPException(status_code=400, detail="Attendance already marked as submitted.")
            attendance_collection.update_one(
                {"_id": attendance_record["_id"]},
                {"$set": {
                    "arrival_time": arrival_time_str,
                    "photo_path": file_path,
                    "is_submitted": True
                }}
            )
    else:
        new_record = {
            "email": Email.lower(),
            "date": date_parsed,
            "is_hybrid": is_hybrid,
            "is_submitted": True
        }

        if is_hybrid:
            new_record["multiple_logs"] = [{
                "arrival_time": arrival_time_str,
                "arrival_photo": file_path,
                "latitude": latitude,
                "longitude": longitude,
                "leaving_time": None,
                "leaving_photo": None,
                "hours_present": None
            }]
        else:
            new_record["arrival_time"] = arrival_time_str
            new_record["photo_path"] = file_path

        attendance_collection.insert_one(new_record)

    return {
        "message": "Arrival logged successfully",
        "arrival_time": arrival_time_str,
        "email": Email,
        "date": date_parsed.strftime("%Y-%m-%d"),
        "is_hybrid": is_hybrid,
        "is_submitted": True
    }

@router.post("/log-leaving/")
async def log_leaving(
    email: str = Form(...),
    date: date = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    photo: UploadFile = File(...)
):
    if not email or not date:
        raise HTTPException(status_code=400, detail="Email and Date are required.")

    start_datetime = datetime.combine(date, time.min)
    user = employee_collection.find_one({"Email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    is_hybrid = user.get("is_hybrid", False)
    user_role = user.get("role", "user")
    location_override = user.get("location_override", False)

    if user_role.lower() != "admin" and not location_override:
        from Ateendance_management.functions import is_within_allowed_location
        if not is_within_allowed_location(latitude, longitude):
            raise HTTPException(status_code=403, detail="Access denied: Outside allowed location")

    record = attendance_collection.find_one({
        "email": email,
        "date": start_datetime
    })

    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    now_ist = datetime.now(IST)
    leaving_time_str = now_ist.strftime("%I:%M:%S %p %Z")

    os.makedirs("photo_leaving", exist_ok=True)
    timestamp = now_ist.strftime("%Y%m%d_%H%M%S")
    filename = f"{email}_{timestamp}_leaving.png"
    file_path = os.path.join("photo_leaving", filename)
    with open(file_path, "wb") as f:
        f.write(await photo.read())

    if is_hybrid:
        logs = record.get("multiple_logs", [])
        for i in reversed(range(len(logs))):
            if logs[i].get("leaving_time") is None:
                arrival_time_str = logs[i].get("arrival_time")
                try:
                    parsed_arrival = datetime.strptime(arrival_time_str.replace(" IST", "").strip(), "%I:%M:%S %p")
                    arrival_dt = datetime.combine(date, parsed_arrival.time())
                    arrival_dt = IST.localize(arrival_dt)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"arrival_time parse error: {e}")

                hours_present = round((now_ist - arrival_dt).total_seconds() / 3600, 2)

                attendance_collection.update_one(
                    {"_id": record["_id"]},
                    {
                        "$set": {
                            f"multiple_logs.{i}.leaving_time": leaving_time_str,
                            f"multiple_logs.{i}.leaving_photo": file_path,
                            f"multiple_logs.{i}.hours_present": hours_present
                        }
                    }
                )
                break
        else:
            raise HTTPException(status_code=400, detail="No open arrival found to pair with leaving.")
    else:
        arrival_time_str = record.get("arrival_time")
        if not arrival_time_str:
            raise HTTPException(status_code=500, detail="Missing arrival_time")

        try:
            parsed_arrival = datetime.strptime(arrival_time_str.replace(" IST", "").strip(), "%I:%M:%S %p")
            arrival_dt = datetime.combine(date, parsed_arrival.time())
            arrival_dt = IST.localize(arrival_dt)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"arrival_time parse error: {e}")

        hours_present = round((now_ist - arrival_dt).total_seconds() / 3600, 2)

        update_fields = {
            "leaving_time": leaving_time_str,
            "hours_present": hours_present,
            "leaving_photo": file_path,
            "is_submitted": False
        }

        # ensure keys exist in DB
        attendance_collection.update_one(
            {"_id": record["_id"]},
            {"$set": update_fields}
        )


    return {
        "message": "Leaving time logged successfully",
        "email": email,
        "date": date.strftime("%Y-%m-%d"),
        "leaving_time": leaving_time_str,
        "is_hybrid": is_hybrid,
        "is_submitted": False
    }

@router.put("/update-attendance/")
async def update_attendance(data: AttendanceUpdate):
    email = data.Email.lower()
    
    if not data.date:
        raise HTTPException(status_code=400, detail="Date is required to update attendance")

    date_start = datetime.combine(data.date, datetime.min.time())

    # Step 1: Validate employee exists

    employee = employee_collection.find_one({"Email": email})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")


    # Prevent future updates
    if date_start > datetime.now():
        raise HTTPException(status_code=400, detail="Cannot update future attendance")

    # Check working day
    weekday = date_start.strftime("%A")
    working_days = employee.get("working_days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
    if weekday not in working_days:
        return {"message": f"{weekday} is not a working day", "updated": False}

    # Setup
    update_data = {}
    audit_log = {}

    from Ateendance_management.functions import parse_datetime

    arrival = parse_datetime(data.arrival_time)
    leaving = parse_datetime(data.leaving_time)


    # Save raw times if provided
    if arrival:
        update_data["arrival_time"] = arrival
        audit_log["arrival_time"] = arrival.isoformat()

    if leaving:
        update_data["leaving_time"] = leaving
        audit_log["leaving_time"] = leaving.isoformat()

    # Recalculate hours if both times
    if arrival and leaving:
        duration = leaving - arrival
        hours = round(duration.total_seconds() / 3600, 2)
        update_data["hours_present"] = hours
        audit_log["hours_present"] = hours

        # Remove leave if attendance exists
        update_data["leave_status"] = None
        update_data["leave_type"] = None
    elif data.hours_present is not None:
        update_data["hours_present"] = data.hours_present
        audit_log["hours_present"] = data.hours_present

    # Late calculation
    if arrival:
        late_cutoff = time(9, 15)
        update_data["is_late"] = arrival.time() > late_cutoff
        audit_log["is_late"] = update_data["is_late"]

    # Handle optional leave fields
    if data.leave_type:
        update_data["leave_type"] = data.leave_type.lower()
        audit_log["leave_type"] = update_data["leave_type"]
    if data.leave_status:
        update_data["leave_status"] = data.leave_status.lower()
        audit_log["leave_status"] = update_data["leave_status"]
    if data.reason:
        update_data["reason"] = data.reason
        audit_log["reason"] = data.reason
    if data.half_day_time:
        update_data["half_day_time"] = data.half_day_time
        audit_log["half_day_time"] = data.half_day_time
    if data.is_compensatory is not None:
        update_data["is_compensatory"] = data.is_compensatory
        audit_log["is_compensatory"] = data.is_compensatory
    if data.leave_duration:
        update_data["leave_duration"] = data.leave_duration
        audit_log["leave_duration"] = data.leave_duration

    # Special handling for leave
    if data.leave_type and data.leave_duration == "full_day":
        update_data["arrival_time"] = None
        update_data["leaving_time"] = None
        update_data["hours_present"] = 0
        update_data["status_reason"] = "on_leave"
    elif data.leave_type and data.leave_duration in ["first_half", "second_half"]:
        update_data["hours_present"] = 4
        if data.leave_duration == "first_half":
            update_data["arrival_time"] = None
        elif data.leave_duration == "second_half":
            update_data["leaving_time"] = None

    if not update_data:
        raise HTTPException(status_code=400, detail="No valid update fields provided")

    # Update Mongo
    # Step 2: Disallow future date updates
    if date_start > datetime.now():
        raise HTTPException(
            status_code=400,
            detail="Cannot update future attendance records."
        )

    # Step 3: Check if it's a working day
    working_days = employee.get("working_days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
    if date_start.strftime("%A") not in working_days:
        return {
            "message": "Not a working day for this employee",
            "updated": False
        }

    # Step 4: Collect update fields
    update_data = {}

    if data.arrival_time:
        update_data["arrival_time"] = data.arrival_time.strftime("%H:%M:%S")
    if data.leaving_time:
        update_data["leaving_time"] = data.leaving_time.strftime("%H:%M:%S")
    if data.hours_present is not None:
        update_data["hours_present"] = data.hours_present
    # 🆕 Leave-related fields
    if data.leave_type:
        update_data["leave_type"] = data.leave_type.lower()
    if data.leave_status:
        update_data["leave_status"] = data.leave_status.lower()
    if data.reason:
        update_data["reason"] = data.reason
    if data.half_day_time:
        update_data["half_day_time"] = data.half_day_time
    if data.is_compensatory is not None:
        update_data["is_compensatory"] = data.is_compensatory
    if data.leave_duration:
        update_data["leave_duration"] = data.leave_duration

    if not update_data:
        raise HTTPException(status_code=400, detail="No attendance data provided to update.")
    
    existing_structured_leave = attendance_collection.find_one({
         "email": email,
         "start_date": date_start,
         "end_date": date_start,
         "leave_status": "approved"
         })
    if existing_structured_leave:
        # Don't overwrite attendance leave_type/leave_status if already approved
        update_data.pop("leave_status", None)
        update_data.pop("leave_type", None)

    # Step 5: Update attendance record

    attendance_collection.update_one(
        {"email": email, "date": date_start},
        {"$set": update_data},
        upsert=True
    )    

    # Audit Logging
    attendance_collection_log = getattr(globals().get("db", {}), "attendance_logs", attendance_collection)
    attendance_collection_log.insert_one({
        "email": email,
        "date": date_start,
        "changes": audit_log,
        "updated_by": employee["Email"],
        "timestamp": datetime.now()
    })

    return {
        "message": "Attendance updated successfully",
        "updated": True,
        "fields": audit_log
    }
    return {
        "message": "Attendance record updated or created successfully",
        "updated": True,
        **update_data

    }
@router.get("/attendance-stats/")
async def get_attendance_stats(
    Email: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sort_by: Optional[str] = Query(None, description="Sort by: name, days, hours"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    
):
    today = datetime.utcnow().date()
    first_day_of_month = today.replace(day=1)

    if not start_date:
        start_date = first_day_of_month
    if not end_date:
        end_date = today

    date_query = {
        "date": {
            "$gte": datetime.combine(start_date, datetime.min.time()),
            "$lte": datetime.combine(end_date, datetime.max.time())
        }
    }

    # Fetch employees
    employee_cursor = employee_collection.find({"Email": Email}) if Email else employee_collection.find()
    employee_docs = list(employee_cursor)
    total_employees = len(employee_docs)

    employee_stats_list = []
    total_leaves = 0
    total_present_days = 0
    total_working_hours = 0.0
    absent_days = 0

    for emp in employee_docs:
        if not emp or not isinstance(emp, dict):
            continue

        emp_email = emp.get("Email")
        if not emp_email:
            continue

        query = {"email": emp_email}
        query.update(date_query)

        attendance_records = list(attendance_collection.find(query))
        stats = calculate_stats(attendance_records) if attendance_records else {
            "total_days_present": 0,
            "leaves_taken": 0,
            "days_absent": 0,
            "total_hours_worked": 0.0
        }

        total_leaves += stats["leaves_taken"]
        total_present_days += stats["total_days_present"]
        total_working_hours += stats["total_hours_worked"]
        absent_days += stats["days_absent"] 


        stats.update({
            "Email": emp.get("Email"),
            "First_name": emp.get("First_name"),
            "Last_name": emp.get("Last_name"),
            "Employee_ID": emp.get("Employee_ID"),
            "location_override": emp.get("location_override"),
            "is_hybrid": emp.get("is_hybrid"),
            "working_days": emp.get("working_days") or [
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
            ]
        })

        employee_stats_list.append(stats)

    # Apply sorting based on sort_by param
    if not Email:
        if sort_by == "name":
            employee_stats_list.sort(key=lambda x: x.get("First_name", "").lower())
        elif sort_by == "days":
            employee_stats_list.sort(key=lambda x: -x.get("total_days_present", 0))
        elif sort_by == "hours":
            employee_stats_list.sort(key=lambda x: -x.get("total_hours_worked", 0.0))

    # Pagination
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    paginated_stats = employee_stats_list[start_index:end_index]

    return {
        "summary_stats": {
            "total_employees": total_employees,
            "total_leaves": total_leaves,
            "total_present_days": total_present_days,
            "total_working_hours": round(total_working_hours, 2),
            "days_absent": absent_days
        },
        "employees": paginated_stats,
        "pagination": {
            "total_count": total_employees,
            "page": page,
            "page_size": page_size,
            "total_pages": math.ceil(total_employees / page_size)
        }
    }

def get_weekday_name(date_obj):
    if date_obj:
        if isinstance(date_obj, str):
            date_obj = datetime.fromisoformat(date_obj)
        return date_obj.strftime("%A")
    return "Unknown"


def extract_time(date_obj):
    if not date_obj:
        return ""
    try:
        if isinstance(date_obj, str):
            date_obj = datetime.fromisoformat(date_obj)
        return date_obj.strftime("%H:%M:%S")
    except Exception:
        return ""



@router.get("/export-attendance/")
async def export_attendance(
    Email: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
  
):
    query = {}

    if Email:
        query["email"] = Email

    if start_date and end_date:
        query["date"] = {
            "$gte": datetime.combine(start_date, datetime.min.time()),
            "$lte": datetime.combine(end_date, datetime.max.time())
        }

    records = list(attendance_collection.find(query))
    if not records:
        raise HTTPException(status_code=404, detail="No attendance records found")

    emails = {record.get("email") for record in records if record.get("email")}
    employees = employee_collection.find({"Email": {"$in": list(emails)}})
    email_to_employee = {
        emp.get("Email"): emp for emp in employees if emp.get("Email")
    }

    final_records = []

    for record in records:
        email = record.get("email")
        employee = email_to_employee.get(email)
        leave_status = (record.get("leave_status") or "").strip().lower()

        # Handle multi-day leave expansion
        if leave_status and record.get("start_date") and record.get("end_date"):
            start_leave = record["start_date"]
            end_leave = record["end_date"]

            if isinstance(start_leave, str):
                start_leave = datetime.fromisoformat(start_leave)
            if isinstance(end_leave, str):
                end_leave = datetime.fromisoformat(end_leave)

            days_count = (end_leave.date() - start_leave.date()).days + 1
            for day_offset in range(days_count):
                leave_date = start_leave.date() + timedelta(days=day_offset)
                weekday_name = get_weekday_name(leave_date)
                working_days = employee.get("working_days", []) if employee else []
                is_working_day = weekday_name.lower() in [wd.lower() for wd in working_days]

                status = "Leave" if leave_status == "approved" else (
                    "Present" if is_working_day and record.get("arrival_time") and record.get("leaving_time")
                    else "Absent" if is_working_day
                    else "Off Day"
                )

                final_records.append({
                    "_id": str(record.get("_id", "")),
                    "email": email,
                    "First_name": employee.get("First_name", "Unknown") if employee else "Unknown",
                    "Last_name": employee.get("Last_name", "Unknown") if employee else "Unknown",
                    "date": leave_date.strftime("%Y-%m-%d"),
                    "arrival_time": "",
                    "leaving_time": "",
                    "hours_present": "",
                    "Employee-ID": employee.get("Employee_ID", "Unknown") if employee else "Unknown",
                    "Attandence_status": status
                })

        else:
            # Handle single day attendance
            date_obj = record.get("date")
            arrival_time = record.get("arrival_time")
            leaving_time = record.get("leaving_time")

            if isinstance(date_obj, str):
                try:
                    date_obj = datetime.fromisoformat(date_obj)
                except Exception:
                    date_str = "Unknown"
                else:
                    date_str = date_obj.strftime("%Y-%m-%d")
            elif isinstance(date_obj, datetime):
                date_str = date_obj.strftime("%Y-%m-%d")
            else:
                date_str = "Unknown"

            weekday_name = get_weekday_name(date_obj)
            working_days = employee.get("working_days", []) if employee else []
            is_working_day = weekday_name.lower() in [wd.lower() for wd in working_days]

            # 🔧 FIXED LOGIC: Always set `status`
            if leave_status == "approved":
                status = "Leave"
            elif leave_status in ["pending", "rejected"]:
                if is_working_day:
                    if arrival_time and leaving_time:
                        status = "Present"
                    else:
                        status = "Absent"
                else:
                    status = "Off Day"
            else:
                if is_working_day:
                    if arrival_time and leaving_time:
                        status = "Present"
                    else:
                        status = "Absent"
                else:
                    status = "Off Day"

            final_records.append({
                "_id": str(record.get("_id", "")),
                "email": email,
                "First_name": employee.get("First_name", "Unknown") if employee else "Unknown",
                "Last_name": employee.get("Last_name", "Unknown") if employee else "Unknown",
                "date": date_str,
                "arrival_time": extract_time(arrival_time),
                "leaving_time": extract_time(leaving_time),
                "hours_present": record.get("hours_present", ""),
                "Employee-ID": employee.get("Employee_ID", "Unknown") if employee else "Unknown",
                "Attandence_status": status
            })

    # Generate CSV
    output = StringIO()
    fieldnames = [
        "_id", "email", "First_name", "Last_name", "date",
        "arrival_time", "leaving_time", "hours_present", "Employee-ID", "Attandence_status"
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(final_records)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance_records.csv"}
    )


@router.get("/employees/names/")
def get_employee_names(Email: str = Query(None)):
    
    query = {}
    if Email:
        query["Email"] = Email

    try:
        employees_cursor = employee_collection.find(query, {"_id": 0, "Email": 1})
        employees = list(employees_cursor)
        return {"employee_names": employees}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/change-password/")
async def change_password(email: str = Form(...), old_password: str = Form(...), new_password: str = Form(...)):
    user = employee_collection.find_one({"Email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not bcrypt.checkpw(old_password.encode('utf-8'), user["Password"].encode('utf-8')):
        raise HTTPException(status_code=403, detail="Incorrect current password")

    # Hash new password
    hashed_new_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

    # Update the password in the database
    employee_collection.update_one(
        {"Email": email},
        {"$set": {"Password": hashed_new_password}}
    )

    return {"message": "Password changed successfully"}

@router.put("/update-working-days/")
async def update_working_days(data: UpdateWorkingDays):
    
    email = data.Email.lower()

    # Step 1: Check if employee exists
    employee = employee_collection.find_one({"Email": email})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Step 2: Update working_days
    result = employee_collection.update_one(
        {"Email": email},
        {"$set": {"working_days": data.workingDays}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update working days")

    # Step 3: Fetch updated employee
    updated_employee = employee_collection.find_one({"Email": email})

    return {
        "message": "Working days updated successfully",
        "updated_employee": {
            "email": updated_employee["Email"],
            "working_days": updated_employee.get("working_days", [])
        }
    }

# Endpoint to handle leave request submissions
@router.post("/request-leaves")
async def request_leave(data: LeaveRequest):
    print("Leave type accepted:", data.leave_type)

    # 1️⃣ Set defaults and normalize
    start_date = data.start_date or date.today()
    end_date = data.end_date or date.today()
    leave_type = data.leave_type.lower() if data.leave_type else "casual"
    total_days = (end_date - start_date).days + 1

    # 2️⃣ Validate employee
    employee = employee_collection.find_one({"Email": data.email})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    manager = employee_collection.find_one({"Email": data.manager_email})
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    # 3️⃣ Leave quota check (skip if compensatory)
    skip_quota = leave_type in ["festival", "compensatory_festival"] and data.is_compensatory
    if not skip_quota:
        approved_leaves = attendance_collection.count_documents({
            "email": data.email,
            "leave_status": "approved",
            "leave_type": leave_type
        })
        quota = LEAVE_QUOTA.get(leave_type, 0)
        remaining = quota - approved_leaves
        if remaining < total_days:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient {leave_type} leave balance. Requested: {total_days}, Remaining: {remaining}"
            )

    # 4️⃣ Half-day formatting
    half_day_str = "No"
    half_day_start_time = None
    half_day_end_time = None
    if data.half_day_time == "first_half":
        half_day_str = "First Half (09:00 AM - 01:00 PM)"
        half_day_start_time = time(9, 0)
        half_day_end_time = time(13, 0)
    elif data.half_day_time == "second_half":
        half_day_str = "Second Half (01:00 PM - 06:00 PM)"
        half_day_start_time = time(13, 0)
        half_day_end_time = time(18, 0)

    # 5️⃣ Email notification
    subject = f"[{leave_type.title()} Leave] Request from {data.email}"
    message = f"""
Leave Request:
- From: {data.email}
- To: {data.manager_email}
- Leave Type: {leave_type}
- Dates: {start_date} to {end_date}
- Half Day: {half_day_str}
- Reason: {data.reason}
- Compensatory: {'Yes' if data.is_compensatory else 'No'}
"""
    for recipient in [data.manager_email, employee.get("Email")]:
        send_email(subject, message, recipient)

    # 6️⃣ ✅ Insert **one record** instead of per day
    leave_doc = {
        "email": data.email,
        "manager_email": data.manager_email,
        "start_date": datetime.combine(start_date, datetime.min.time()),
        "end_date": datetime.combine(end_date, datetime.min.time()),
        "leave_type": leave_type,
        "reason": data.reason,
        "leave_status": "pending",
        "half_day_time": data.half_day_time,
        "is_compensatory": data.is_compensatory,
        "leave_duration": "full_day" if not data.half_day_time else data.half_day_time,
        "created_at": datetime.now()
    }

    existing_attendance = attendance_collection.find_one({
        "email": data.email,
        "date": datetime.combine(data.start_date, datetime.min.time())
    })

    if existing_attendance:
        attendance_collection.update_one(
            {"_id": existing_attendance["_id"]},
            {"$set": {
                "leave_status": "pending",
                "manager_email": data.manager_email,
                "reason": data.reason,
                "leave_type": data.leave_type,
                "start_date": datetime.combine(start_date, datetime.min.time()),
                "end_date": datetime.combine(end_date, datetime.min.time()),
                "leave_duration": data.half_day_time or "full_day",
                "is_compensatory": data.is_compensatory,
                "half_day_time": data.half_day_time,
                "created_at": datetime.now()
            }}
        )
    else:
        attendance_collection.insert_one({
            "email": data.email,
            "manager_email": data.manager_email,
            "reason": data.reason,
            "start_date": datetime.combine(start_date, datetime.min.time()),
            "end_date": datetime.combine(end_date, datetime.min.time()),
            "leave_status": "pending",
            "leave_type": data.leave_type,
            "leave_duration": data.half_day_time or "full_day",
            "half_day_time": data.half_day_time,
            "is_compensatory": data.is_compensatory,
            "created_at": datetime.now()
        })


    return {
        "message": f"{leave_type.title()} Leave request submitted for {total_days} day(s)",
        "leave_type": leave_type,
        "is_compensatory": data.is_compensatory,
        "start_date": start_date,
        "end_date": end_date,
        "half_day_time": data.half_day_time,
        "leave_duration": "full_day" if not data.half_day_time else data.half_day_time,
        "full_day": not data.half_day_time,
        "total_days": total_days
    }

# Endpoint to handle admin approval or rejection of a leave request
@router.post("/approve-decline-leave")
async def approve_decline_leave(data: LeaveAction):
    # Validate allowed actions
    if data.action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'.")

    # Convert string leave_id to MongoDB ObjectId
    try:
        leave_object_id = ObjectId(data.leave_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid leave_id format")

    # Fetch pending leave request by ID
    attendance_record = attendance_collection.find_one({
        "_id": leave_object_id,
        "leave_status": "pending"
    })
    if not attendance_record:
        raise HTTPException(status_code=404, detail="Pending leave request not found")

    # Get fields
    is_compensatory = attendance_record.get("is_compensatory", False)
    leave_type = attendance_record.get("leave_type", "casual")
    new_status = "approved" if data.action == "approve" else "rejected"
    from datetime import timedelta

    if new_status == "approved" and attendance_record.get("start_date") and attendance_record.get("end_date"):
        try:
            start_date = attendance_record["start_date"]
            end_date = attendance_record["end_date"]

            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date)
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date)

            email = attendance_record["email"]
            leave_duration = attendance_record.get("leave_duration")
            half_day_time = attendance_record.get("half_day_time")
            from datetime import timedelta, datetime, time, timezone as dt_timezone

            # Normalize start and end to just date
            if isinstance(start_date, datetime):
                start_date = start_date.date()
            if isinstance(end_date, datetime):
                end_date = end_date.date()

            current_date = start_date
            while current_date <= end_date:
                full_datetime = datetime.combine(current_date, time.min).replace(tzinfo=dt_timezone.utc)

                attendance_collection.insert_one({
                    "email": email,
                    "arrival_time": attendance_record.get("arrival_time"),
                    "leaving_time": attendance_record.get("leaving_time"),
                    "hours_present": attendance_record.get("hours_present", 0),
                    "date": full_datetime,
                    "start_date": full_datetime,
                    "end_date": full_datetime,
                    "leave_status": new_status,
                    "leave_type": leave_type,
                    "is_compensatory": is_compensatory,
                    "leave_duration": leave_duration,
                    "half_day_time": half_day_time,
                    "created_at": datetime.utcnow().replace(tzinfo=dt_timezone.utc)
                })

                current_date += timedelta(days=1)


            attendance_collection.delete_one({"_id": leave_object_id})

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to split leave range: {str(e)}")

    else:
        # Single-day or rejected leave – just update the original record
        attendance_collection.update_one(
            {"_id": leave_object_id},
            {"$set": {
                "leave_status": new_status,
                "leave_type": leave_type,
                "is_compensatory": is_compensatory
            }}
        )

    # Safe patch: auto-update today's attendance if approved and today falls in range
    if new_status == "approved":
        try:
            leave_start = attendance_record.get("start_date")
            leave_end = attendance_record.get("end_date") or leave_start
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

            if isinstance(leave_start, str):
                leave_start = datetime.fromisoformat(leave_start)
            if isinstance(leave_end, str):
                leave_end = datetime.fromisoformat(leave_end)

            if leave_start <= today <= leave_end:
                attendance_collection.update_one(
                    {"email": attendance_record["email"], "date": today},
                    {"$set": {
                        "leave_type": leave_type,
                        "leave_status": new_status,
                        "is_compensatory": is_compensatory,
                        "arrival_time": attendance_record.get("arrival_time"),
                        "leaving_time": attendance_record.get("leaving_time"),
                        "hours_present": attendance_record.get("hours_present", 0),
                        "status_reason": "on_leave"
                        }},
                    upsert=True
                )
        except Exception as e:
                    logging.warning(f"[Auto-Update Attendance] Failed for approved leave: {str(e)}")


    # 🛡 Safely extract leave date
    leave_date = attendance_record.get("date") or attendance_record.get("start_date") or attendance_record.get("leave_date")

    if leave_date:
        try:
            # If it's a string, convert to datetime
            if isinstance(leave_date, str):
                leave_date = datetime.fromisoformat(leave_date)
            formatted_date = leave_date.date()
        except Exception:
            formatted_date = leave_date  # fallback to raw string
    else:
        formatted_date = "Unknown"

    # Prepare email
    subject = f"Leave Request {new_status.capitalize()}"
    message = (
        f"Hi,\n\nYour leave request from {formatted_date} has been {new_status}.\n"
        f"Type: {leave_type.title()}\n"
        f"Compensatory: {'Yes' if is_compensatory else 'No'}\n\n"
        f"Regards,\nHR Team"
    )

    send_email(subject, message, attendance_record["email"])

    return {"message": f"Leave request {new_status} successfully"}

@router.get("/get-attendance-summary")
async def get_attendance_summary(
    email: str = Query(..., description="Employee email"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    page_size: int = Query(10, ge=1, le=100, description="Number of records per page"),
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
):
    emp = employee_collection.find_one({"Email": email})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee details not found.")

    try:
        today = datetime.today().date()
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if start_date_obj > end_date_obj:
        raise HTTPException(status_code=400, detail="Start date must be before end date.")

    employee_details = {}
    for field in ["Email", "First_name", "Last_name", "Employee_ID", "location_override", "working_days", "Designation", "phone", "address"]:
        employee_details[field] = emp.get(
            field,
            [] if field == "working_days" else (False if field == "location_override" else 0)
        )

    employee_details.update({
        "days_present": 0,
        "days_absent": 0,
        "leaves": [],
        "total_hours_worked": 0.0,
    })

    # Generate all working weekdays in date range
    all_dates = [
        (start_date_obj + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range((end_date_obj - start_date_obj).days + 1)
        if (start_date_obj + timedelta(days=i)).weekday() < 5
    ]
    all_dates.reverse()

    records = list(attendance_collection.find({"email": email}).sort("date", DESCENDING))
    grouped_by_date = {}

    for record in records:
        date = record.get("date") or record.get("start_date")
        if isinstance(date, datetime):
            date_str = date.strftime("%Y-%m-%d")
            grouped_by_date.setdefault(date_str, []).append(record)

    full_records = []

    for date_str in all_dates:
        attendance_status = "absent"
        leave = "none"
        is_late = False
        hours_worked = 0.0
        multiple_logs = []

        same_day_records = grouped_by_date.get(date_str, [])

        for record in same_day_records:
            curr_leave_status = record.get("leave_status", "none")

            main_arrival = record.get("arrival_time")
            main_leaving = record.get("leaving_time")
            main_hours = record.get("hours_present")

            if main_arrival or main_leaving:
                multiple_logs.append({
                    "arrival_time": main_arrival,
                    "leaving_time": main_leaving,
                    "arrival_photo": record.get("photo_path"),
                    "leaving_photo": record.get("leaving_photo"),
                    "hours_present": main_hours,
                    "latitude": record.get("latitude"),
                    "longitude": record.get("longitude")
                })
                try:
                    hours_worked += float(main_hours or 0)
                except (TypeError, ValueError):
                    pass
                attendance_status = "present"

            logs = record.get("multiple_logs", [])
            for log in logs:
                if log.get("arrival_time") or log.get("leaving_time"):
                    multiple_logs.append({
                        "arrival_time": log.get("arrival_time"),
                        "leaving_time": log.get("leaving_time"),
                        "arrival_photo": log.get("arrival_photo"),
                        "leaving_photo": log.get("leaving_photo"),
                        "hours_present": log.get("hours_present"),
                        "latitude": log.get("latitude"),
                        "longitude": log.get("longitude")
                    })
                    try:
                        hours_worked += float(log.get("hours_present") or 0)
                    except (TypeError, ValueError):
                        pass
                    attendance_status = "present"

            if record.get("is_late"):
                is_late = True

            if curr_leave_status == "approved":
                leave = "approved"
                attendance_status = "leave"
                break
            elif curr_leave_status == "pending":
                leave = "pending"
                attendance_status = "not approved"
            elif curr_leave_status == "rejected":
                leave = "rejected"
                attendance_status = "rejected"

        entry = {
            "date": date_str,
            "leave": leave,
            "attendance_status": attendance_status,
            "is_late": is_late,
            "logs": multiple_logs
        }

        full_records.append(entry)

        if is_late:
            employee_details.setdefault("late_days", 0)
            employee_details["late_days"] += 1

        if attendance_status == "leave":
            employee_details["leaves"].append(entry)
        elif attendance_status == "present":
            employee_details["days_present"] += 1
        elif attendance_status == "absent":
            employee_details["days_absent"] += 1

        employee_details["total_hours_worked"] += hours_worked

    total_records = len(full_records)
    total_pages = ceil(total_records / page_size)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_records = full_records[start_idx:end_idx]

    employee_details["total_days_present"] = employee_details["days_present"]
    employee_details["total_leaves"] = len(employee_details["leaves"])
    employee_details["total_absent"] = employee_details["days_absent"]
    employee_details["total_hours_worked"] = round(employee_details["total_hours_worked"], 2)
    employee_details["total_late_days"] = employee_details.get("late_days", 0)
    employee_details["is_hybrid"] = emp.get("is_hybrid", False)

    return {
        "email": email,
        "start_date": str(start_date_obj),
        "end_date": str(end_date_obj),
        "attendance_records": paginated_records,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_records": total_records,
        "employee_details": employee_details
    }


@router.get("/leave-balance/")
async def get_leave_balance(email: str = Query(..., description="Employee email")):
    # Ensure employee exists
    employee = employee_collection.find_one({"Email": email})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Get all approved leave records for this user with leave_type
    approved_leaves = attendance_collection.find({
        "email": email,
        "leave_status": "approved",
        "leave_type": {"$exists": True}
    })

    # ✅ Properly count used leaves per type
    used = {}

    for leave in approved_leaves:
        leave_type = leave.get("leave_type", "casual")

        # ✅ Handle compensatory festival inside the loop
        if leave_type == "festival" and leave.get("is_compensatory", False):
            leave_type = "compensatory_festival"

        used[leave_type] = used.get(leave_type, 0) + 1

    # Compute leave balance
    balance = {}
    for leave_type, total_allowed in LEAVE_QUOTA.items():
        used_count = used.get(leave_type, 0)
        balance[leave_type] = {
            "used": used_count,
            "remaining": max(0, total_allowed - used_count),
            "total": total_allowed
        }

    return {
        "email": email,
        "leave_balance": balance
    }


@router.get("/getLoginStatus")
async def get_is_submitted(
    email: str = Query(..., description="Employee email")
):
    from pytz import timezone
    IST = timezone("Asia/Kolkata")
    
    today_date_str = datetime.utcnow().date().isoformat()

    # Find the attendance record for this user for today
    record = attendance_collection.find_one({
        "email": email,
        "$expr": {
            "$eq": [{"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}}, today_date_str]
        }
    })

    if not record:
        return {
            "is_submitted": False,
            "arrival_time": None
        }

    is_submitted = record.get("is_submitted", False)
    arrival_time = record.get("arrival_time")

    return {
        "is_submitted": is_submitted,
        "arrival_time": arrival_time
    }


@router.get("/get-all-leaves", response_model=dict)
async def get_all_leaves(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=200, description="Page size"),
    email: Optional[str] = Query(None, description="Filter by employee email"),
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    leave_status: Optional[str] = Query(None, description="Filter by leave status"),
    leave_type: Optional[str] = Query(None, description="Filter by leave type"),
    group_by_email: bool = Query(True, description="Group multiple-day leaves into a single record"),
    fast_mode: bool = Query(False, description="Disable grouping and use fast pagination")
):
    skip = (page - 1) * page_size
    query = {
        "leave_status": {"$exists": True},
        "leave_type": {"$exists": True},
        "start_date": {"$exists": True},
        "end_date": {"$exists": True}
    }

    if email:
        query["email"] = email
    if leave_status:
        query["leave_status"] = leave_status.lower()
    if leave_type:
        query["leave_type"] = leave_type.lower()
    if start_date and end_date:
        query["start_date"] = {"$lte": datetime.combine(end_date, datetime.max.time())}
        query["end_date"] = {"$gte": datetime.combine(start_date, datetime.min.time())}

    def fmt(dt):
        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%d")
        return None

    # ✅ Fast mode: return raw results with individual IDs
    if fast_mode or not group_by_email:
        cursor = (
            attendance_collection
            .find(query)
            .sort("start_date", DESCENDING)
            .skip(skip)
            .limit(page_size)
        )
        leaves = list(cursor)
        results = []
        for leave in leaves:
            emp_email = leave.get("email", "unknown@example.com")
            emp = employee_collection.find_one({"Email": emp_email}) or {}
            results.append({
                "leave_id": str(leave.get("_id")),
                "email": emp_email,
                "first_name": emp.get("First_name", "Unknown"),
                "last_name": emp.get("Last_name", "Unknown"),
                "employee_id": leave.get("Employee_ID", "Unknown"),
                "leave_type": leave.get("leave_type", "unknown"),
                "leave_status": leave.get("leave_status", "unknown"),
                "is_compensatory": leave.get("is_compensatory", False),
                "reason": leave.get("reason", ""),
                "half_day_time": leave.get("half_day_time", None),
                "leave_duration": leave.get("leave_duration", "full_day"),
                "full_day": leave.get("leave_duration", "full_day") == "full_day",
                "start_date": fmt(leave.get("start_date")),
                "end_date": fmt(leave.get("end_date"))
            })
        total = attendance_collection.count_documents(query)
        total_pages = math.ceil(total / page_size)
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "leaves": results
        }

    # ✅ Grouped mode: fixed leave_id from sample, no duplicates
    raw_leaves = list(attendance_collection.find(query).sort("start_date", DESCENDING))
    grouped = defaultdict(list)
    seen_keys = set()

    for leave in raw_leaves:
        key = (
            leave.get("email"),
            leave.get("start_date"),
            leave.get("end_date"),
            leave.get("leave_type"),
            leave.get("leave_status"),
            leave.get("is_compensatory", False)
        )
        key_hash = str(key)
        if key_hash in seen_keys:
            continue  # Skip duplicate
        seen_keys.add(key_hash)
        grouped[key].append(leave)

    results = []
    for (email_key, s_date, e_date, leave_type, status, is_comp), leaves in grouped.items():
        sample = leaves[0]
        emp = employee_collection.find_one({"Email": email_key}) or {}
        results.append({
            "leave_id": str(sample.get("_id")),  # ✅ Correct ID for each grouped record
            "email": email_key,
            "first_name": emp.get("First_name", "Unknown"),
            "last_name": emp.get("Last_name", "Unknown"),
            "employee_id": emp.get("Employee_ID", "Unknown"),
            "leave_type": leave_type,
            "leave_status": status,
            "is_compensatory": is_comp,
            "reason": sample.get("reason", ""),
            "half_day_time": sample.get("half_day_time", None),
            "leave_duration": sample.get("leave_duration", "full_day"),
            "full_day": sample.get("leave_duration", "full_day") == "full_day",
            "start_date": fmt(s_date),
            "end_date": fmt(e_date),
            "total_days": (e_date - s_date).days + 1
        })

    total = len(results)
    total_pages = max(1, math.ceil(total / page_size))
    paginated = results[skip: skip + page_size]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "leaves": paginated
    }

@router.get("/leaves/summary/")
async def leave_summary(email: str = Query(...)):
    leaves = attendance_collection.find({
        "email": email,
        "leave_status": "approved"
    })

    summary = defaultdict(int)
    for leave in leaves:
        summary[leave.get("leave_type", "casual")] += 1

    return {
        "email": email,
        "leaves_taken": dict(summary)
    }

@router.get("/leaves/pending/count/")
async def count_pending_leaves():
    count = attendance_collection.count_documents({"leave_status": "pending"})
    return {"pending_leaves": count}

@router.get("/leaves/approved/today", summary="List of approved leaves for today")

async def get_today_approved_leaves():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    query = {
        "leave_status": "approved",
        "date": {"$gte": today, "$lt": tomorrow}
    }

    records = list(attendance_collection.find(query))
    result = []

    for record in records:
        emp = employee_collection.find_one({"Email": record.get("email")})
        result.append({
            "email": record.get("email"),
            "First_name": emp.get("First_name", "Unknown") if emp else "Unknown",
            "Last_name": emp.get("Last_name", "Unknown") if emp else "Unknown",
            "leave_type": record.get("leave_type", "casual"),
            "half_day_time": record.get("half_day_time", "full_day"),
            "reason": record.get("reason", ""),
            "date": record.get("date").strftime("%Y-%m-%d") if record.get("date") else "N/A"
        })

    return {
        "date": today.strftime("%Y-%m-%d"),
        "on_leave_today": result,
        "count": len(result)
    }

@router.get("/leaves/upcoming/week", summary="Upcoming approved leaves for the next 7 days")
async def get_upcoming_leaves_week():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ahead = today + timedelta(days=7)

    query = {
        "leave_status": "approved",
        "date": {"$gte": today, "$lte": week_ahead}
    }

    records = list(attendance_collection.find(query).sort("date", 1))
    upcoming = []

    for record in records:
        emp = employee_collection.find_one({"Email": record.get("email")})
        upcoming.append({
            "email": record.get("email"),
            "First_name": emp.get("First_name", "Unknown") if emp else "Unknown",
            "Last_name": emp.get("Last_name", "Unknown") if emp else "Unknown",
            "leave_type": record.get("leave_type", "casual"),
            "half_day_time": record.get("half_day_time", "full_day"),
            "reason": record.get("reason", ""),
            "date": record.get("date").strftime("%Y-%m-%d") if record.get("date") else "N/A"
        })

    return {
        "from": today.strftime("%Y-%m-%d"),
        "to": week_ahead.strftime("%Y-%m-%d"),
        "upcoming_leaves": upcoming,
        "count": len(upcoming)
    }

@router.get("/leaves/status/ongoing")
async def get_ongoing_leave_requests(email: str):
    today = datetime.utcnow()
    query = {
        "email": email,
        "leave_status": {"$in": ["pending", "approved"]},
        "start_date": {"$lte": today},
        "end_date": {"$gte": today}
    }

    records = list(attendance_collection.find(query).sort("start_date", ASCENDING))
    results = []
    for leave in records:
        results.append({
            "leave_id": str(leave.get("_id")),
            "leave_type": leave.get("leave_type"),
            "leave_status": leave.get("leave_status"),
            "is_compensatory": leave.get("is_compensatory", False),
            "start_date": leave.get("start_date").strftime("%Y-%m-%d") if leave.get("start_date") else None,
            "end_date": leave.get("end_date").strftime("%Y-%m-%d") if leave.get("end_date") else None,
            "reason": leave.get("reason", "")
        })

    return {
        "email": email,
        "ongoing_leaves": results,
        "count": len(results)
    }

@router.post("/admin/fix-compensatory-leaves")
async def fix_compensatory_leaves(secret: str = Query(...)):
    if secret != "AIiotSecret123":  # Protect this route!
        raise HTTPException(status_code=403, detail="Unauthorized")

    result = attendance_collection.update_many(
        {
            "leave_type": "festival",
            "is_compensatory": True,
            "leave_status": "approved"
        },
        {
            "$set": {"leave_type": "compensatory_festival"}
        }
    )

    return {
        "message": "Compensatory festival leaves updated successfully.",
        "modified_count": result.modified_count
    }

from fastapi.responses import FileResponse

@router.get("/view-document/")
async def view_document(email: str, filename: str):
    folder = "uploaded_documents"
    full_path = os.path.join(folder, filename)

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="Document not found")

    return FileResponse(full_path, filename=filename)


@router.get("/list-documents/")
async def list_documents(email: str):
    user = employee_collection.find_one({"Email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"documents": user.get("documents", [])}



@router.post("/submit-feedback")
async def submit_feedback(data: FeedbackInput):
    employee = employee_collection.find_one({"Email": data.email})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    feedback_doc = {
        "email": data.email,
        "subject": data.subject.strip(),
        "message": data.message.strip(),
        "rating": data.rating,
        "submitted_at": datetime.utcnow()
    }

    feedback_collection.insert_one(feedback_doc)

    return {"message": "Feedback submitted successfully"}

@router.get("/admin/feedbacks")  #Admin view api if needed
async def get_all_feedback():
    feedbacks = list(feedback_collection.find().sort("submitted_at", -1))
    for fb in feedbacks:
        fb["_id"] = str(fb["_id"])
        fb["submitted_at"] = fb["submitted_at"].strftime("%Y-%m-%d %H:%M:%S")
    return {"feedbacks": feedbacks}

@router.get("/admin/today-attendance", summary="Admin: Get today's attendance record(s)")
async def get_today_attendance(email: Optional[str] = Query(None, description="Optional employee email")):
    ist = timezone("Asia/Kolkata")
    today = datetime.now(ist).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    # Step 1: Fetch employees (all or single)
    employee_query = {"Email": email} if email else {}
    employees = list(employee_collection.find(employee_query))

    if not employees:
        raise HTTPException(status_code=404, detail="Employee(s) not found.")

    results = []

    for emp in employees:
        emp_email = emp.get("Email")
        emp_id = emp.get("Employee_ID", "N/A")
        first_name = emp.get("First_name", "N/A")
        last_name = emp.get("Last_name", "")
        full_name = f"{first_name} {last_name}".strip()
        is_hybrid = emp.get("is_hybrid", False)

        # Step 2: Get today's attendance
        records = list(attendance_collection.find({
            "email": emp_email,
            "date": {"$gte": today, "$lt": tomorrow}
        }))

        attendance_status = "absent"
        leave = "none"
        is_late = False
        hours_worked = 0.0
        multiple_logs = []

        for record in records:
            # Main check-in/out
            arrival = record.get("arrival_time")
            leaving = record.get("leaving_time")
            hours = float(record.get("hours_present") or 0)

            if arrival or leaving:
                multiple_logs.append({
                    "arrival_time": arrival,
                    "leaving_time": leaving,
                    "arrival_photo": record.get("photo_path"),
                    "leaving_photo": record.get("leaving_photo"),
                    "hours_present": record.get("hours_present"),
                    "latitude": record.get("latitude"),
                    "longitude": record.get("longitude")
                })
                hours_worked += hours
                attendance_status = "present"

            # Additional logs
            for log in record.get("multiple_logs", []):
                if log.get("arrival_time") or log.get("leaving_time"):
                    multiple_logs.append({
                        "arrival_time": log.get("arrival_time"),
                        "leaving_time": log.get("leaving_time"),
                        "arrival_photo": log.get("arrival_photo"),
                        "leaving_photo": log.get("leaving_photo"),
                        "hours_present": log.get("hours_present"),
                        "latitude": log.get("latitude"),
                        "longitude": log.get("longitude")
                    })
                    try:
                        hours_worked += float(log.get("hours_present") or 0)
                    except (TypeError, ValueError):
                        pass
                    attendance_status = "present"

            # Leave Handling
            curr_leave_status = (record.get("leave_status") or "").lower()
            curr_leave_duration = (record.get("leave_duration") or "").lower()

            if curr_leave_status == "approved":
                leave = "approved"
                if curr_leave_duration in ["first_half", "second_half", "half-day"] or hours_worked <= 4:
                    attendance_status = "half-day leave"
                else:
                    attendance_status = "leave"
                break
            elif curr_leave_status == "pending":
                leave = "pending"
                attendance_status = "not approved"
            elif curr_leave_status == "rejected":
                leave = "rejected"
                attendance_status = "rejected"

            if record.get("is_late"):
                is_late = True

            # Handle auto-logged
            if record.get("auto_logged_reason"):
                attendance_status = "Auto-Logged < Min Hours"
            elif record.get("auto_logged"):
                attendance_status = "Auto-Logged"

        results.append({
            "email": emp_email,
            "name": full_name,
            "employee_id": emp_id,
            "leave": leave,
            "attendance_status": attendance_status,
            "is_late": is_late,
            "total_hours_present": round(hours_worked, 2),
            "is_hybrid": is_hybrid,
            "logs": multiple_logs,
        })

    return {
        "date": today.strftime("%Y-%m-%d"),
        "total_records": len(results),
        "records": results
    }


@router.post("/admin/auto-log-leaving")
async def trigger_smart_auto_log(secret: str = Query(...)):
    if secret != "aiiots":
        raise HTTPException(status_code=403, detail="Unauthorized")
    from Ateendance_management.functions import smart_auto_log_leaving
    smart_auto_log_leaving()
    return {"message": "Auto-logout completed"}


@router.delete("/delete-employee", summary="Delete employee and their attendance records")
async def delete_employee(
    email: str = Query(..., description="Email of the employee to delete")
):
    # Step 1: Check if employee exists
    employee = employee_collection.find_one({"Email": email})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Step 2: Delete employee record
    emp_result = employee_collection.delete_one({"Email": email})

    # Step 3: Delete attendance records
    att_result = attendance_collection.delete_many({"email": email})

    # Step 4: Return response
    return {
        "message": f"Employee '{email}' deleted successfully.",
        "employee_deleted": emp_result.deleted_count == 1,
        "attendance_records_deleted": att_result.deleted_count
    }

@router.post("/create-team-by-email")
def create_team_by_email(data: CreateTeamRequest):
    members = []

    for email in data.member_emails:
        email = email.lower().strip()
        employee = employee_collection.find_one({"Email": email})

        if not employee:
            raise HTTPException(status_code=404, detail=f"Employee with email {email} not found")

        # 🔒 Check if already in any team
        already_in_team = teams_collection.find_one({
            "members.employee_id": employee["_id"]
        })

        if already_in_team:
            raise HTTPException(
                status_code=400,
                detail=f"Employee {email} is already part of a team: {already_in_team['team_name']}"
            )

        # ✅ Append full employee info
        members.append({
            "employee_id": employee["_id"],
            "email": employee["Email"],
            "first_name": employee.get("First_name", ""),
            "last_name": employee.get("Last_name", "")
        })

    # Create team document
    team_doc = {
        "team_name": data.team_name,
        "members": members
    }

    result = teams_collection.insert_one(team_doc)

    # Convert ObjectId for response
    for member in members:
        member["employee_id"] = str(member["employee_id"])

    return {
        "message": "Team created successfully",
        "team_id": str(result.inserted_id),
        "members": members
    }

def convert_objectid(obj):
    if isinstance(obj, list):
        return [convert_objectid(item) for item in obj]
    elif isinstance(obj, dict):
        return {
            key: convert_objectid(value)
            for key, value in obj.items()
        }
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj
    
@router.get("/teams")
async def get_teams():
    teams = []
    for team in teams_collection.find():
        teams.append(convert_objectid(team))
    return {"teams": teams}

@router.put("/team/update-members")
def update_team_members(data: UpdateTeamMembersRequest):
    team = teams_collection.find_one({"team_name": data.team_name})

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    members = team.get("members", [])
    member_emails = {member["email"].lower(): member for member in members}

    # Remove members
    for email in data.remove_members:
        member_emails.pop(email.lower(), None)

    # Add members
    for email in data.add_members:
        email = email.lower().strip()
        employee = employee_collection.find_one({"Email": email})

        if not employee:
            raise HTTPException(status_code=404, detail=f"Employee {email} not found")

        # Prevent adding someone already in a different team
        already_in_team = teams_collection.find_one({
            "team_name": {"$ne": data.team_name},
            "members.employee_id": employee["_id"]
        })

        if already_in_team:
            raise HTTPException(
                status_code=400,
                detail=f"Employee {email} is already in team {already_in_team['team_name']}"
            )

        # Add/update entry
        member_emails[email] = {
            "employee_id": employee["_id"],
            "email": employee["Email"],
            "first_name": employee.get("First_name", ""),
            "last_name": employee.get("Last_name", ""),
            "is_lead": False
        }

    if data.set_lead:
        lead_email = data.set_lead.lower()
        if lead_email not in member_emails:
            raise HTTPException(status_code=400, detail="Lead must be a current team member")

        for member in member_emails.values():
            member["is_lead"] = (member["email"].lower() == lead_email)

    # Update team in DB
    teams_collection.update_one(
        {"_id": team["_id"]},
        {"$set": {"members": list(member_emails.values())}}
    )

    # Convert ObjectId to string for response
    response_members = []
    for m in member_emails.values():
        m["employee_id"] = str(m["employee_id"])
        response_members.append(m)

    return {
        "message": "Team updated successfully",
        "team_name": data.team_name,
        "members": response_members
    }
