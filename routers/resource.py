from fastapi import APIRouter, Request, Body, HTTPException
from models import Resource, ResourceUpdate, UserResourceLink, ResourceResponse
from utils.helpers import serialize
from bson import ObjectId
from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel

router = APIRouter()


class ResourceCommentRequest(BaseModel):
    """Request model for saving resource comments"""
    userId: str
    resourceId: str
    comment: str
    commentBy: Optional[Literal["user", "admin"]] = "user"


@router.post("/", response_model=Resource, status_code=201)
async def create_resource(request: Request, resource: Resource = Body(...)):
    """Create a new learning resource"""
    db = request.app.state.db
    resource_dict = resource.model_dump(exclude={"id"})
    result = await db.resources.insert_one(resource_dict)

    new_resource = await db.resources.find_one({"_id": result.inserted_id})
    return serialize(new_resource)


@router.get("/user/{user_id}", response_model=List[ResourceResponse])
async def get_user_resources(request: Request, user_id: str):
    """
    Get all resources assigned to a user from the resource_assignments collection.
    """
    db = request.app.state.db
    
    # Get user's resource assignment document
    assignment = await db.resource_assignments.find_one({"userId": user_id})
    
    if not assignment or not assignment.get("resources"):
        return []
    
    response_resources = []
    
    for resource_assignment in assignment["resources"]:
        resource_id = resource_assignment["resourceId"]
        
        # Validate ObjectId
        if not ObjectId.is_valid(resource_id):
            continue
        
        # Fetch resource details
        resource = await db.resources.find_one({"_id": ObjectId(resource_id)})
        if not resource:
            continue
        
        # Build response
        resource_response = ResourceResponse(
            resourceId=resource_id,
            name=resource.get("name", ""),
            description=resource.get("description"),
            link=resource.get("link", ""),
            category=resource.get("category", "General"),
            tags=resource.get("tags", []),
            assignedBy=resource_assignment.get("assignedBy", "admin"),
            sequenceId=resource_assignment.get("sequenceId"),
            isCompleted=resource_assignment.get("isCompleted", False),
            comments=resource_assignment.get("comments", [])
        )
        
        response_resources.append(resource_response)
    
    return response_resources


@router.put("/{resource_id}", response_model=Resource)
async def update_resource(request: Request, resource_id: str, update: ResourceUpdate):
    """Update a resource"""
    db = request.app.state.db
    
    if not ObjectId.is_valid(resource_id):
        raise HTTPException(status_code=400, detail="Invalid Resource ID")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    await db.resources.update_one({"_id": ObjectId(resource_id)}, {"$set": update_data})

    updated = await db.resources.find_one({"_id": ObjectId(resource_id)})
    return serialize(updated)


@router.post("/user-resources", status_code=201)
async def link_user_to_resource(request: Request, payload: UserResourceLink = Body(...)):
    """
    Assign a resource to a user by adding it to the resource_assignments collection.
    Creates or updates the user's resource assignment document.
    """
    db = request.app.state.db
    
    # Validate resourceId
    if not ObjectId.is_valid(payload.resourceId):
        raise HTTPException(status_code=400, detail="Invalid resourceId format")
    
    # Verify resource exists
    resource = await db.resources.find_one({"_id": ObjectId(payload.resourceId)})
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    # Create resource assignment object
    resource_assignment = {
        "resourceId": payload.resourceId,
        "assignedBy": payload.assignedBy,
        "sequenceId": payload.sequenceId,
        "isCompleted": False,
        "comments": []
    }
    
    # Update or create assignment document
    result = await db.resource_assignments.update_one(
        {"userId": payload.userId},
        {
            "$addToSet": {"resources": resource_assignment}
        },
        upsert=True
    )
    
    return {
        "status": "success", 
        "message": f"Resource {payload.resourceId} assigned to user {payload.userId}"
    }


