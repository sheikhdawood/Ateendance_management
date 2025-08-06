from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db = client["Attendance"]
employee_collection = db["employees"]
attendance_collection = db["attendance"]
attendance_logs = db["attendance_logs"] 
teams_collection = db["teams_collection"]
feedback_collection = db["feedback"]
leave_collection = db["leave_requests"]
working_days_collection = db["working_days"]    
leave_responses_collection = db["leave_responses"]
attendance_query_collection = db["attendance_query"]
forget_password_collection = db["forget_password"]
confirm_forget_password_collection = db["confirm_forget_password"]
update_working_days_collection = db["update_working_days"]
leave_action_collection = db["leave_action"]
feedback_input_collection = db["feedback_input"]

