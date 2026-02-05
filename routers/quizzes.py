from fastapi import APIRouter, Request, Body, HTTPException
from typing import List, Optional
from bson import ObjectId
from models.models import Quiz, QuizQuestion

router = APIRouter()

def serialize(doc):
    """Helper to convert MongoDB _id to string id"""
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc

@router.get("/task/{task_id}", response_model=Quiz)
async def get_quiz_by_task(request: Request, task_id: str):
    """Get the quiz associated with a specific task"""
    db = request.app.state.db
    quiz = await db.quizzes.find_one({"taskId": task_id})
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found for this task")
    return serialize(quiz)

@router.post("/", status_code=201)
async def create_or_update_quiz(request: Request, quiz: Quiz = Body(...)):
    """Create or update a quiz for a task"""
    db = request.app.state.db
    quiz_dict = quiz.model_dump(exclude={"id"})
    
    # Upsert based on taskId
    result = await db.quizzes.update_one(
        {"taskId": quiz.taskId},
        {"$set": quiz_dict},
        upsert=True
    )
    
    updated_quiz = await db.quizzes.find_one({"taskId": quiz.taskId})
    return serialize(updated_quiz)
