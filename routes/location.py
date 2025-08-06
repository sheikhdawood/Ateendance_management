from fastapi import APIRouter, Query
from fastapi.exceptions import HTTPException
from Ateendance_management.functions import is_within_allowed_location
from config.db import employee_collection
from utils.auth1 import get_current_user
from fastapi import Depends

router = APIRouter()

@router.post("/check-access/")
def check_employee_location(
    lat: float = Query(..., ge=-90, le=90),  # Ensure lat is in the range of -90 to 90
    lon: float = Query(..., ge=-180, le=180),  # Ensure lon is in the range of -180 to 180
    employee_id: str = Query(...),
    
):
    # Fetch employee from the database
    employee = employee_collection.find_one({"Employee_ID": employee_id})
    
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Check if the employee's location is within the allowed range
    in_range = is_within_allowed_location(lat, lon)
    
    # If the employee is within the allowed location, grant access
    if in_range:
        return {"access": "granted", "reason": "Within allowed location"}

    # If not within range, check if the location override is enabled for the employee
    if employee.get("location_override", False):
        return {"access": "granted", "reason": "Location override granted by admin"}

    # Else, deny access
    return {"access": "denied", "reason": "Out of allowed range and no override"}

@router.put("/override-access/{employee_id}")
def override_access(employee_id: str, allow_override: bool = Query(...)):
    
    # Update the employee document to allow or disallow the location override
    result = employee_collection.update_one(
        {"Employee_ID": employee_id},  # Match by Employee_ID (not by ObjectId)
        {"$set": {"location_override": allow_override}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found or already set")
    
    return {"message": f"Location override set to {allow_override} for employee {employee_id}"}


@router.post("/enable-hybrid/")
async def enable_hybrid_mode(email: str, allow_hybrid: bool = Query(...)):
    result = employee_collection.update_one(
        {"Email": email},
        {"$set": {"is_hybrid": allow_hybrid}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")

    return {
        "message": "Hybrid mode set for employee",
        "is_hybrid": allow_hybrid
    }
