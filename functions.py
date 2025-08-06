from math import sin, atan2, radians, sqrt, cos
from bson import ObjectId
from datetime import datetime, timedelta, time, date
from PIL import Image
import bcrypt
from config.db import employee_collection, attendance_collection
import pytz
from dateutil import parser
import uuid
import io
import os
from fastapi import Query, HTTPException
from msal import ConfidentialClientApplication
import requests
from calendar import day_name
from jose import jwt
from typing import Union
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import csv # Add this line
from pytz import timezone, UTC
from fastapi.responses import StreamingResponse # Add this line
from datetime import datetime, timedelta
#from functions import format_time  # or wherever it's defined

load_dotenv()

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://graph.microsoft.com/.default"]

# Use a strong secret key in production
SECRET_KEY = "AIIOT-GEEKs"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # Validity

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

app = ConfidentialClientApplication(
    CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
)

def send_reset_code(email: str, code: str):
    token_result = app.acquire_token_silent(SCOPE, account=None) or \
                   app.acquire_token_for_client(scopes=SCOPE)

    if "access_token" not in token_result:
        raise Exception("Could not authenticate with Microsoft Graph")

    access_token = token_result["access_token"]
    payload = {
    "message": {
        "subject": "Password Reset Code",
        "body": {
            "contentType": "HTML",
            "content": f"""
                <html>
                    <body>
                        <p>Dear user,</p>
                        <p>Your password reset code is: <strong>{code}</strong></p>
                        <p>Please enter this code in the password reset form to continue.</p>
                        <p>
                            <a href="https://timelog.aiiotgeeks.com/forgetPassword?email={email}"
                            style="display: inline-block; padding: 10px 20px; font-size: 16px; color: white; background-color: #007bff; text-decoration: none; border-radius: 5px;">
                            Reset Password
                        </a></p>
                        <p>This link will expire in 15 minutes. If you did not request a password reset, please ignore this email.</p>
                        <br>
                        <p>Regards,<br>Team AiiotGeeks</p>
                    </body>
                </html>
            """
        },
        "toRecipients": [
            {
                "emailAddress": {
                    "address": email
                }
            }
        ]
    }
}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail",
        headers=headers,
        json=payload
    )

    if response.status_code != 202:
        raise Exception(f"Failed to send email: {response.text}")

IST = pytz.timezone('Asia/Kolkata')

allowed_latitude = 34.1273052    # Example:  latitude
allowed_longitude = 74.8408074   # Example:  longitude34.1273052, 74.8408074
allowed_radius_km = 0.5 


def clean_mongo_doc(doc):
    """Converts ObjectId and other non-serializable values to string."""
    return {
        key: str(value) if isinstance(value, ObjectId) else value
        for key, value in doc.items()
    }

def haversine_distance(lat1, lon1, lat2, lon2):
    # Earth radius in kilometers
    R = 6371.0

    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return distance


def serialize_record(record):
    record['_id'] = str(record['_id'])  # Convert ObjectId to string
    return record
def parse_datetime(value):
    if isinstance(value, datetime):
        return value
    elif isinstance(value, str):
        try:
            if len(value.strip()) <= 8 and ":" in value:
                # Format is like "15:48:00"
                today = date.today()
                h, m, s = map(int, value.strip().split(":"))
                return datetime(today.year, today.month, today.day, h, m, s)
            else:
                # ISO format with date and/or timezone
                return parser.isoparse(value)
        except Exception as e:
            print(f"❌ Failed to parse time: {value}, error: {e}")
    return None

from datetime import datetime
from bson import ObjectId

def is_late(arrival_time):
    if not arrival_time:
        return False
    late_threshold = time(10, 0)  # 10:00 AM
    return arrival_time.time() > late_threshold

from datetime import datetime, timedelta

