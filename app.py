# from geopy.distance import geodesic
import uuid
import bcrypt
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, Query
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import pytz
from typing import List, Optional
from PIL import Image
from datetime import datetime, date, timedelta
import io
import os
from fastapi.responses import StreamingResponse
from math import radians, cos, sin, sqrt, atan2

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


allowed_latitude = 34.1273052    # Example:  latitude
allowed_longitude = 74.8408074   # Example:  longitude34.1273052, 74.8408074
allowed_radius_km = 0.5 


client = MongoClient('mongodb://localhost:27017/')
db = client['Attendance']
employee_collection = db['employees']
attendance_collection = db["attendance"]
settings_collection = db["settings"]

# # Define the allowed location coordinates (latitude, longitude)
# ALLOWED_LOCATION = (34.1273052, 74.8408074)  #coordinates
# MAX_DISTANCE_KM = 50.0 # Maximum allowed distance in kilometers


# def is_within_allowed_location(lat, lon):
#     user_location = (lat, lon)
#     distance = geodesic(user_location, ALLOWED_LOCATION).kilometers
#     return distance <= MAX_DISTANCE_KM

app = FastAPI()

class EmployeeRegister(BaseModel):
    first_name: str
    last_name: str
    designation: str
    phone: int
    email: str
    address: str
    password: str
    secret: str

    class Config:
        orm_mode = True

class Login(BaseModel):
    email: str
    password: str
    

# def get_location_restriction():
#     setting = settings_collection.find_one({"setting": "location_restriction"})
#     if setting:
#         return setting["value"]
#     else:
#         # Default to True if setting is not found
#         settings_collection.insert_one({"setting": "location_restriction", "value": True})
#         return True

# def set_location_restriction(value):
#     settings_collection.update_one(
#         {"setting": "location_restriction"},
#         {"$set": {"value": value}},
#         upsert=True
#     )


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
def verify_password(stored_password: str, provided_password: str) -> bool:
    return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password.encode('utf-8'))
IST = pytz.timezone('Asia/Kolkata')

def get_current_ist_time():
    return datetime.now(IST)

def save_image(img):
    image = Image.open(img)
    image = image.resize((250, 250))  # Resize to 250x250 pixels
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

# def log_arrival(First_name, Last_name, date, photo):
#     # Convert date to datetime for MongoDB query
#     query_date = datetime.combine(date, datetime.min.time())
    
#     if attendance_collection.find_one({"First_name": First_name, "Last_name": Last_name, "Date": query_date}):
#         return False, "Arrival already logged for today."

#     current_time = get_current_ist_time()
#     photo_data = save_image(photo)

#     new_entry = {
#         'First_name': First_name,
#         'Last_name': Last_name,
#         'Date': query_date,
#         'Arrival Time': current_time.strftime('%I:%M %p'),
#         'Leaving Time': None,
#         'Hours Present': None,
#         'Arrival Photo': photo_data,
#         'Leaving Photo': None
#     }

#     attendance_collection.insert_one(new_entry)
#     return True, "Arrival logged successfully."

os.makedirs("photo", exist_ok=True)

# def calculate_hours_present(arrival_time_str: str, leaving_time: datetime, date: datetime.date):

#     arrival_time = datetime.strptime(arrival_time_str, '%I:%M %p')
    
#     # Combine date and time
#     date_obj = datetime.combine(date, datetime.min.time())
#     arrival_datetime = date_obj.replace(hour=arrival_time.hour, minute=arrival_time.minute)
#     leaving_datetime = date_obj.replace(hour=leaving_time.hour, minute=leaving_time.minute)
    
#     # Handle case when leaving time is past midnight (next day)
#     time_diff = leaving_datetime - arrival_datetime
#     if time_diff.total_seconds() < 0:
#         leaving_datetime += timedelta(days=1)
#         time_diff = leaving_datetime - arrival_datetime

#     # Calculate total hours
#     hours_present = round(time_diff.total_seconds() / 3600, 2)
#     return hours_present


