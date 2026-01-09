from fastapi import APIRouter, Request, Body, HTTPException
from datetime import datetime
from models import Chat
from agents.learning_agent import run_learning_agent
from bson import ObjectId
from pydantic import BaseModel

router = APIRouter()


class AgentRequest(BaseModel):
    """Simplified request model for agent endpoint"""
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
    The agent will:
    1. Check if user has goals
    2. If no goals, ask them to set goals
    3. If goals exist, fetch project tasks and assign 3 relevant tasks
    4. Return the response
    """
    db = request.app.state.db
    user_id = agent_req.userId

    print(f"🚀 Agent invoked for user: {user_id}")

    # Run the Agent
    try:
        print("⚙️ Running learning agent...")
        result = await run_learning_agent(db, user_id)
        agent_response = result.get("response_text", "I couldn't process your request.")
        status = result.get("status", "error")
        
        print(f"✅ Agent completed with status: {status}")
    except Exception as e:
        print(f"❌ Agent Error: {str(e)}")
        import traceback
        traceback.print_exc()
        agent_response = f"An error occurred: {str(e)}"
        status = "error"

    # Store the agent's response in chat history
    agent_chat_doc = {
        "userId": user_id,
        "userType": "agent",
        "message": agent_response,
        "timestamp": datetime.now()
    }

    result = await db.chats.insert_one(agent_chat_doc)
    print(f"💾 Stored agent response in chat history")

    # Return the serialized agent message
    created_chat = await db.chats.find_one({"_id": result.inserted_id})
    return serialize(created_chat)


@router.get("/history/{user_id}", response_model=list[Chat])
async def get_chat_history(request: Request, user_id: str):
    """Retrieve chat history for a specific user"""
    db = request.app.state.db
    cursor = db.chats.find({"userId": user_id}).sort("timestamp", 1)
    return [serialize(doc) async for doc in cursor]