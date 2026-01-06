from fastapi import APIRouter, Request, Body, HTTPException
from models import Goal
from utils.helpers import serialize
from datetime import datetime
from fastapi import APIRouter, Request, Body, HTTPException
from models import Goal
from utils.helpers import serialize
from bson import ObjectId

router = APIRouter()


@router.get("/")
async def get_all_goals(request: Request, userId: str = None):
    db = request.app.state.db
    query = {"userId": userId} if userId else {}
    return [serialize(g) async for g in db.goals.find(query)]

@router.get("/{goal_id}")
async def get_goal_by_id(request: Request, goal_id: str):
    db = request.app.state.db
    goal = await db.goals.find_one({"_id": ObjectId(goal_id)})
    return serialize(goal) if goal else HTTPException(404)
@router.post("/", response_model=Goal, status_code=201)
async def set_user_goals(request: Request, goal_data: Goal = Body(...)):
    db = request.app.state.db

    # Update if exists, otherwise create (Upsert)
    await db.goals.update_one(
        {"userId": goal_data.userId},
        {"$set": {
            "goals": goal_data.goals,
            "updated_at": datetime.now()
        }},
        upsert=True
    )

    updated_goal = await db.goals.find_one({"userId": goal_data.userId})
    return serialize(updated_goal)


@router.get("/{user_id}", response_model=Goal)
async def get_user_goals(request: Request, user_id: str):
    db = request.app.state.db
    goal = await db.goals.find_one({"userId": user_id})
    if not goal:
        raise HTTPException(status_code=404, detail="Goals not found for this user")
    return serialize(goal)