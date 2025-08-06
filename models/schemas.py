from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Literal
from datetime import datetime, date, time
from enum import Enum
from typing import Optional, Union
from datetime import datetime, date
from pydantic import BaseModel, validator
from dateutil.parser import parse
from pydantic import validator
from typing import Union
from typing import Union
from dateutil.parser import parse
from pydantic import BaseModel, EmailStr
from typing import Optional



class AttendanceUpdate(BaseModel):
    Email: str
    date: date
    arrival_time: Optional[Union[str, datetime]] = None
    leaving_time: Optional[Union[str, datetime]] = None
    hours_present: Optional[float] = None
    leave_type: Optional[str] = None
    leave_status: Optional[str] = None
    reason: Optional[str] = None
    half_day_time: Optional[str] = None
    is_compensatory: Optional[bool] = None
    leave_duration: Optional[str] = None

    @validator('arrival_time', 'leaving_time', pre=True)
    def parse_time(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return parse(value)
            except Exception:
                raise ValueError("Time must be a valid string like '09:00:00' or full ISO datetime")
        return value


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


class EmployeeUpdate(BaseModel):
    First_name: Optional[str] = None
    Last_name: Optional[str] = None
    Designation: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    

from dateutil.parser import parse



class ForgetPassword(BaseModel):
    email: EmailStr

class ConfirmForgetPassword(BaseModel):
    email: EmailStr
    code: str
    new_password: str

class UpdateWorkingDays(BaseModel):
    Email: str
    workingDays: List[str]


class LeaveRequest(BaseModel):
    email: EmailStr
    start_date: Optional[date] = Field(default_factory=date.today)
    end_date: Optional[date] = Field(default_factory=date.today)
    half_day_time: Optional[Literal["first_half", "second_half"]] = None
    leave_type: Literal['casual', 'sick', 'earned', 'bereavement', 'festival', 'compensatory_festival']
    reason: str
    manager_email: EmailStr
    is_compensatory: Optional[bool] = False


class LeaveAction(BaseModel):
    leave_id: str 
    action: str    

class AttendanceQuery(BaseModel):
    email: str

class Feedback(BaseModel):
    email: EmailStr
    feedback: str

class AttendanceEntry(BaseModel):
    record_id: str
    date: str
    arrival_time: Optional[str]
    leaving_time: Optional[str]
    leave: Optional[str]
    attendance_status: str
    is_late: bool

class LeaveResponse(BaseModel):
    email: str = Field(..., description="Employee's email address")
    first_name: str = Field(..., description="Employee's first name")
    last_name: str = Field(..., description="Employee's last name")
    employee_id: str = Field(..., description="Employee ID")
    leave_type: str = Field(..., description="Type of leave taken")
    leave_status: str = Field(..., description="Current status of leave (approved, pending, etc.)")
    is_compensatory: bool = Field(..., description="Whether the leave is compensatory")
    start_date: Optional[str] = Field(None, description="Start date of leave (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date of leave (YYYY-MM-DD)")
    total_days: int = Field(..., ge=1, description="Total number of days for the leave")
    leave_duration: str = Field(..., description="Leave duration: full_day / first_half / second_half")
    full_day: bool = Field(..., description="True if full day leave")



class FeedbackInput(BaseModel):
    email: EmailStr
    subject: str
    message: str
    rating: Optional[int] = None  # 1–5 optional rating

class CreateTeamRequest(BaseModel):
    team_name: str
    member_emails: List[str]

class UpdateTeamMembersRequest(BaseModel):
    team_name: str
    add_members: Optional[List[EmailStr]] = []
    remove_members: Optional[List[EmailStr]] = []
    set_lead: Optional[EmailStr] = None