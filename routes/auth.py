from fastapi import APIRouter, HTTPException, Form, Body,UploadFile, File
from Ateendance_management.functions import generate_employee_id, employee_exists, secret_key_matchs, verify_password, send_reset_code, create_access_token, send_email
import bcrypt
from models.schemas import EmployeeRegister, Login, ConfirmForgetPassword, ForgetPassword, Feedback
from config.db import employee_collection, attendance_collection
from datetime import datetime
import random
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from pymongo import ReturnDocument, DESCENDING
import string
import pytz
from utils.auth1 import get_current_user
from fastapi import Depends
from pydantic import BaseModel
from utils.auth1 import create_access_token
from passlib.context import CryptContext
from Ateendance_management.functions import generate_employee_id, employee_exists, secret_key_matchs, verify_password
from typing import Optional,List
from fastapi import UploadFile, File
import os, shutil, bcrypt
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import EmailStr
from bson.objectid import ObjectId
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import EmailStr
from bson.objectid import ObjectId
import bcrypt
import mimetypes
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional, List
from fastapi import APIRouter, Form, File, UploadFile, HTTPException
from datetime import datetime
import bcrypt
from pymongo import MongoClient
from bson import Binary

router = APIRouter()


ist = pytz.timezone('Asia/Kolkata')

# Uploads directory
UPLOAD_DIR = "uploaded_docs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/register_employee/")
async def register_employee(
    first_name: str = Form(...),
    last_name: str = Form(...),
    designation: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    address: str = Form(...),
    secret: str = Form(...),

    # Optional document uploads
    aadhaar_or_passport: Optional[UploadFile] = File(None),
    pan_card: Optional[UploadFile] = File(None),
    qualification_cert: Optional[UploadFile] = File(None),
    experience_letter: Optional[UploadFile] = File(None),
    bank_details: Optional[UploadFile] = File(None),
    company_issued_docs: Optional[List[UploadFile]] = File(default=None),
    latest_photo: Optional[UploadFile] = File(None)
):
    # Check if employee already exists
    if employee_exists(email):
        raise HTTPException(status_code=400, detail="Employee already registered with this email.")
    
    if secret_key_matchs(secret):
        raise HTTPException(status_code=400, detail="Secret key does not match.")

    # Hash the password
    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    employee_id = generate_employee_id()

    # Save single file: only path
    def save_file(file: UploadFile, label: str):
        if not file:
            return None
        filename = f"{email}_{label}_{file.filename}"
        path = os.path.join(UPLOAD_DIR, filename)
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return path

    # Save multiple files: only path
    def save_multiple_files(files: Optional[List[UploadFile]], label_prefix: str):
        saved_files = []
        if files:
            for idx, file in enumerate(files):
                if file:
                    filename = f"{email}_{label_prefix}_{idx}_{file.filename}"
                    path = os.path.join(UPLOAD_DIR, filename)
                    with open(path, "wb") as buffer:
                        shutil.copyfileobj(file.file, buffer)
                    saved_files.append({
                        "filename": file.filename,
                        "path": path
                    })
        return saved_files

    # Save documents
    aadhaar_path = save_file(aadhaar_or_passport, "aadhaar")
    pan_path = save_file(pan_card, "pan")
    photo_path = save_file(latest_photo, "photo")
    qualification_path = save_file(qualification_cert, "qualification")
    experience_path = save_file(experience_letter, "experience")
    bank_path = save_file(bank_details, "bank")
    company_docs = save_multiple_files(company_issued_docs, "companydoc")

    # Construct employee data
    employee_data = {
    "First_name": first_name,
    "Last_name": last_name,
    "Designation": designation,
    "Employee_ID": employee_id,
    "phone": phone,
    "Email": email,
    "Password": hashed_password.decode("utf-8"),
    "address": address,
    "role": "user",
    "Documents": {
        "aadhaar_or_passport": {"path": aadhaar_path} if aadhaar_path else None,
        "pan_card": {"path": pan_path} if pan_path else None,
        "qualification_cert": {"path": qualification_path} if qualification_path else None,
        "experience_letter": {"path": experience_path} if experience_path else None,
        "bank_details": {"path": bank_path} if bank_path else None,
        "latest_photo": {"path": photo_path} if photo_path else None,
        "company_issued_docs": company_docs if company_docs else []
    }
}

    # Save to DB
    result = employee_collection.insert_one(employee_data)
    attendance_collection.insert_one({"Employee_ID": employee_id})
    employee_data["_id"] = str(result.inserted_id)
    
    return {
        "message": "Employee registered successfully!",
        "employee": {
            "Employee_ID": employee_id,
            "First_name": first_name,
            "Last_name": last_name,
            "Email": email,
            "Phone": phone,
            "role": "user",
            "address": address,
            "Designation": designation,
            "role": "user",
            "location_override": False,
            "is_submitted": False,
            "workingDays": None,
            "photo_url": None,
            "is_hybrid": False
        }
    }

BASE_URL = "http://127.0.0.1:8000"
UPLOAD_DIR = "uploaded_docs"