def calculate_stats(attendance_records, employee=None):
    total_days_present = 0
    total_hours_worked = 0.0
    leaves_taken = 0
    days_absent = 0

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=30)

    working_days = (employee or {}).get("working_days") or [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
    ]

    attendance_map = {}

    for record in attendance_records:
        record_date = record.get("date") or record.get("start_date")
        if isinstance(record_date, str):
            try:
                record_date = datetime.strptime(record_date, "%Y-%m-%d").date()
            except ValueError:
                continue
        elif isinstance(record_date, datetime):
            record_date = record_date.date()
        elif not isinstance(record_date, datetime.date):
            continue

        if not (start_date <= record_date <= end_date):
            continue

        # --- Handle multiple_logs ---
        total_hours = 0.0
        has_valid_entry = False

        if "multiple_logs" in record:
            logs = record.get("multiple_logs", [])
            for log in logs:
                if log.get("arrival_time") or log.get("leaving_time"):
                    try:
                        total_hours += float(log.get("hours_present") or 0)
                        has_valid_entry = True
                    except:
                        continue
        else:
            # Single-entry fallback
            try:
                total_hours = float(record.get("hours_present") or 0)
                has_valid_entry = bool(record.get("arrival_time") or record.get("leaving_time"))
            except:
                pass

        # Keep the record with more hours
        existing = attendance_map.get(record_date)
        if has_valid_entry and (not existing or total_hours > float(existing.get("hours_present") or 0)):
            record["hours_present"] = total_hours  # Normalize field
            attendance_map[record_date] = record

    # ---- Final computation ----
    current_date = start_date
    while current_date <= end_date:
        weekday = current_date.strftime("%A")

        if weekday not in working_days:
            current_date += timedelta(days=1)
            continue

        record = attendance_map.get(current_date)

        if record:
            leave_status = (record.get("leave_status") or "").lower()

            if leave_status == "approved":
                leaves_taken += 1
            elif record.get("hours_present", 0) > 0 or record.get("arrival_time"):
                total_days_present += 1
                total_hours_worked += float(record["hours_present"])
            else:
                days_absent += 1
        else:
            days_absent += 1

        current_date += timedelta(days=1)

    return {
        "total_days_present": total_days_present,
        "total_hours_worked": round(total_hours_worked, 2),
        "leaves_taken": leaves_taken,
        "days_absent": days_absent
    }


def object_id_to_str(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj

def is_within_allowed_location(lat, lon):
    distance = haversine_distance(lat, lon, allowed_latitude, allowed_longitude)
    return distance <= allowed_radius_km


def generate_employee_id():
    """Generates a unique Employee ID like EMP20240001"""
    year = datetime.now().year
    random_part = str(uuid.uuid4().int)[:4]  # 4-digit random number
    return f"EMP{year}{random_part}"

# Check if employee exists (by email)
def employee_exists(email: str):
    return employee_collection.find_one({"Email": email}) is not None
def secret_key_matchs(secret: str):
    return employee_collection.find_one({"secret": secret}) is None
# Verify if password matches
def verify_password(stored_password: Union[str, bytes], provided_password: str) -> bool:
    if isinstance(stored_password, str):
        stored_password = stored_password.encode('utf-8')
    return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password)


IST = pytz.timezone('Asia/Kolkata')

def get_current_ist_time():
    return datetime.now(IST)

def save_image(img):
    image = Image.open(img)
    image = image.resize((250, 250))  # Resize to 250x250 pixels
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

def check_employee_location(
    lat: float = Query(..., ge=-90, le=90),  # Ensure lat is in the range of -90 to 90
    lon: float = Query(..., ge=-180, le=180),  # Ensure lon is in the range of -180 to 180
    employee_id: str = Query(...)
):
    # Fetch employee from the database
    employee = employee_collection.find_one({"Employee_ID": employee_id})
    
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Check if the employee's location is within the allowed range
    in_range = is_within_allowed_location(lat, lon)
    
    # If the employee is within the allowed location, grant access
    if in_range:
        return {"True"}

    # If not within range, check if the location override is enabled for the employee
    if employee.get("location_override", False):
        return {"True"}

    # Else, deny access
    return {"False"}

reset_codes = {}

def store_reset_code(email: str, code: str, expiry_minutes=10):
    reset_codes[email] = {
        "code": code,
        "expires_at": datetime.utcnow() + timedelta(minutes=expiry_minutes)
    }

