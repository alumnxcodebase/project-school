import os
import json
import httpx
import time
import asyncio
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from models.assessment import AssessmentSubmission, TestResultDetails, RunAssessmentRequest
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

router = APIRouter()

# Helper to get DB
def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db

import re

def slugify(text: str) -> str:
    """
    Converts a string to a slug.
    Removes '(Practical)' prefix if present.
    """
    # Remove leading (Practical) case-insensitive
    text = re.sub(r"^\(practical\)\s*", "", text, flags=re.IGNORECASE)
    # Lowercase
    text = text.lower()
    # Replace non-alphanumeric (excluding -) with -
    text = re.sub(r"[^a-z0-9]+", "-", text)
    # Strip leading/trailing dashes
    return text.strip("-")

async def load_assessment_config(task_id: str, db: AsyncIOMotorDatabase):
    """
    Loads the JSON configuration for a specific task.
    Fetches the task from DB to get the title, then slugifies it to find the file.
    """
    # 1. Fetch task from DB
    try:
        # Check 'tasks' collection, then 'assignedprojects' (assignments) if not found?
        # Actually assignment has projectId/taskId referencing the source task.
        # But 'tasks' collection is the source of truth for task definitions.
        
        # Try to find by string ID or ObjectId
        task = await db.tasks.find_one({"_id": ObjectId(task_id)})
        if not task:
            # Fallback for string IDs if relevant
            task = await db.tasks.find_one({"id": task_id})
        
        if not task:
            # Last ditch: maybe the task_id passed IS the slug (for manual testing)
            slug = task_id
        else:
            title = task.get("title") or task.get("name") or ""
            slug = slugify(title)
            
    except Exception:
        # If task_id is not a valid ObjectId, assume it might be a slug or manual ID
        slug = slugify(task_id)

    # 2. Load file
    safe_slug = os.path.basename(slug)
    file_path = os.path.join("data", "assessments", f"{safe_slug}.json")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Assessment configuration not found for task: {slug} (File: {file_path})")
    
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading assessment config: {str(e)}")

def validate_response(expected: dict, actual: dict) -> bool:
    """
    Validates if the actual response matches the expected output.
    Can be enhanced to support complex matching (e.g., ignore order).
    For now, strict equality on 'indices' (sorted).
    """
    # Specific logic for Two Sum (order doesn't matter for the pair, but values must match)
    if "indices" in expected and "indices" in actual:
        return sorted(expected["indices"]) == sorted(actual["indices"])
    
    # Fallback to direct comparison
    return expected == actual

@router.post("/run", response_model=AssessmentSubmission)
async def run_assessment(
    request: RunAssessmentRequest,
    db: AsyncIOMotorDatabase = Depends(get_db)
    # verify_token dependency would normally go here to get userId
):
    # Retrieve User ID from request header (set by frontend/auth middleware) for now, or mock it
    # in a real implementation, we'd extract from JWT.
    # For this implementation, we'll accept a header or assume a test user if not present.
    user_id = "test_user_id" # Replace with actual user extraction logic
    
    # Load config (awaitable now)
    config = await load_assessment_config(request.taskId, db)
    
    test_cases = config.get("test_cases", [])
    
    results = []
    passed_count = 0
    
    async with httpx.AsyncClient() as client:
        for test_case in test_cases:
            start_time = time.time()
            result_detail = TestResultDetails(
                test_case_id=test_case["id"],
                description=test_case["description"],
                status="pending",
                input=test_case["input"],
                expected_output=test_case["expected_output"],
                execution_time_ms=0
            )
            
            try:
                # Prepare request
                response = await client.post(
                    request.studentUrl,
                    json=test_case["input"],
                    timeout=5.0
                )
                
                execution_time = (time.time() - start_time) * 1000
                result_detail.execution_time_ms = round(execution_time, 2)
                
                if response.status_code == 200:
                    actual_output = response.json()
                    result_detail.actual_output = actual_output
                    
                    if validate_response(test_case["expected_output"], actual_output):
                        result_detail.status = "passed"
                        passed_count += 1
                    else:
                        result_detail.status = "failed"
                        result_detail.error_message = f"Expected {test_case['expected_output']}, got {actual_output}"
                else:
                    result_detail.status = "failed"
                    result_detail.error_message = f"HTTP {response.status_code}: {response.text}"
                    
            except httpx.RequestError as e:
                result_detail.status = "error"
                result_detail.error_message = f"Connection error: {str(e)}"
                result_detail.execution_time_ms = round((time.time() - start_time) * 1000, 2)
            except Exception as e:
                result_detail.status = "error"
                result_detail.error_message = f"Unexpected error: {str(e)}"
                result_detail.execution_time_ms = round((time.time() - start_time) * 1000, 2)
            
            results.append(result_detail)
    
    overall_status = "passed" if passed_count == len(test_cases) else "failed"
    score = int((passed_count / len(test_cases)) * 100) if test_cases else 0
    
    submission = AssessmentSubmission(
        userId=user_id,
        taskId=request.taskId,
        endpoint_url=request.studentUrl,
        status=overall_status,
        score=score,
        total_tests=len(test_cases),
        passed_tests=passed_count,
        results=results
    )
    
    # Save to DB
    await db.assessment_submissions.insert_one(submission.model_dump(by_alias=True, exclude={"id"}))
    
    # If passed, update the user's task status to completed
    if overall_status == "passed":
        # Check assignments
        pass # Implement logic to mark assignment as completed

    return submission

@router.get("/history/{task_id}/{user_id}")
async def get_assessment_history(
    task_id: str,
    user_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    cursor = db.assessment_submissions.find(
        {"userId": user_id, "taskId": task_id}
    ).sort("timestamp", -1).limit(10)
    
    history = await cursor.to_list(length=10)
    return history
