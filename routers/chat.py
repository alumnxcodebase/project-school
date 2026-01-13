from fastapi import APIRouter, Request, Body, HTTPException
from datetime import datetime
from models import Chat
from agents.learning_agent import run_learning_agent, handle_agent_name_update
from bson import ObjectId
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter()


class AgentRequest(BaseModel):
    """Simplified request model for agent endpoint"""
    userId: str
    message: Optional[str] = None


class ManageAgentRequest(BaseModel):
    """Request model for managing agent name"""
    userId: str
    agentName: str


class GetAgentRequest(BaseModel):
    """Request model for getting agent details"""
    userId: str


def serialize(doc):
    """Helper to convert MongoDB _id to string id"""
    if not doc: 
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


def parse_agent_response_to_tasks(response_text: str) -> List[Dict[str, Any]]:
    """
    Parse the agent's response text to extract tasks.
    Expected format: numbered list like "1. Task description 2. Another task..."
    Returns a list of task objects with taskId and name.
    """
    tasks = []
    
    # Split by newlines first to handle multi-line format
    lines = response_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Try to match numbered format: "1. Task name" or "1) Task name"
        import re
        match = re.match(r'^(\d+)[.\)]\s*(.+)$', line)
        
        if match:
            task_number = match.group(1)
            task_description = match.group(2).strip()
            
            # Generate a taskId (you might want to use actual task IDs from your database)
            # For now, using a simple format: "suggested_task_{number}"
            task_id = f"suggested_task_{task_number}"
            
            tasks.append({
                "taskId": task_id,
                "name": task_description,
                "isSuggested": True  # Flag to indicate this is an AI-suggested task
            })
    
    # Fallback: if no numbered items found, try splitting by common delimiters
    if not tasks:
        # Try splitting by numbers followed by period/parenthesis
        parts = re.split(r'\d+[.\)]\s*', response_text)
        for i, part in enumerate(parts[1:], 1):  # Skip first empty part
            if part.strip():
                tasks.append({
                    "taskId": f"suggested_task_{i}",
                    "name": part.strip(),
                    "isSuggested": True
                })
    
    return tasks


@router.post("/agent", status_code=200)
async def chat_with_agent(request: Request, agent_req: AgentRequest = Body(...)):
    """
    Invoke the learning agent for a user.
    Accepts optional message parameter for conversational queries or task updates.
    Returns both a message and a structured tasks array for UI rendering.
    """
    db = request.app.state.db
    user_id = agent_req.userId
    message = agent_req.message

    print(f"🚀 Agent invoked for user: {user_id}")
    if message:
        print(f"📝 With message: {message}")

    try:
        # Check if this is an agent name update message
        if message and message.startswith("Updated the name of the agent to "):
            print("🔄 Detected agent name update message")
            agent_response = await handle_agent_name_update(db, user_id, message)
            status = "success"
            tasks = []  # No tasks for name update
        else:
            # Regular learning agent invocation with optional message
            print("⚙️ Running learning agent...")
            result = await run_learning_agent(db, user_id, message)
            agent_response = result.get("response_text", "I couldn't process your request.")
            status = result.get("status", "error")
            
            # Parse the response to extract tasks only if it looks like a task list
            print("🔍 Parsing response for tasks...")
            if _is_task_list_response(agent_response):
                tasks = parse_agent_response_to_tasks(agent_response)
                print(f"✅ Extracted {len(tasks)} tasks from response")
            else:
                tasks = []
                print("ℹ️ Response is conversational (no tasks to extract)")
        
        print(f"✅ Agent completed with status: {status}")
    except Exception as e:
        print(f"❌ Agent Error: {str(e)}")
        import traceback
        traceback.print_exc()
        agent_response = f"An error occurred: {str(e)}"
        status = "error"
        tasks = []

    # Store agent chat in database
    agent_chat_doc = {
        "userId": user_id,
        "userType": "agent",
        "message": agent_response,
        "timestamp": datetime.now()
    }

    result = await db.chats.insert_one(agent_chat_doc)
    print(f"💾 Stored agent response in chat history")

    created_chat = await db.chats.find_one({"_id": result.inserted_id})
    
    # Return structured response with both message and tasks
    return {
        **serialize(created_chat),
        "tasks": tasks,  # Add tasks array to response
        "status": status
    }


def _is_task_list_response(text: str) -> bool:
    """Check if response looks like a task list (has numbered items)"""
    lines = text.strip().split('\n')
    numbered_lines = [l for l in lines if l.strip() and l.strip()[0].isdigit()]
    return len(numbered_lines) >= 3  # At least 3 numbered items


@router.get("/history/{user_id}")
async def get_chat_history(request: Request, user_id: str):
    """Retrieve chat history for a specific user"""
    db = request.app.state.db
    cursor = db.chats.find({"userId": user_id}).sort("timestamp", 1)
    return [serialize(doc) async for doc in cursor]