# def log_leaving(name, date, photo):
#     # Convert date to datetime for MongoDB query
#     query_date = datetime.combine(date, datetime.min.time())
    
#     entry = attendance_collection.find_one({"Name": name, "Date": query_date})
#     if not entry:
#         return False, "Arrival not logged for today."

#     if entry['Leaving Time'] is not None:
#         return False, "Leaving time already logged for today."

#     leaving_time = get_current_ist_time()
#     arrival_time = datetime.strptime(entry['Arrival Time'], '%I:%M %p')
#     # Combine the date and time for both arrival and leaving
#     date_obj = datetime.combine(date, datetime.min.time())
#     arrival_datetime = date_obj.replace(hour=arrival_time.hour, minute=arrival_time.minute)
#     leaving_datetime = date_obj.replace(hour=leaving_time.hour, minute=leaving_time.minute)

#     photo_data = save_image(photo)
#     hours_present=calculate_hours_present(arrival_datetime, leaving_datetime, date_obj)
#     attendance_collection.update_one(
#         {"_id": entry["_id"]},
#         {
#             "$set": {
#                 'Leaving Time': leaving_time.strftime('%I:%M %p'),
#                 'Hours Present': hours_present,
#                 'Leaving Photo': photo_data
#             }
#         }
#     )
#     return True, "Leaving time logged successfully."



#Register
@app.post("/register_employee/")
def register_employee(employee: EmployeeRegister):
    # Check if the employee already exists
    if employee_exists(employee.email):
        raise HTTPException(status_code=400, detail="Employee already registered with this email.")
    if secret_key_matchs(employee.secret):
        raise HTTPException(status_code=400, detail="Secret key does not match")
    # Secure the password
    hashed_password = bcrypt.hashpw(employee.password.encode('utf-8'), bcrypt.gensalt())
    employee_id = generate_employee_id()
    # Prepare employee data
    employee_data = {
        "First_name": employee.first_name,
        "Last_name": employee.last_name,
        "Designation": employee.designation,
        "Employee_ID": employee_id,
        "phone": employee.phone,
        "Email": employee.email,
        "Password": hashed_password.decode('utf-8'),  # Save as string
        "address": employee.address

    }

    # Insert employee data into the collection
    result = employee_collection.insert_one(employee_data)

    # Retrieve the inserted employee document and convert the _id to string
    employee_data["_id"] = str(result.inserted_id)  # Get the ObjectId of the inserted employee
    return {"message": "Employee registered successfully!", "employee": {
            "Employee_ID": employee_id,
            "First_name": employee_data["First_name"],
            "Last_name":employee_data["Last_name"],
            "Email": employee_data["Email"],
            "Password": employee_data["Password"],
        }}

@app.post("/log-arrival/")
async def log_arrival(
    First_name: str = Form(...),
    Last_name: str = Form(...),
    date_str: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    photo: UploadFile = File(...)
):
    # Check location restriction
    allowed_latitude = 34.1273052    # Example:  latitude
    allowed_longitude = 74.8408074   # Example:  longitude34.1273052, 74.8408074
    allowed_radius_km = 0.5       # Within 500 meters

    distance = haversine_distance(latitude, longitude, allowed_latitude, allowed_longitude)

    if distance > allowed_radius_km:
        raise HTTPException(status_code=403, detail="Access denied: Outside allowed location")

    # Parse the date
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD."}

    # Read and resize the photo
    photo_bytes = await photo.read()
    resized_photo = save_image(io.BytesIO(photo_bytes))

    # Ensure 'photo' folder exists
    os.makedirs("photo_arrival", exist_ok=True)

    # Create filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{First_name}_{Last_name}_{timestamp}.png"
    file_path = os.path.join("photo_arrival", filename)

    # Save resized photo to 'photo' folder
    with open(file_path, "wb") as f:
        f.write(resized_photo)

    # Prepare document
    new_record = {
        "First_name": First_name,
        "Last_name": Last_name,
        "date": date_obj,
        "arrival_time": datetime.now().strftime("%H:%M:%S"),
        "leaving_time": None,
        "hours_present": None,
        "photo_path": file_path,
        "latitude": latitude,
        "longitude": longitude
    }

    # Insert into MongoDB
    attendance_collection.insert_one(new_record)

    return {"message": "Arrival logged successfully", "photo_path": file_path}
