from fastapi import APIRouter, Request, Body, HTTPException
from models import Task,TaskUpdate
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