@router.put("/user-resources/{user_id}/{resource_id}", status_code=200)
async def update_user_resource_assignment(
    request: Request, 
    user_id: str, 
    resource_id: str,
    isCompleted: Optional[bool] = None,
    sequenceId: Optional[int] = None,
    comment: Optional[str] = None,
    commentBy: Optional[Literal["user", "admin"]] = None
):
    """
    Update a specific resource assignment for a user.
    Can update completion status, sequence, or add comments.
    """
    db = request.app.state.db
    
    update_fields = {}
    
    if isCompleted is not None:
        update_fields["resources.$[elem].isCompleted"] = isCompleted
    
    if sequenceId is not None:
        update_fields["resources.$[elem].sequenceId"] = sequenceId
    
    # Add comment if provided
    if comment and commentBy:
        new_comment = {
            "comment": comment,
            "commentBy": commentBy,
            "createdAt": datetime.now()
        }
        await db.resource_assignments.update_one(
            {"userId": user_id},
            {"$push": {"resources.$[elem].comments": new_comment}},
            array_filters=[{"elem.resourceId": resource_id}]
        )
    
    # Update other fields if any
    if update_fields:
        result = await db.resource_assignments.update_one(
            {"userId": user_id},
            {"$set": update_fields},
            array_filters=[{"elem.resourceId": resource_id}]
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Assignment not found")
    
    return {"status": "success", "message": "Assignment updated"}


@router.post("/rearrange-user-resources", status_code=200)
async def rearrange_user_resources(request: Request, payload: dict = Body(...)):
    """
    Rearrange resources for a user by updating their sequenceId values.
    Accepts a list of resources with updated sequenceIds.
    """
    db = request.app.state.db
    
    user_id = payload.get("userId")
    resources = payload.get("resources", [])
    
    if not user_id:
        raise HTTPException(status_code=400, detail="userId is required")
    
    if not resources:
        raise HTTPException(status_code=400, detail="resources array is required")
    
    # Verify user assignment exists
    assignment = await db.resource_assignments.find_one({"userId": user_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="No assignments found for this user")
    
    # Update sequenceId for each resource
    for resource_update in resources:
        resource_id = resource_update.get("resourceId")
        sequence_id = resource_update.get("sequenceId")
        
        if not resource_id or sequence_id is None:
            continue
        
        # Update the sequenceId for the specific resource in the array
        await db.resource_assignments.update_one(
            {"userId": user_id},
            {"$set": {"resources.$[elem].sequenceId": sequence_id}},
            array_filters=[{"elem.resourceId": resource_id}]
        )
    
    return {
        "status": "success",
        "message": f"Resource order updated for user {user_id}"
    }


@router.post("/delete-user-resource", status_code=200)
async def delete_user_resource(request: Request, payload: dict = Body(...)):
    """
    Delete a resource assignment from a user's resource list.
    Removes the resource from the resource_assignments collection.
    """
    db = request.app.state.db
    
    user_id = payload.get("userId")
    resource_id = payload.get("resourceId")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="userId is required")
    
    if not resource_id:
        raise HTTPException(status_code=400, detail="resourceId is required")
    
    # Verify user assignment exists
    assignment = await db.resource_assignments.find_one({"userId": user_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="No assignments found for this user")
    
    # Remove the resource from the user's resources array
    result = await db.resource_assignments.update_one(
        {"userId": user_id},
        {"$pull": {"resources": {"resourceId": resource_id}}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=404, 
            detail=f"Resource {resource_id} not found in user's assignments"
        )
    
    return {
        "status": "success",
        "message": f"Resource {resource_id} deleted from user {user_id}'s assignments"
    }


@router.post("/resource-comments", status_code=200)
async def save_resource_comment(request: Request, payload: ResourceCommentRequest = Body(...)):
    """
    Save a comment for a specific resource in the resource_assignments collection.
    Adds a new comment to the resource's comments array.
    
    Request body:
    - userId: str (required) - The ID of the user
    - resourceId: str (required) - The ID of the resource
    - comment: str (required) - The comment text
    - commentBy: str (optional) - Either "user" or "admin", defaults to "user"
    """
    db = request.app.state.db
    
    # Validate that comment is not empty after stripping
    if not payload.comment.strip():
        raise HTTPException(status_code=400, detail="comment cannot be empty")
    
    # Verify user assignment exists
    assignment = await db.resource_assignments.find_one({"userId": payload.userId})
    if not assignment:
        raise HTTPException(status_code=404, detail="No assignments found for this user")
    
    # Verify resource exists in user's assignments
    resource_found = any(
        resource.get("resourceId") == payload.resourceId 
        for resource in assignment.get("resources", [])
    )
    if not resource_found:
        raise HTTPException(
            status_code=404, 
            detail=f"Resource {payload.resourceId} not found in user's assignments"
        )
    
    # Create comment object
    new_comment = {
        "comment": payload.comment.strip(),
        "commentBy": payload.commentBy,
        "createdAt": datetime.now()
    }
    
    # Add comment to the resource's comments array
    result = await db.resource_assignments.update_one(
        {"userId": payload.userId},
        {"$push": {"resources.$[elem].comments": new_comment}},
        array_filters=[{"elem.resourceId": payload.resourceId}]
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=500, 
            detail="Failed to save comment"
        )
    
    return {
        "status": "success",
        "message": "Comment saved successfully",
        "comment": new_comment
    }


@router.post("/update-resource-completion-status", status_code=200)
async def update_resource_completion_status(request: Request, payload: dict = Body(...)):
    """
    Update the completion status of a resource in the resource_assignments collection.
    
    Request body:
    - userId: str (required) - The ID of the user
    - resourceId: str (required) - The ID of the resource
    - isCompleted: bool (required) - The completion status (true for completed, false for pending)
    """
    db = request.app.state.db
    
    user_id = payload.get("userId")
    resource_id = payload.get("resourceId")
    is_completed = payload.get("isCompleted")
    
    # Validate required fields
    if not user_id:
        raise HTTPException(status_code=400, detail="userId is required")
    
    if not resource_id:
        raise HTTPException(status_code=400, detail="resourceId is required")
    
    if is_completed is None:
        raise HTTPException(status_code=400, detail="isCompleted is required")
    
    # Verify user assignment exists
    assignment = await db.resource_assignments.find_one({"userId": user_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="No assignments found for this user")
    
    # Verify resource exists in user's assignments
    resource_found = any(
        resource.get("resourceId") == resource_id 
        for resource in assignment.get("resources", [])
    )
    if not resource_found:
        raise HTTPException(
            status_code=404, 
            detail=f"Resource {resource_id} not found in user's assignments"
        )
    
    # Update the resource completion status
    result = await db.resource_assignments.update_one(
        {"userId": user_id},
        {"$set": {"resources.$[elem].isCompleted": is_completed}},
        array_filters=[{"elem.resourceId": resource_id}]
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=500, 
            detail="Failed to update resource completion status"
        )
    
    return {
        "status": "success",
        "message": f"Resource completion status updated to {'completed' if is_completed else 'pending'}",
        "isCompleted": is_completed
    }