@router.post("/manage-agent", status_code=200)
async def manage_agent(request: Request, agent_req: ManageAgentRequest = Body(...)):
    """
    Create or update agent name for a user.
    """
    db = request.app.state.db
    user_id = agent_req.userId
    agent_name = agent_req.agentName

    print("=" * 80)
    print(f"📝 MANAGE AGENT REQUEST")
    print(f"📝 Received userId: {user_id}")
    print(f"📝 userId type: {type(user_id)}")
    print(f"📝 userId length: {len(user_id)}")
    print(f"📝 Agent name: {agent_name}")
    print("=" * 80)

    # Validate agent name
    if not agent_name or not agent_name.strip():
        raise HTTPException(status_code=400, detail="Agent name cannot be empty")

    # Check for existing agents with this userId
    print(f"🔍 Searching for existing agent with userId: {user_id}")
    existing_agent = await db.agents.find_one({"userId": user_id})
    
    if existing_agent:
        print(f"✅ Found existing agent:")
        print(f"   - _id: {existing_agent.get('_id')}")
        print(f"   - userId: {existing_agent.get('userId')}")
        print(f"   - agentName: {existing_agent.get('agentName')}")
        print(f"   - updated_at: {existing_agent.get('updated_at')}")
    else:
        print(f"❌ No existing agent found for userId: {user_id}")
        
        # Check if there are any agents at all for debugging
        all_agents_count = await db.agents.count_documents({})
        print(f"📊 Total agents in collection: {all_agents_count}")
        
        if all_agents_count > 0:
            print(f"🔍 Checking all existing userIds in agents collection:")
            all_agents = await db.agents.find({}, {"userId": 1, "agentName": 1}).to_list(length=10)
            for ag in all_agents:
                print(f"   - userId: '{ag.get('userId')}' (type: {type(ag.get('userId'))}), agentName: '{ag.get('agentName')}'")

    # Upsert agent document
    print(f"💾 Performing upsert for userId: {user_id}")
    result = await db.agents.update_one(
        {"userId": user_id},
        {
            "$set": {
                "agentName": agent_name.strip(),
                "updated_at": datetime.now()
            },
            "$setOnInsert": {
                "created_at": datetime.now()
            }
        },
        upsert=True
    )

    print(f"💾 Upsert result:")
    print(f"   - matched_count: {result.matched_count}")
    print(f"   - modified_count: {result.modified_count}")
    print(f"   - upserted_id: {result.upserted_id}")

    # Fetch the updated/created agent
    agent = await db.agents.find_one({"userId": user_id})
    
    if agent:
        print(f"✅ Final agent state:")
        print(f"   - _id: {agent.get('_id')}")
        print(f"   - userId: {agent.get('userId')}")
        print(f"   - agentName: {agent.get('agentName')}")
    else:
        print(f"❌ WARNING: Could not retrieve agent after upsert!")
    
    action = "updated" if result.modified_count > 0 else "created"
    print(f"✅ Agent {action} successfully")
    print("=" * 80)
    
    return {
        "status": "success",
        "message": f"Agent name {action} successfully",
        "agent": serialize(agent)
    }


@router.post("/get-agent", status_code=200)
async def get_agent(request: Request, agent_req: GetAgentRequest = Body(...)):
    """
    Get agent details for a specific user.
    """
    db = request.app.state.db
    user_id = agent_req.userId

    print("=" * 80)
    print(f"🔍 GET AGENT REQUEST")
    print(f"🔍 Received userId: {user_id}")
    print(f"🔍 userId type: {type(user_id)}")
    print(f"🔍 userId length: {len(user_id)}")
    print("=" * 80)

    # Find agent document
    agent = await db.agents.find_one({"userId": user_id})
    
    if not agent:
        print(f"❌ No agent found for userId: {user_id}")
        
        # Debug: show what userIds exist
        all_agents_count = await db.agents.count_documents({})
        print(f"📊 Total agents in collection: {all_agents_count}")
        
        if all_agents_count > 0:
            print(f"🔍 Existing userIds in agents collection:")
            all_agents = await db.agents.find({}, {"userId": 1, "agentName": 1}).to_list(length=10)
            for ag in all_agents:
                print(f"   - userId: '{ag.get('userId')}' (type: {type(ag.get('userId'))})")
        
        # Return default agent name if not found
        return {
            "status": "success",
            "agent": {
                "userId": user_id,
                "agentName": "Study Buddy",
                "isDefault": True
            }
        }
    
    print(f"✅ Agent found:")
    print(f"   - _id: {agent.get('_id')}")
    print(f"   - userId: {agent.get('userId')}")
    print(f"   - agentName: {agent.get('agentName')}")
    print("=" * 80)
    
    return {
        "status": "success",
        "agent": serialize(agent)
    }