@router.get("/get_employee_details/")
async def get_employee_details(
    email: EmailStr = Query(...),
    download: Optional[str] = Query(None)
):
    if download:
        safe_path = os.path.basename(download)
        full_path = os.path.abspath(os.path.join(UPLOAD_DIR, safe_path))
        if not os.path.isfile(full_path):
            raise HTTPException(status_code=404, detail="Document not found")

        media_type, _ = mimetypes.guess_type(full_path)
        return FileResponse(
            path=full_path,
            filename=safe_path,
            media_type=media_type or "application/octet-stream"
        )

    # Fetch employee from DB
    employee = employee_collection.find_one({"Email": email.lower()})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee["_id"] = str(employee["_id"])
    employee.pop("Password", None)

    documents = {}
    cleaned_documents = {}

    if "Documents" in employee:
        for doc_key, doc_value in employee["Documents"].items():
            # Single file (dict)
            if isinstance(doc_value, dict):
                doc_value.pop("content", None)  # Remove binary
                path = doc_value.get("path")
                if path:
                    filename = os.path.basename(path)
                    documents[f"{doc_key}_download"] = (
                        f"{BASE_URL}/auth/get_employee_details/?email={email}&download={filename}"
                    )
                cleaned_documents[doc_key] = doc_value

            # Multiple files (list)
            elif isinstance(doc_value, list):
                new_doc_list = []
                for idx, doc in enumerate(doc_value):
                    if isinstance(doc, dict):
                        doc.pop("content", None)
                        path = doc.get("path")
                        if path:
                            filename = os.path.basename(path)
                            documents[f"{doc_key}_{idx}_download"] = (
                                f"{BASE_URL}/auth/get_employee_details/?email={email}&download={filename}"
                            )
                        new_doc_list.append(doc)
                cleaned_documents[doc_key] = new_doc_list

            else:
                print(f"⚠️ Unexpected format for document '{doc_key}': {type(doc_value)}")

        # Replace original document section with cleaned version
        employee["Documents"] = cleaned_documents

    return JSONResponse(content={
        "message": "Employee details fetched successfully.",
        "employee": employee,
        "documents": documents,
        "working_days": employee.get("working_days") or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    })



@router.post("/login_employee/")
def login_employee(login: Login):
    # Step 1: Check user existence
    employee_data = employee_collection.find_one({"Email": login.email.lower()})
    if not employee_data:
        raise HTTPException(status_code=400, detail="Employee not found.")

    # Step 2: Verify password
    if not verify_password(employee_data["Password"], login.password):
        raise HTTPException(status_code=400, detail="Incorrect password.")

    # Step 3: Check today's attendance
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    attendance_record = attendance_collection.find_one({
        "email": employee_data["Email"].lower(),
        "date": {"$gte": today, "$lt": today.replace(hour=23, minute=59, second=59)}
    })
    is_submitted = attendance_record.get("is_submitted", False) if attendance_record else False

    # Step 4: Generate JWT
    token = create_access_token({
        "sub": employee_data["Email"],
        "role": employee_data.get("role")
    })

    latest_photo = employee_data.get("Documents", {}).get("latest_photo")
    photo_url = None
    if latest_photo:
        photo_url = f"http://localhost:8000/uploaded_docs/{latest_photo}"


    photo_filename = employee_data.get("Documents", {}).get("latest_photo", None)
    if photo_filename:
        photo_url = f"http://localhost:8000/uploaded_docs{photo_filename}"
    else:
        photo_url = None

    # Step 5: Return login info + token
    return {
        "message": "Login successful",
        "user": {
            "Email": employee_data.get("Email"),
            "Employee_ID": employee_data.get("Employee_ID"),
            "First_name": employee_data.get("First_name"),
            "Last_name": employee_data.get("Last_name"),
            "address": employee_data.get("address"),
            "phone":employee_data.get ("phone"),
            "Designation":employee_data.get ("Designation"),
            "access_token": token,
            "token_type": "bearer",
            "role": employee_data.get("role"),
            "location_override": employee_data.get("location_override", False),
            "is_submitted": is_submitted,
            "workingDays": employee_data.get("working_days"),
            "photo_url": photo_url,
            "is_hybrid": employee_data.get("is_hybrid", False)
        }
    }

