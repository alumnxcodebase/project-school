from fastapi import APIRouter, Request
from bson import ObjectId

router = APIRouter()

@router.get("/tasks")
async def get_my_tasks(request: Request):
    db = request.app.state.db
    user_id = request.state.userId  # Set by verify_api_key in main.py

    user_tasks = await db.usertasks.find({"userId": user_id}).to_list(None)

    completed = []
    active = []
    pending = []

    for ut in user_tasks:
        status = ut.get("taskStatus", ut.get("status", "pending"))
        task_id = ut.get("taskId")

        try:
            task = await db.tasks.find_one({"_id": ObjectId(task_id)}) if task_id else None
        except Exception:
            task = None

        entry = {
            "taskId": task_id,
            "status": status,
            "title": task.get("title") if task else ut.get("name", "Unknown"),
            "description": task.get("description") if task else "",
            "skillType": task.get("skillType") if task else ut.get("skillType", ""),
            "projectId": ut.get("projectId", ""),
            "projectName": ut.get("projectName", ""),
            "assignedAt": str(ut.get("assignedAt", "")),
            "completedAt": str(ut.get("completionDate", "")) if ut.get("completionDate") else None,
        }

        if status == "completed":
            completed.append(entry)
        elif status == "active":
            active.append(entry)
        else:
            pending.append(entry)

    return {
        "userId": user_id,
        "completed": completed,
        "active": active,
        "pending": pending,
        "summary": {
            "total": len(user_tasks),
            "completed": len(completed),
            "active": len(active),
            "pending": len(pending)
        }
    }