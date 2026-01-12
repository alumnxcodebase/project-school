from fastapi import APIRouter, Request, Body, HTTPException
from bson import ObjectId
from typing import List
from models import Resource
from utils.helpers import serialize

router = APIRouter()

@router.get("/", response_model=List[Resource])
async def list_resources(request: Request):
    db = request.app.state.db
    cursor = db.resources.find().sort("created_at", -1)
    return [serialize(doc) async for doc in cursor]

@router.post("/", response_model=Resource, status_code=201)
async def create_resource(request: Request, resource: Resource = Body(...)):
    db = request.app.state.db
    data = resource.model_dump(exclude={"id"})
    result = await db.resources.insert_one(data)
    created = await db.resources.find_one({"_id": result.inserted_id})
    return serialize(created)

@router.get("/{resource_id}", response_model=Resource)
async def get_resource(request: Request, resource_id: str):
    db = request.app.state.db
    if not ObjectId.is_valid(resource_id):
        raise HTTPException(status_code=400, detail="Invalid Resource ID")
    doc = await db.resources.find_one({"_id": ObjectId(resource_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Resource not found")
    return serialize(doc)

@router.put("/{resource_id}", response_model=Resource)
async def update_resource(request: Request, resource_id: str, resource: Resource):
    db = request.app.state.db
    if not ObjectId.is_valid(resource_id):
        raise HTTPException(status_code=400, detail="Invalid Resource ID")
    update_data = {k: v for k, v in resource.model_dump().items() if v is not None}
    update_data.pop("id", None)
    await db.resources.update_one({"_id": ObjectId(resource_id)}, {"$set": update_data})
    updated = await db.resources.find_one({"_id": ObjectId(resource_id)})
    if not updated:
        raise HTTPException(status_code=404, detail="Resource not found")
    return serialize(updated)

@router.delete("/{resource_id}", status_code=204)
async def delete_resource(request: Request, resource_id: str):
    db = request.app.state.db
    if not ObjectId.is_valid(resource_id):
        raise HTTPException(status_code=400, detail="Invalid Resource ID")
    result = await db.resources.delete_one({"_id": ObjectId(resource_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Resource not found")
    return None