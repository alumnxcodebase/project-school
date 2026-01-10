from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langsmith import traceable
import os
from dotenv import load_dotenv
from bson import ObjectId

# Load environment variables
load_dotenv()


async def handle_agent_name_update(db, user_id: str, message: str) -> str:
    """
    Handle agent name update messages.
    Extracts the agent name from the message and returns a personalized greeting.
    
    Expected message format: "Updated the name of the agent to <agent_name>"
    Returns: "Hello! I'm <agent_name>. How can I help you today?"
    """
    try:
        print(f"🔄 Processing agent name update for user: {user_id}")
        print(f"📝 Message: {message}")
        
        # Extract agent name from the message
        # Format: "Updated the name of the agent to <agent_name>"
        prefix = "Updated the name of the agent to "
        
        if message.startswith(prefix):
            agent_name = message[len(prefix):].strip()
            print(f"✅ Extracted agent name: {agent_name}")
            
            # Create personalized greeting
            greeting = f"Hello! I'm {agent_name}. How can I help you today?"
            print(f"💬 Generated greeting: {greeting}")
            
            return greeting
        else:
            print("⚠️ Message format didn't match expected pattern")
            return "Hello! How can I help you today?"
            
    except Exception as e:
        print(f"❌ Error in handle_agent_name_update: {str(e)}")
        import traceback
        traceback.print_exc()
        return "Hello! How can I help you today?"


def get_learning_agent(db):
    """
    Initialize and return the learning agent.
    This function exists for compatibility with your existing code.
    
    Returns a simple object that can be invoked.
    """
    print("✅ Learning agent initialized")
    
    # Return a simple callable that wraps run_learning_agent
    class SimpleLearningAgent:
        def __init__(self, database):
            self.db = database
        
        async def ainvoke(self, user_id: str, message: str = None):
            """Invoke the agent for a specific user."""
            return await run_learning_agent(self.db, user_id, message)
    
    return SimpleLearningAgent(db)