# @app.post("/log-arrival/")
# async def log_arrival(
#     First_name: str = Form(...),
#     Last_name: str = Form(...),
#     date_str: str = Form(...),
#     photo: UploadFile = File(...)
# ):
#     # Parse the date
#     try:
#         date_obj = datetime.strptime(date_str, "%Y-%m-%d")
#     except ValueError:
#         return {"error": "Invalid date format. Use YYYY-MM-DD."}

#     # Read and resize the photo
#     photo_bytes = await photo.read()
#     resized_photo = save_image(io.BytesIO(photo_bytes))

#     # Ensure 'photo' folder exists
#     os.makedirs("photo", exist_ok=True)

#     # Create filename
#     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#     filename = f"{First_name}_{Last_name}_{timestamp}.png"
#     file_path = os.path.join("photo", filename)

#     # Save resized photo to 'photo' folder
#     with open(file_path, "wb") as f:
#         f.write(resized_photo)

#     # Prepare document
#     new_record = {
#         "First_name": First_name,
#         "Last_name": Last_name,
#         "date": date_obj,
#         "arrival_time": datetime.now().strftime("%H:%M:%S"),
#         "leaving_time": None,
#         "hours_present": None,
#         "photo_path": file_path  # Save photo path instead of binary
#     }

#     # Insert into MongoDB
#     attendance_collection.insert_one(new_record)

#     return {"message": "Arrival logged successfully", "photo_path": file_path}


# API Route to login an employee
@app.post("/login_employee/")
def login_employee(login: Login):
    # Check if the employee exists by email
    employee_data = employee_collection.find_one({"Email": login.email})
    
    if not employee_data:
        raise HTTPException(status_code=400, detail="Employee not found.")

    # Verify the provided password with the stored hashed password
    if not verify_password(employee_data["Password"], login.password):
        raise HTTPException(status_code=400, detail="Incorrect password.")
    
    # Return success message (You could generate a JWT or session here for a real-world app)
    return {"message": "Login successful!", "employee": {"Name": employee_data["Name"], "Email": employee_data["Email"]}}


@app.post("/log-leaving/")
async def log_leaving(First_name: str, Last_name: str, date: date, photo: UploadFile = File(...)):
    start_datetime = datetime.combine(date, datetime.min.time())
    end_datetime = datetime.combine(date + timedelta(days=1), datetime.min.time())
    # Step 1: Fetch the record
    record = attendance_collection.find_one({
        "First_name": First_name,
        "Last_name": Last_name,
        "date": {
            "$gte": start_datetime,
            "$lt": end_datetime
        }
    })

    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    # Step 2: Get the arrival time string and convert to datetime
    try:
        arrival_time_str = record["arrival_time"]  # e.g., '14:35:00'
        arrival_time = datetime.strptime(arrival_time_str, '%H:%M:%S')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid arrival_time format: {e}")

    # Step 3: Get current time as leaving time
    leaving_time = get_current_ist_time()
    
    # Step 4: Combine with date to get full datetime objects
    arrival_datetime = datetime.combine(date, arrival_time.time())
    leaving_datetime = datetime.combine(date, leaving_time.time())

    # Handle case where leaving time is after midnight (next day)
    if leaving_datetime < arrival_datetime:
        leaving_datetime += timedelta(days=1)

    # Step 5: Calculate hours_present
    time_diff = leaving_datetime - arrival_datetime
    hours_present = round(time_diff.total_seconds() / 3600, 2)
    
    os.makedirs("photo_arrival", exist_ok=True)

    # Step 6: Save the new photo if needed
    photo_bytes = await photo.read()
    filename = f"{First_name}_{Last_name}_{date.strftime('%Y-%m-%d')}_leaving.png"
    file_path = os.path.join("photo", filename)
    with open(file_path, "wb") as f:
        f.write(photo_bytes)

    # Step 7: Update MongoDB
    updated_fields = {
        "leaving_time": leaving_time.strftime('%H:%M:%S'),
        "hours_present": hours_present,
        "leaving_photo": filename
    }

    attendance_collection.update_one(
        {"_id": ObjectId(record["_id"])},
        {"$set": updated_fields}
    )

    return {"message": "Leaving time and hours calculated successfully", "hours_present": hours_present}


