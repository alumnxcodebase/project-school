from fastapi import APIRouter, Request, Body, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from utils.helpers import serialize

router = APIRouter()

# --- Models ---

class ProjectSchoolSubscription(BaseModel):
    userId: str
    cohortId: str
    status: str = "active"
    type: str = "paid"
    startDate: datetime = Field(default_factory=datetime.now)

class PaymentRecord(BaseModel):
    userId: str
    amount: float
    status: str
    transactionId: str
    date: datetime = Field(default_factory=datetime.now)

class FeedbackItem(BaseModel):
    userId: str
    message: str
    adminId: str
    createdAt: datetime = Field(default_factory=datetime.now)

class AssignmentTemplateTask(BaseModel):
    name: str
    description: Optional[str] = None

class AssignmentTemplate(BaseModel):
    name: str
    description: Optional[str] = None
    tasks: List[AssignmentTemplateTask] = Field(default_factory=list)
    createdBy: str = "admin"
    createdAt: datetime = Field(default_factory=datetime.now)

# --- Endpoints ---

@router.get("/get-cohort-members", status_code=200)
async def get_cohort_members(request: Request):
    db = request.app.state.db
    # Fetch all users with relevant fields
    cursor = db.users.find({}, {"_id": 1, "name": 1, "email": 1, "phone": 1, "subscriptionStatus": 1})
    members = []
    async for doc in cursor:
        member = serialize(doc)
        # Map backend 'name' to frontend 'fullName' and 'id' to 'userId'
        member["userId"] = member.get("id")
        member["fullName"] = member.get("name", "Unknown User")
        
        # Determine subscription status flags
        sub_status = member.get("subscriptionStatus", "trial").lower()
        member["isPaid"] = sub_status == "paid"
        member["isTrial"] = sub_status == "trial"
        
        members.append(member)
    return members

@router.post("/add-assignment", status_code=201)
async def add_assignment(request: Request, assignment: AssignmentTemplate = Body(...)):
    db = request.app.state.db
    assignment_dict = assignment.model_dump()
    result = await db.assignment_templates.insert_one(assignment_dict)
    return {"status": "success", "id": str(result.inserted_id)}

@router.post("/feedback", status_code=201)
async def add_feedback(request: Request, feedback: FeedbackItem = Body(...)):
    db = request.app.state.db
    feedback_dict = feedback.model_dump()
    await db.feedback.insert_one(feedback_dict)
    return {"status": "success", "message": "Feedback recorded"}

@router.get("/get-assignments", status_code=200)
async def get_assignments(request: Request):
    db = request.app.state.db
    cursor = db.assignment_templates.find().sort("createdAt", -1)
    assignments = [serialize(doc) async for doc in cursor]
    return assignments

@router.post("/update-assignment", status_code=200)
async def update_assignment(request: Request, body: Dict[str, Any] = Body(...)):
    db = request.app.state.db
    assignment_id = body.get("id")
    if not assignment_id or not ObjectId.is_valid(assignment_id):
        raise HTTPException(status_code=400, detail="Invalid Assignment ID")
    
    update_data = body.get("update", {})
    await db.assignment_templates.update_one(
        {"_id": ObjectId(assignment_id)},
        {"$set": update_data}
    )
    return {"status": "success"}

@router.post("/assignments/delete", status_code=200)
async def delete_assignment(request: Request, body: Dict[str, Any] = Body(...)):
    db = request.app.state.db
    assignment_id = body.get("id")
    if not assignment_id or not ObjectId.is_valid(assignment_id):
        raise HTTPException(status_code=400, detail="Invalid Assignment ID")
    
    await db.assignment_templates.delete_one({"_id": ObjectId(assignment_id)})
    return {"status": "success"}

@router.post("/get-preferences", status_code=200)
async def get_preferences(request: Request, body: Dict[str, Any] = Body(...)):
    """Proxy to preferences router or direct DB call"""
    db = request.app.state.db
    user_id = body.get("userId")
    if not user_id:
        raise HTTPException(status_code=400, detail="userId is required")
    
    prefs_doc = await db.preferences.find_one({"userId": user_id})
    if not prefs_doc:
        return {"status": "success", "preferences": {"userId": user_id, "preferences": []}}
    
    return {"status": "success", "preferences": serialize(prefs_doc)}
