from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage
from models import AgentState
import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables first
load_dotenv()


def get_learning_agent(db):
    """
    Create a LangGraph agent that uses Google's Gemini API directly
    to avoid LangChain model compatibility issues.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment variables")

    # Configure Gemini directly - no LangChain wrapper
    genai.configure(api_key=api_key)
    
    # Use the best available model
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        generation_config={
            'temperature': 0.7,
            'top_p': 0.95,
            'top_k': 40,
            'max_output_tokens': 2048,
        }
    )
    
    print("✅ Gemini model initialized: gemini-2.5-flash")

    async def analyze_state(state: AgentState):
        """Fetch user's goals and active tasks from database"""
        user_id = state["userId"]
        
        # Fetch goals
        goals_doc = await db.goals.find_one({"userId": user_id})
        goals = goals_doc["goals"] if goals_doc else []
        
        # Fetch active task (not completed)
        task = await db.tasks.find_one({
            "assigned_to": user_id, 
            "status": {"$ne": "completed"}
        })
        
        print(f"📊 User: {user_id}")
        print(f"   Goals: {goals}")
        print(f"   Active Task: {task['title'] if task else 'None'}")
        
        return {
            "goals": goals,
            "active_task": task
        }

    async def call_model(state: AgentState):
        """Call Gemini API with user context"""
        goals = state.get('goals', [])
        active_task = state.get('active_task')
        user_message = state["message"]
        
        # Build context-aware prompt
        context_parts = [
            "You are a helpful learning mentor and project assistant.",
            "",
            f"**User's Learning Goals:**"
        ]
        
        if goals:
            for i, goal in enumerate(goals, 1):
                context_parts.append(f"{i}. {goal}")
        else:
            context_parts.append("- No goals set yet")
        
        context_parts.append("")
        context_parts.append("**Current Active Task:**")
        
        if active_task:
            context_parts.append(f"- {active_task.get('title', 'Untitled task')}")
            context_parts.append(f"- Status: {active_task.get('status', 'unknown')}")
        else:
            context_parts.append("- No active tasks")
        
        context_parts.extend([
            "",
            "Provide helpful, encouraging, and actionable guidance to help the user achieve their goals.",
            "Keep responses concise but informative.",
            "",
            f"**User asks:** {user_message}"
        ])
        
        prompt = "\n".join(context_parts)
        
        print(f"\n🤖 Calling Gemini API...")
        print(f"Prompt length: {len(prompt)} characters")
        
        try:
            # Call Gemini API
            response = model.generate_content(prompt)
            response_text = response.text
            
            print(f"✅ Response received: {len(response_text)} characters")
            print(f"Preview: {response_text[:100]}...")
            
            return {
                "response_text": response_text,
                "messages": [AIMessage(content=response_text)]
            }
            
        except Exception as e:
            error_msg = f"Error generating response: {str(e)}"
            print(f"❌ {error_msg}")
            
            # Return friendly error message
            fallback_response = (
                "I apologize, but I'm having trouble processing your request right now. "
                "Please try again in a moment."
            )
            
            return {
                "response_text": fallback_response,
                "messages": [AIMessage(content=fallback_response)]
            }

    # Build the workflow graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("analyze", analyze_state)
    workflow.add_node("agent", call_model)
    
    # Define edges
    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "agent")
    workflow.add_edge("agent", END)
    
    print("✅ LangGraph workflow compiled successfully")
    
    return workflow.compile()