class AttendanceRecord(BaseModel):
    First_name: str
    Last_name: str
    employee_id: str
    date: Optional[str] = None
    arrival_time: Optional[str] = None
    leaving_time: Optional[str] = None
    hours_present: Optional[int] = None
    photo: Optional[str] = None

def serialize_record(record):
    record['_id'] = str(record['_id'])  # Convert ObjectId to string
    return record

# @app.get("/attendance/{First_name}/{Last_name}/")
# async def get_attendance(First_name: str, Last_name: str):
#     projection = {
#         "date": 1,
#         "arrival_time": 1,
#         "leaving_time": 1,
#         "hours_present": 1,
#         "photo": 1,
#         "First_name":1,
#         "Last_name": 1  # You still need "name" because it's required in AttendanceRecord model
#     }
#     # Fetch all attendance records for the employee
#     records = list(employee_collection.find({"First_name": First_name, "Last_name": Last_name}, projection))
    
#     if not records:
#         raise HTTPException(status_code=404, detail="No attendance records found for this employee")

#     # Ensure each record includes the required fields, or provide default values
#     for record in records:
#         # Set default values for missing fields
#         record = serialize_record(record)
#         record.setdefault('date', None)
#         record.setdefault('arrival_time', None)
#         record.setdefault('leaving_time', None)
#         record.setdefault('hours_present', 0)
#         record.setdefault('photo', None)
    
#     return records

@app.put("/update-attendance/")
async def update_attendance(First_name: str, Last_name:str, date: date, arrival_time: Optional[str] = None, 
                            leaving_time: Optional[str] = None, hours_present: Optional[float] = None):
    date = datetime.combine(date, datetime.min.time())
    # Find the employee's record by name and date
    record = attendance_collection.find_one({"First_name": First_name, "Last_name": Last_name, "date": date})
    
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    
    # Prepare the update object
    update_data = {}
    if arrival_time:
        update_data["arrival_time"] = arrival_time
    if leaving_time:
        update_data["leaving_time"] = leaving_time
    if hours_present is not None:
        update_data["hours_present"] = hours_present
    
    # Perform the update operation
    attendance_collection.update_one({"_id": record["_id"]}, {"$set": update_data})
    
    return {"message": "Attendance record updated successfully"}

@app.get("/attendance-stats/")
async def get_attendance_stats(First_name: Optional[str] = None, Last_name: Optional[str] = None, start_date: date = None, end_date: date = None):
    query = {}
    
    if First_name:
        query["First_name"] = First_name
    if Last_name:
        query["Last_name"] = Last_name

    
    if start_date and end_date:
        query["date"] = {
            "$gte": datetime.combine(start_date, datetime.min.time()),
            "$lte": datetime.combine(end_date, datetime.max.time())
        }
    
    # Fetch attendance records based on the query
    records = list(attendance_collection.find(query))
    
    if not records:
        raise HTTPException(status_code=404, detail="No attendance records found")
    
    # Calculate statistics
    total_days = len(records)
    total_hours = sum([record.get("hours_present", 0) for record in records])
    total_leaves = total_days - len([record for record in records if record.get("hours_present") is not None])
    
    stats = {
        "total_days_present": total_days,
        "total_hours_worked": total_hours,
        "leaves_taken": total_leaves
    }
    
    return stats


