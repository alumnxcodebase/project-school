from fastapi import APIRouter, Request, Body, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId
from utils.helpers import serialize

router = APIRouter()


class Resource(BaseModel):
    """Request and Response model for learning resources"""
    id: Optional[str] = None
    name: str
    description: str
    link: str


@router.post("/", response_model=Resource, status_code=201)
async def create_resource(request: Request, resource: Resource = Body(...)):
    """
    Create a new learning resource.
    
    Example payload:
    {
        "name": "Video to Fork a Repo",
        "description": "This resource is for helping you to fork a repo from Github",
        "link": "https://youtube.com/wkeljrew"
    }
    """
    db = request.app.state.db
    resource_dict = resource.model_dump(exclude={"id"})
    result = await db.resources.insert_one(resource_dict)

    new_resource = await db.resources.find_one({"_id": result.inserted_id})
    return serialize(new_resource)


@router.get("/", response_model=List[Resource])
async def get_all_resources(request: Request):
    """
    Get all learning resources.
    """
    db = request.app.state.db
    
    resources_cursor = db.resources.find({})
    resources = await resources_cursor.to_list(length=1000)
    
    return [serialize(resource) for resource in resources]


@router.get("/{resource_id}", response_model=Resource)
async def get_resource_by_id(request: Request, resource_id: str):
    """
    Get a specific resource by ID.
    """
    db = request.app.state.db
    
    if not ObjectId.is_valid(resource_id):
        raise HTTPException(status_code=400, detail="Invalid resource ID")
    
    resource = await db.resources.find_one({"_id": ObjectId(resource_id)})
    
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    return serialize(resource)


@router.put("/{resource_id}", response_model=Resource)
async def update_resource(request: Request, resource_id: str, resource: Resource = Body(...)):
    """
    Update an existing resource.
    """
    db = request.app.state.db
    
    if not ObjectId.is_valid(resource_id):
        raise HTTPException(status_code=400, detail="Invalid resource ID")
    
    update_data = {k: v for k, v in resource.model_dump(exclude={"id"}).items() if v is not None}
    
    await db.resources.update_one(
        {"_id": ObjectId(resource_id)},
        {"$set": update_data}
    )
    
    updated_resource = await db.resources.find_one({"_id": ObjectId(resource_id)})
    
    if not updated_resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    return serialize(updated_resource)


@router.delete("/{resource_id}", status_code=200)
async def delete_resource(request: Request, resource_id: str):
    """
    Delete a resource by ID.
    """
    db = request.app.state.db
    
    if not ObjectId.is_valid(resource_id):
        raise HTTPException(status_code=400, detail="Invalid resource ID")
    
    result = await db.resources.delete_one({"_id": ObjectId(resource_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    return {
        "status": "success",
        "message": f"Resource {resource_id} deleted successfully"
    }