reset_codes = {}
@router.post("/forget-password/")
def forget_password(data: ForgetPassword):
    
    # TODO: Verify email exists in DB
    code = ''.join(random.choices(string.digits, k=6))
    reset_codes[data.email.lower()] = code  # Store securely in production

    try:
        send_reset_code(data.email, code)
        return {"message": "Reset code and link sent via email"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/forget-password/confirm/")
def confirm_forget_password(data: ConfirmForgetPassword):
    #,user: dict = Depends(get_current_user)
    # Check if code matches
    expected_code = reset_codes.get(data.email.lower())
    if not expected_code or expected_code != data.code:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    # Hash new password
    hashed_password = bcrypt.hashpw(data.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Update in DB
    result = employee_collection.update_one(
        {"Email": data.email.lower()},
        {"$set": {"Password": hashed_password}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Password update failed")

    # Clean up code
    reset_codes.pop(data.email.lower(), None)

    return {"message": "Password reset successful"}

UPLOAD_DIR = "uploaded_docs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.put("/update_employee/")
async def update_employee(
    email: EmailStr = Form(...),
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    designation: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    aadhaar_or_passport: Optional[UploadFile] = File(None),
    pan_card: Optional[UploadFile] = File(None),
    qualification_cert: Optional[UploadFile] = File(None),
    experience_letter: Optional[UploadFile] = File(None),
    bank_details: Optional[UploadFile] = File(None),
    company_issued_docs: Optional[List[UploadFile]] = File(None),
    latest_photo: Optional[UploadFile] = File(None)
):
    employee = employee_collection.find_one({"Email": email.lower()})
    if not employee:
        raise HTTPException(404, "Employee not found")

    def save_file(file: UploadFile, label: str):
        filename = f"{email}_{label}_{file.filename}"
        full = os.path.abspath(os.path.join(UPLOAD_DIR, filename))
        with open(full, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
        return full

    update_fields = {}
    if first_name: update_fields["First_name"] = first_name
    if last_name: update_fields["Last_name"] = last_name
    if designation: update_fields["Designation"] = designation
    if phone: update_fields["phone"] = phone
    if address: update_fields["address"] = address
    if password:
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        update_fields["Password"] = hashed.decode()

    doc_updates = {}
    if aadhaar_or_passport:
        doc_updates["aadhaar_or_passport"] = {"path": save_file(aadhaar_or_passport, "aadhaar")}
    if pan_card:
        doc_updates["pan_card"] = {"path": save_file(pan_card, "pan")}
    if qualification_cert:
        doc_updates["qualification_cert"] = {"path": save_file(qualification_cert, "qualification")}
    if experience_letter:
        doc_updates["experience_letter"] = {"path": save_file(experience_letter, "experience")}
    if bank_details:
        doc_updates["bank_details"] = {"path": save_file(bank_details, "bank")}
    if latest_photo:
        doc_updates["latest_photo"] = {"path": save_file(latest_photo, "photo")}
    if company_issued_docs:
        existing_docs = employee.get("Documents", {}).get("company_issued_docs", [])
        new_paths = [save_file(file, f"company_{i}") for i, file in enumerate(company_issued_docs)]
        combined_docs = existing_docs + [{"path": p} for p in new_paths]
        doc_updates["company_issued_docs"] = combined_docs


    if doc_updates:
        update_fields["Documents"] = {**employee.get("Documents", {}), **doc_updates}

    if not update_fields:
        raise HTTPException(400, "No updates provided")

    updated = employee_collection.find_one_and_update(
        {"Email": email.lower()},
        {"$set": update_fields},
        return_document=ReturnDocument.AFTER
    )
    updated["_id"] = str(updated["_id"])
    return {"message": "Employee updated successfully", "employee": updated}

from pytz import timezone  # assuming you're using pytz for IST

@router.post("/submit_feedback/", summary="Submit feedback", response_description="Feedback stored")
def submit_feedback(data: Feedback):
    timestamp_ist = datetime.now(ist)

    # Store feedback in DB
    feedback_data = {
        "email": data.email,
        "feedback": data.feedback,
        "timestamp": timestamp_ist
    }

    result = attendance_collection.insert_one(feedback_data)

    if result.inserted_id:
        # Find admin from employee collection
        admin = employee_collection.find_one({"role": "Admin"})
        if not admin or "Email" not in admin:
            raise HTTPException(status_code=404, detail="Admin email not found in employee collection")

        admin_email = admin["Email"]

        # Email content
        subject = "📩 New Employee Feedback Received"
        body = (
            f"Timestamp: {timestamp_ist.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"From: {data.email}\n"
            f"Feedback:\n{data.feedback}"
        )

        try:
            send_email(subject, body, to_email=admin_email)
        except Exception as e:
            print("⚠️ Feedback stored, but email failed to send:", e)

        return {"message": "Feedback submitted successfully and emailed to admin"}

    raise HTTPException(status_code=500, detail="Failed to store feedback")


utc = pytz.UTC

@router.get("/get_feedbacks/", summary="Get all feedbacks", response_description="List of feedbacks")
def get_all_feedbacks():
    
    try:
        feedbacks = attendance_collection.find(
            {"feedback": {"$exists": True}}
        ).sort("timestamp", -1)

        feedback_list = []
        for fb in feedbacks:
            ts = fb.get("timestamp")
            if ts:
                # If timestamp is naive, localize it to UTC first
                if ts.tzinfo is None:
                    ts = utc.localize(ts)
                # Now convert to IST
                ts_ist = ts.astimezone(ist)
                if ts:
                    if ts.tzinfo is None:
                        ts = utc.localize(ts)
                    ts_ist = ts.astimezone(ist)
                    # 12-hour format with AM/PM
                    timestamp_str = ts_ist.strftime("%Y-%m-%d %I:%M:%S %p")
                else:
                    timestamp_str = "N/A"

            feedback_list.append({
                "email": fb.get("email"),
                "feedback": fb.get("feedback"),
                "timestamp": timestamp_str
            })

        return {"total": len(feedback_list), "feedbacks": feedback_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching feedbacks: {str(e)}")