def verify_reset_code(email: str, code: str):
    entry = reset_codes.get(email)
    if not entry:
        return False
    if entry["code"] != code or datetime.utcnow() > entry["expires_at"]:
        return False
    return True

from datetime import datetime, timedelta
import pytz

IST = pytz.timezone("Asia/Kolkata")

from datetime import datetime, timedelta
import pytz

IST = pytz.timezone("Asia/Kolkata")
IST = timezone("Asia/Kolkata")

def auto_log_leaving_job():
    now = datetime.now(IST)
    print("[Scheduler] Running auto_log_leaving_job at", now)

    # Find pending check-ins without leaving time
    pending_logs = list(attendance_collection.find({
        "$and": [
            {"arrival_time": {"$exists": True}},
            {"$or": [
                {"leaving_time": {"$exists": False}},
                {"leaving_time": None}
            ]},
            {"leave_type": {"$exists": False}}  # skip leave records
        ]
    }))

    print(f"[Scheduler] Found {len(pending_logs)} records pending auto-log.")

    for record in pending_logs:
        arrival_time = record.get("arrival_time")

        if arrival_time:
            # Convert string to datetime if needed
            from dateutil import parser

            if isinstance(arrival_time, str):
                if isinstance(arrival_time, str):
                    try:
                        parsed_time = parser.parse(arrival_time)

                        # Combine with date field from record (stored as datetime in UTC)
                        record_date = record.get("date")  # this is a datetime object

                        if isinstance(record_date, str):
                            record_date = parser.parse(record_date)
                        elif record_date.tzinfo is None:
                            record_date = pytz.UTC.localize(record_date)

                        record_date = record_date.astimezone(IST)

                        # Replace time part into date
                        arrival_time = datetime.combine(record_date.date(), parsed_time.time())
                        arrival_time = IST.localize(arrival_time)
                    except Exception as e:
                        print(f"[Error] Failed to parse arrival_time: {arrival_time}, error: {e}")
                        continue

            elif arrival_time.tzinfo is None:
                arrival_time = pytz.UTC.localize(arrival_time).astimezone(IST)
            else:
                arrival_time = arrival_time.astimezone(IST)

            # Proceed with time comparison
            if now - arrival_time > timedelta(hours=12):
                auto_leave_time = arrival_time + timedelta(hours=7)

                # Format time as 24-hour string in IST for display
                leaving_time_str = auto_leave_time.strftime("%I:%M:%S %p %Z")

                attendance_collection.update_one(
                    {"_id": record["_id"]},
                    {"$set": {
                        "leaving_time": leaving_time_str,  # store readable IST time
                        "hours_present": 7,
                        "leaving_photo": "auto-logged",
                        "is_submitted": False,
                        "auto_logged": True
                    }}
                )

                print(f"[Auto-log] {record['email']} auto-logged at {leaving_time_str} on {arrival_time.date()}")

# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.add_job(auto_log_leaving_job, "interval", minutes=240)  # Check every 4 hours
scheduler.start()

def extract_time(value):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = parser.isoparse(value)  # handles timezone-aware strings
        except Exception:
            return value  # fallback if string is broken
    return value.strftime("%H:%M:%S")

def get_access_token():
    app = ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    token = app.acquire_token_for_client(scopes=SCOPE)
    if "access_token" in token:
        return token["access_token"]
    else:
        raise Exception("Could not obtain access token")

GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"
def send_email(subject, body, to_email):
    # Fetch access token
    access_token = get_access_token()

    # Prepare the message
    email_msg = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body
            },
            "toRecipients": [
                {"emailAddress": {"address": to_email}}
            ]
        },
        "saveToSentItems": "true"
    }

    # Send email
    response = requests.post(
        f"{GRAPH_ENDPOINT}/users/{SENDER_EMAIL}/sendMail",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=email_msg
    )

    if response.status_code == 202:
        print("✅ Email sent successfully.")
    else:
        print("❌ Failed to send email:", response.status_code, response.text)

