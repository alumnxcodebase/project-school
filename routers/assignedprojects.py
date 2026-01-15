from fastapi import APIRouter, Request, Body, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import datetime

router = APIRouter()


class ProjectAssignment(BaseModel):
    projectId: str
    sequenceId: int


class AssignProjectsRequest(BaseModel):
    userId: str
    projects: List[ProjectAssignment]


@router.post("/assign-projects", status_code=200)
async def assign_projects(request: Request, payload: AssignProjectsRequest = Body(...)):
    """
    Assign projects to a user. Replaces all existing project assignments for the user.
    
    Request body:
    {
        "userId": "user123",
        "projects": [
            {"projectId": "proj1", "sequenceId": 1},
            {"projectId": "proj2", "sequenceId": 2}
        ]
    }
    """
    db = request.app.state.db
    user_id = payload.userId
    projects = payload.projects

    print(f"📦 Assigning {len(projects)} projects to user: {user_id}")

    # Delete all existing assignments for this user
    delete_result = await db.assignedprojects.delete_many({"userId": user_id})
    print(f"🗑️ Deleted {delete_result.deleted_count} existing project assignments")

    # Insert new assignments
    if projects:
        assignments = [
            {
                "userId": user_id,
                "projectId": proj.projectId,
                "sequenceId": proj.sequenceId,
                "created_at": datetime.now()
            }
            for proj in projects
        ]
        
        insert_result = await db.assignedprojects.insert_many(assignments)
        print(f"✅ Inserted {len(insert_result.inserted_ids)} new project assignments")
    
    return {
        "status": "success",
        "message": f"Successfully assigned {len(projects)} projects to user {user_id}",
        "projectCount": len(projects)
    }