# @app.get("/location-restriction/")
# async def get_location_restriction():
#     # Here, we're assuming the status is stored in a config collection

#     location_restriction = settings_collection.find_one({"name": "location_restriction"})
    
#     if location_restriction:
#         return {"location_restriction_enabled": location_restriction["value"]}
#     else:
#         return {"location_restriction_enabled": False}


# @app.put("/location-restriction/")
# async def update_location_restriction(value: bool):
#     # Update the location restriction status in config
#     settings_collection.update_one(
#         {"name": "location_restriction"},
#         {"$set": {"value": value}},
#         upsert=True
#     )
    
#     return {"message": "Location restriction updated successfully"}


@app.post("/admin-authenticate/")
async def authenticate_admin(username: str, password: str):
    # Assume we have a simple admin check (in a real app, you'd use hashed passwords)
    admin_data = {
        "admin": "password123"  # Simple mock data, replace with actual logic
    }
    
    if admin_data.get(username) == password:
        return {"message": "Authentication successful"}
    else:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    

import csv
from fastapi.responses import FileResponse
from io import StringIO

@app.get("/export-attendance/")
async def export_attendance(First_name: Optional[str] = None, Last_name: Optional[str] = None, start_date: date = None, end_date: date = None):
    query = {}
    
    if First_name:
        query["First_name"] = First_name
    if Last_name:
        query["Last_name"] = Last_name
    
    if start_date and end_date:
        query["date"] = {
            "$gte": datetime.combine(start_date, datetime.min.time()),
            "$lte": datetime.combine(end_date, datetime.max.time())
        }
    
    
    # Fetch the attendance records
    records = list(attendance_collection.find(query))
    
    if not records:
        raise HTTPException(status_code=404, detail="No attendance records found")
    
    # Remove MongoDB ObjectId (_id) or convert it to str
    for record in records:
        record["_id"] = str(record["_id"])
    # Prepare CSV response
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=["_id", "First_name", "Last_name", "date", "arrival_time", "leaving_time", "hours_present", "photo"])
    writer.writeheader()
    writer.writerows(records)
    output.seek(0)
    
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=attendance_records.csv"})



@app.get("/employees/names/")
def get_employee_names(first_name: str = Query(None), last_name: str = Query(None)):
    query = {}
    if first_name:
        query["First_name"] = first_name
    if last_name:
        query["Last_name"] = last_name

    try:
        employees_cursor = employee_collection.find(query, {"_id": 0, "First_name": 1, "Last_name": 1})
        employees = list(employees_cursor)
        return {"employee_names": employees}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




def is_within_allowed_location(lat, lon):
    distance = haversine_distance(lat, lon, allowed_latitude, allowed_longitude).kilometers
    return distance <= allowed_radius_km


@app.post("/check-access/")
def check_employee_location(
    lat: float = Query(...),
    lon: float = Query(...),
    employee_id: str = Query(...)
):

    distance = haversine_distance(lat, lon, allowed_latitude, allowed_longitude)
    # Fetch employee
    employee = employee_collection.find_one({"_id": ObjectId(employee_id)})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Check distance
    in_range = is_within_allowed_location(lat, lon)
    
    # If in range, allow access
    if in_range:
        return {"access": "granted", "reason": "Within allowed location"}

    # If out of range, check for override
    if employee.get("location_override", False):
        return {"access": "granted", "reason": "Location override granted by admin"}

    # Else, deny access
    return {"access": "denied", "reason": "Out of allowed range and no override"}


@app.put("/override-access/{employee_id}")
def override_access(employee_id: str, allow_override: bool = Query(...)):
    result = employee_collection.update_one(
        {"_id": ObjectId(employee_id)},
        {"$set": {"location_override": allow_override}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found or already set")
    return {"message": f"Location override set to {allow_override} for employee {employee_id}"}
