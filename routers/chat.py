from fastapi import APIRouter, Request, Body, HTTPException
from datetime import datetime
from models import Chat, AgentState
from langchain_core.messages import HumanMessage
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
    Invoke the LangGraph agent workflow with just userId.
    The agent will check goals and either:
    - Return a message asking user to set goals (if no goals)
    - Return a summary of goals (if goals exist)
    """
    db = request.app.state.db
    agent = request.app.state.agent
    user_id = agent_req.userId

    print(f"🚀 Agent invoked for user: {user_id}")

    # Prepare the initial state for LangGraph
    initial_state = {
        "userId": user_id,
        "message": "",  # No user message in this workflow
        "messages": [],  # Empty initially
        "goals": [],  # Will be populated by the 'supervisor' node
        "active_task": None,
        "response_text": ""
    }

    # Run the Agent Workflow
    try:
        print("⚙️ Invoking LangGraph workflow...")
        final_state = await agent.ainvoke(initial_state)
        print("✅ Workflow completed successfully")
    except Exception as e:
        print(f"❌ Agent Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Agent Error: {str(e)}")

    # Extract the agent's response
    agent_response = final_state.get("response_text", "I'm sorry, I couldn't process that.")

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