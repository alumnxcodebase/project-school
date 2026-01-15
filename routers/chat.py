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
            
            # Get tasks directly from result if they exist
            tasks = result.get("tasks", [])
            print(f"✅ Retrieved {len(tasks)} tasks from agent result")
        
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
    print(f"🔍 MANAGE AGENT REQUEST")
    print(f"🔍 Received userId: {user_id}")
    print(f"🔍 userId type: {type(user_id)}")
    print(f"🔍 userId length: {len(user_id)}")
    print(f"🔍 Agent name: {agent_name}")
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