def format_time(t):
    if isinstance(t, str):
        return t
    elif isinstance(t, (datetime, time)):
        return t.strftime("%H:%M:%S")
    return None

def format_time_stat(time_obj):
    if not time_obj:
        return None
    # If time_obj is a string, try to parse it into datetime.time first
    if isinstance(time_obj, str):
        try:
            # Try parsing time string e.g. "14:30:00"
            time_obj = datetime.strptime(time_obj, "%H:%M:%S").time()
        except ValueError:
            return time_obj  # Return as is if parsing fails

    return time_obj.strftime("%I:%M:%S %p")  # 12-hour format with AM/PM

async def get_daily_attendance_for_export(export_date: date):
    """
    Fetches daily attendance records for all employees on a given date,
    enriching them with employee details.
    """
    start_of_day = datetime(export_date.year, export_date.month, export_date.day, 0, 0, 0)
    end_of_day = datetime(export_date.year, export_date.month, export_date.day, 23, 59, 59)
    attendance_records_cursor = attendance_collection.find({
        "date": {"$gte": start_of_day, "$lte": end_of_day}
    })
    attendance_records = await attendance_records_cursor.to_list(length=None)
    employees_cursor = employee_collection.find({})
    employees = await employees_cursor.to_list(length=None)
    employee_map = {emp.get("Email"): emp for emp in employees}
    exported_data = []
    for record in attendance_records:
        employee_email = record.get("email")
        employee_info = employee_map.get(employee_email, {})

        exported_data.append({
            "Date": export_date.strftime("%Y-%m-%d"),
            "Employee ID": employee_info.get("Employee_ID", "N/A"),
            "Name": employee_info.get("Name", "N/A"),
            "Email": employee_email,
            "Arrival Time": format_time(record.get("arrival_time")),
            "Leaving Time": format_time(record.get("leaving_time")),
            "Hours Present": record.get("hours_present", 0),
            "Leave Status": record.get("leave_status", "N/A"),
            "Remarks": record.get("remarks", ""),
            "Is Late": record.get("is_late", False)
        })
    return exported_data

def generate_csv_response(data: list[dict], filename: str):
    """
    Generates a CSV file from a list of dictionaries and returns it as a StreamingResponse.
    """
    if not data:
        # If no data, still provide headers for an empty CSV
        return StreamingResponse(
            iter(["Date,Employee ID,Name,Email,Arrival Time,Leaving Time,Hours Present,Leave Status,Remarks\n"]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}.csv"}
        )

    output = io.StringIO()
    headers = list(data[0].keys())

    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(data)

    output.seek(0) # Rewind to the beginning of the stream

    return StreamingResponse(
        iter([output.getvalue()]), # Wrap in iter to make it an async iterator
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}.csv"}
    )

from datetime import datetime, time

def auto_complete_missing_leaving():
    today = datetime.now().date()
    date_start = datetime.combine(today, datetime.min.time())
    
    # Find employees who logged arrival but missed leaving
    records = attendance_collection.find({
        "date": date_start,
        "arrival_time": {"$exists": True},
        "leaving_time": None,
        "leave_type": {"$exists": False}
    })

    for record in records:
        arrival_time = record.get("arrival_time")
        if not arrival_time:
            continue

        leaving_time = datetime.combine(today, time(18, 0))  # Set to 6:00 PM
        duration = leaving_time - arrival_time
        hours_present = round(duration.total_seconds() / 3600, 2)

        attendance_collection.update_one(
            {"_id": record["_id"]},
            {"$set": {
                "leaving_time": leaving_time,
                "hours_present": hours_present,
                "auto_filled": True,
                "auto_reason": "Auto-filled leaving due to missing logout at 6 PM"
            }}
        )

    print("✅ All missing leaving times auto-filled as 6:00 PM.")


    def to_ist_string(dt: datetime):
        if not dt:
         return None
        if dt.tzinfo is None:
            dt = IST.localize(dt)
        else:
            dt = dt.astimezone(IST)
        return dt.strftime("%H:%M:%S")