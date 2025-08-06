from fastapi import FastAPI, HTTPException, Request,Query
from pymongo import MongoClient
#from bson import ObjectIds
import pytz
import os
from bson import ObjectId  # Ensure this import is present
from routes.auth import router as auth
from routes.attendance import router as attendance
from routes.location import router as location
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Request, Depends, status, Response # Ensure Response and status are imported
from datetime import date, timedelta, datetime # Ensure date and datetime are imported
from Ateendance_management.functions import get_daily_attendance_for_export
from Ateendance_management.functions import generate_csv_response
from datetime import time
#from routes.login import router as login_router

from fastapi import FastAPI
#from routes.attendance import router as attendance_router


app = FastAPI()

origins = [
    "http://localhost:8083"
]


#app = FastAPI()



# Apply CORS middleware BEFORE including routers
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Specific origins instead of "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
    expose_headers=["Content-Type", "Authorization"],
)

app.include_router(auth, prefix="/auth", tags=["Authentication"])
app.include_router(attendance, prefix="/attendance", tags=["Attendance"])
app.include_router(location, prefix="/location", tags=["Restrict_location"])

