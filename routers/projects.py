from fastapi import APIRouter, Request, Body, HTTPException
from models import Project
from utils.helpers import serialize
from bson import ObjectId
from typing import List

router = APIRouter()


@router.get("/", response_model=List[Project])
async def list_projects(request: Request):
    db = request.app.state.db
    cursor = db.projects.find().sort("created_at", -1)
    return [serialize(doc) async for doc in cursor]


@router.post("/", response_model=Project, status_code=201)
async def create_new_project(request: Request, project: Project = Body(...)):
    db = request.app.state.db
    project_dict = project.model_dump(exclude={"id"})
    result = await db.projects.insert_one(project_dict)

    new_project = await db.projects.find_one({"_id": result.inserted_id})
    return serialize(new_project)


@router.get("/{project_id}", response_model=Project)
async def get_project_details(request: Request, project_id: str):
    db = request.app.state.db
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid Project ID")

    project = await db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return serialize(project)

@router.get("/{project_id}/stats")
async def get_project_stats(request: Request, project_id: str):
    db = request.app.state.db
    tasks = await db.tasks.find({"project_id": project_id}).to_list(length=100)
    return {
        "total_tasks": len(tasks),
        "completed": len([t for t in tasks if t["status"] == "completed"]),
        "pending": len([t for t in tasks if t["status"] == "pending"]),
        "in_progress": len([t for t in tasks if t["status"] == "in_progress"])
    }