from fastapi import APIRouter, Request, Body, HTTPException
from models import Task, TaskUpdate, UserTaskLink
from utils.helpers import serialize
from bson import ObjectId
from typing import List

router = APIRouter()


@router.post("/", response_model=Task, status_code=201)
async def create_task(request: Request, task: Task = Body(...)):
    db = request.app.state.db
    task_dict = task.model_dump(exclude={"id"})
    result = await db.tasks.insert_one(task_dict)

    new_task = await db.tasks.find_one({"_id": result.inserted_id})
    return serialize(new_task)


@router.get("/", response_model=List[Task])
async def get_all_tasks(request: Request):
    db = request.app.state.db
    # Find all tasks
    cursor = db.tasks.find({})
    return [serialize(doc) async for doc in cursor]


@router.get("/user/{user_id}", response_model=List[Task])
async def get_user_tasks(request: Request, user_id: str):
    db = request.app.state.db
    # Find all tasks assigned to this user
    cursor = db.tasks.find({"assigned_to": user_id})
    return [serialize(doc) async for doc in cursor]


@router.put("/{task_id}", response_model=Task)
async def update_task_status(request: Request, task_id: str, update: TaskUpdate):
    db = request.app.state.db
    if not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=400, detail="Invalid Task ID")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    await db.tasks.update_one({"_id": ObjectId(task_id)}, {"$set": update_data})

    updated = await db.tasks.find_one({"_id": ObjectId(task_id)})
    return serialize(updated)

@router.post("/user-tasks", status_code=201)
async def link_user_to_task(request: Request, payload: UserTaskLink = Body(...)):
    db = request.app.state.db
    
    # 1. Validate that the taskId is a real MongoDB ObjectId
    if not ObjectId.is_valid(payload.taskId):
        raise HTTPException(status_code=400, detail="Invalid taskId format")
    
    # 2. Update the task in the database
    # We set the 'assigned_to' field of the task to the provided userId
    result = await db.tasks.update_one(
        {"_id": ObjectId(payload.taskId)},
        {"$set": {"assigned_to": payload.userId}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return {"status": "success", "message": f"Task {payload.taskId} assigned to user {payload.userId}"}