@traceable(name="Learning Agent", tags=["agent", "career-guidance"])
async def run_learning_agent(db, user_id: str, user_message: str = None) -> dict:
    """
    Agentic learning assistant that:
    1. Answers career and growth questions conversationally
    2. Provides personalized task recommendations based on goals
    3. Handles general career guidance queries
    
    Args:
        db: Database connection
        user_id: User identifier
        user_message: Optional message from user. If "Updated the goals. Share the revised tasks.", 
                     triggers task assignment mode. Otherwise, conversational mode.
    """
    try:
        print(f"\n{'='*60}")
        print(f"🚀 Starting learning agent for user: {user_id}")
        print(f"📝 User message: {user_message}")
        print(f"{'='*60}\n")
        
        # Get agent name for personalized responses
        agent_doc = await db.agents.find_one({"userId": user_id})
        agent_name = agent_doc.get("agentName", "Study Buddy") if agent_doc else "Study Buddy"
        print(f"🤖 Agent name: {agent_name}")
        
        # Initialize LLM
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found")
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-exp",
            temperature=0.7,
            google_api_key=api_key
        )
        
        print("✅ LLM initialized")
        
        # Define tools
        @tool
        async def get_user_goals(user_id: str) -> dict:
            """Fetch the learning goals for a specific user."""
            try:
                print(f"🔍 Fetching goals for user: {user_id}")
                goals_doc = await db.goals.find_one({"userId": user_id})
                if not goals_doc:
                    return {"goals": [], "message": "No goals set"}
                
                goals_data = goals_doc.get("goals", [])
                print(f"   Raw goals_data type: {type(goals_data)}")
                print(f"   Raw goals_data: {goals_data}")
                
                # Robust parsing - handle any data type
                goals = []
                
                if isinstance(goals_data, list):
                    for item in goals_data:
                        if item:
                            item_str = str(item).strip()
                            if item_str:
                                goals.append(item_str)
                
                elif isinstance(goals_data, str):
                    stripped = goals_data.strip()
                    if stripped:
                        goals.append(stripped)
                
                elif goals_data:
                    goals.append(str(goals_data))
                
                print(f"✅ Parsed {len(goals)} goal(s): {goals}")
                return {"goals": goals}
                
            except Exception as e:
                print(f"❌ Error in get_user_goals: {str(e)}")
                import traceback
                traceback.print_exc()
                return {"error": str(e)}
        
        @tool
        async def get_project_details(project_id: str) -> dict:
            """Fetch project details including name, description, and status."""
            try:
                print(f"🔍 Fetching project: {project_id}")
                project = await db.projects.find_one({"_id": ObjectId(project_id)})
                if not project:
                    return {"error": f"Project {project_id} not found"}
                
                result = {
                    "id": str(project["_id"]),
                    "name": project.get("name"),
                    "description": project.get("description", "No description"),
                    "status": project.get("status")
                }
                print(f"✅ Project found: {result['name']}")
                return result
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                return {"error": str(e)}
        
        @tool
        async def get_project_tasks(project_id: str) -> list:
            """Fetch all tasks for a specific project."""
            try:
                print(f"🔍 Fetching tasks for project: {project_id}")
                tasks_cursor = db.tasks.find({"project_id": project_id})
                tasks = await tasks_cursor.to_list(length=None)
                
                result = [
                    {
                        "id": str(task["_id"]),
                        "title": task.get("title"),
                        "description": task.get("description", "No description"),
                        "status": task.get("status")
                    }
                    for task in tasks
                ]
                print(f"✅ Found {len(result)} tasks")
                return result
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                return [{"error": str(e)}]
        
        @tool
        async def get_user_assigned_tasks(user_id: str) -> dict:
            """Fetch all tasks already assigned to the user (both completed and pending)."""
            try:
                print(f"🔍 Fetching assigned tasks for user: {user_id}")
                assignment = await db.assignments.find_one({"userId": user_id})
                
                if not assignment or not assignment.get("tasks"):
                    print("✅ No tasks assigned to user yet")
                    return {"assigned_task_ids": [], "completed_task_ids": []}
                
                assigned_task_ids = []
                completed_task_ids = []
                
                for task in assignment.get("tasks", []):
                    task_id = task.get("taskId")
                    if task_id:
                        assigned_task_ids.append(task_id)
                        if task.get("isCompleted", False):
                            completed_task_ids.append(task_id)
                
                print(f"✅ User has {len(assigned_task_ids)} assigned tasks ({len(completed_task_ids)} completed)")
                return {
                    "assigned_task_ids": assigned_task_ids,
                    "completed_task_ids": completed_task_ids
                }
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                return {"error": str(e), "assigned_task_ids": [], "completed_task_ids": []}
        
        # Determine mode based on user message
        is_task_assignment_mode = (
            user_message and 
            ("updated the goals" in user_message.lower() or 
             "share the revised tasks" in user_message.lower() or
             "share tasks" in user_message.lower())
        )
        
        if is_task_assignment_mode:
            print("🎯 MODE: Task Assignment")
            tools = [get_user_goals, get_project_details, get_project_tasks, get_user_assigned_tasks]
            
            system_prompt = f"""You are {agent_name}, an expert learning path advisor.

Your task:
1. Use get_user_goals to fetch the user's learning goals
2. Use get_user_assigned_tasks to fetch tasks already assigned to the user
3. Use get_project_details for project_id: "695caa41c485455f397017ae"
4. Use get_project_tasks to fetch ALL tasks from the project
5. Filter OUT any tasks whose ID appears in the assigned_task_ids list
6. From the remaining UNASSIGNED tasks, select exactly 6 tasks
7. Analyze user goals vs the unassigned tasks (title + description)
8. Select tasks in progressive order (foundation → intermediate → advanced)

CRITICAL RULES:
- NEVER recommend tasks that are already in assigned_task_ids
- ONLY suggest tasks from the project that the user has NOT been assigned yet
- Select exactly 6 NEW tasks that match user's goals
- Ensure logical learning progression

RESPONSE FORMAT - Return ONLY task titles as a numbered list:
1. [Task Title 1]
2. [Task Title 2]
3. [Task Title 3]
4. [Task Title 4]
5. [Task Title 5]
6. [Task Title 6]

No explanations, just the numbered list of NEW tasks."""

            user_prompt = f"""User ID: {user_id}

Create my personalized learning path with NEW tasks only:
1. Fetch my learning goals
2. Fetch my already assigned tasks (to exclude them)
3. Fetch project and all tasks
4. Filter out any tasks I already have assigned
5. From remaining tasks, select 6 that match my goals in learning order
6. Return ONLY the numbered list of task titles"""
            
        else:
            print("💬 MODE: Conversational Career Guidance")
            tools = [get_user_goals]
            
            system_prompt = f"""You are {agent_name}, a friendly and knowledgeable career advisor specializing in AI/ML, Data Science, and tech careers.

YOUR EXPERTISE:
- Career roadmaps (AI/ML, Data Science, Software Engineering)
- Learning paths and skill development
- Industry trends and job market insights
- Project recommendations
- Resume and interview guidance
- Career transitions and upskilling

CONVERSATION STYLE:
- Warm, encouraging, and professional
- Provide specific, actionable advice
- Use examples and real-world insights
- Be honest about timelines and effort required

BOUNDARIES:
You can answer questions about:
✅ Career paths in tech (AI/ML, Data Science, Software Engineering)
✅ Learning roadmaps and skill development
✅ Project ideas and portfolio building
✅ Industry trends and job opportunities
✅ Interview preparation and resume tips
✅ Course and certification recommendations

For questions OUTSIDE these topics (personal problems, non-tech careers, medical/legal advice, etc.):
❌ Politely decline and say: "I'm {agent_name}, focused on tech career growth. For other matters, please contact Vijender P at support@alumnx.com"

IMPORTANT:
- Use get_user_goals tool to understand user's current goals
- Reference their goals in your advice when relevant
- Keep responses concise (2-3 paragraphs max)
- End with a follow-up question to continue the conversation"""

            if user_message:
                user_prompt = f"""User message: {user_message}

User ID: {user_id}

Please respond to the user's question. First, fetch their learning goals to provide personalized advice."""
            else:
                user_prompt = f"""User ID: {user_id}

The user has just updated their goals. Fetch their goals and provide an encouraging welcome message about their learning journey."""
        
        print("🤖 Creating LangGraph ReAct agent...\n")
        
        # Create the ReAct agent
        agent = create_react_agent(llm, tools)
        
        print("✅ Agent created\n")
        print("📄 Running agent...\n")
        
        # Run the agent
        result = await agent.ainvoke({
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
        })
        
        print("✅ Agent execution completed\n")
        
        # Extract final response
        final_message = result["messages"][-1]
        final_response = final_message.content if hasattr(final_message, 'content') else str(final_message)
        
        # Handle list content from Gemini
        if isinstance(final_response, list):
            content_parts = []
            for part in final_response:
                if isinstance(part, str):
                    content_parts.append(part)
                elif hasattr(part, 'text'):
                    content_parts.append(part.text)
                else:
                    content_parts.append(str(part))
            final_response = ''.join(content_parts).strip()
        
        print(f"{'='*60}")
        print(f"✅ Agent completed successfully")
        print(f"{'='*60}\n")
        print(f"Response:\n{final_response}\n")
        
        return {
            "response_text": final_response,
            "status": "success",
            "messages": result["messages"]
        }
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "response_text": f"An error occurred: {str(e)}",
            "status": "error"
        }