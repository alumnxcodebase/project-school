from fastapi import APIRouter, Request, Body, HTTPException
from models.models import Notice
from utils.helpers import serialize
from typing import List, Optional
from datetime import datetime

router = APIRouter()

@router.get("", response_model=List[Notice])
async def list_notices(request: Request):
    """Get all notices sorted by createdAt descending"""
    try:
        db = request.app.state.db
        cursor = db.notices.find().sort("createdAt", -1)
        notices = [serialize(doc) async for doc in cursor]
        return notices
    except Exception as e:
        print(f"❌ Error fetching notices: {str(e)}")
        # Return empty list instead of 500 while troubleshooting
        return []

@router.post("/", response_model=Notice, status_code=201)
async def create_notice(request: Request, notice: Notice = Body(...)):
    """Create a new notice"""
    db = request.app.state.db
    notice_dict = notice.model_dump(exclude={"id"})
    if "createdAt" not in notice_dict or notice_dict["createdAt"] is None:
        notice_dict["createdAt"] = datetime.now()
    
    result = await db.notices.insert_one(notice_dict)
    new_notice = await db.notices.find_one({"_id": result.inserted_id})
    return serialize(new_notice)

@router.delete("/{notice_id}", status_code=200)
async def delete_notice(request: Request, notice_id: str):
    """Delete a notice"""
    from bson import ObjectId
    db = request.app.state.db
    if not ObjectId.is_valid(notice_id):
        raise HTTPException(status_code=400, detail="Invalid Notice ID")
    
    result = await db.notices.delete_one({"_id": ObjectId(notice_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notice not found")
    
    return {"status": "success", "message": "Notice deleted"}
