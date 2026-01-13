from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langsmith import traceable
import os
from dotenv import load_dotenv
from bson import ObjectId

# Load environment variables
load_dotenv()

# LangSmith will automatically trace if environment variables are set
# No additional code needed - just set LANGCHAIN_TRACING_V2=true in .env


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
        
        async def ainvoke(self, user_id: str):
            """Invoke the agent for a specific user."""
            return await run_learning_agent(self.db, user_id)
    
    return SimpleLearningAgent(db)


@traceable(name="Learning Agent", tags=["agent", "task-assignment"])
async def run_learning_agent(db, user_id: str) -> dict:
    """
    Simple learning agent that:
    1. Fetches user goals
    2. Fetches project and tasks
    3. Recommends 3 tasks based on goals
    4. Assigns tasks to user
    
    No complex graphs - just simple tool calling loop.
    """
    try:
        print(f"\n{'='*60}")
        print(f"🚀 Starting learning agent for user: {user_id}")
        print(f"{'='*60}\n")
        
        # Initialize LLM
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found")
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
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
                    # It's a list - process each item
                    for item in goals_data:
                        if item:  # Not None, not empty
                            # Convert to string and strip
                            item_str = str(item).strip()
                            if item_str:  # Not empty after stripping
                                goals.append(item_str)
                
                elif isinstance(goals_data, str):
                    # It's a string - strip and add if not empty
                    stripped = goals_data.strip()
                    if stripped:
                        goals.append(stripped)
                
                elif goals_data:
                    # Unknown type but not None/empty - convert to string
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
        async def assign_task_to_user(user_id: str, task_id: str) -> dict:
            """Assign a task to a user."""
            try:
                print(f"📌 Assigning task {task_id} to {user_id}")
                if not ObjectId.is_valid(task_id):
                    return {"error": "Invalid task ID"}
                
                result = await db.tasks.update_one(
                    {"_id": ObjectId(task_id)},
                    {"$set": {"assigned_to": user_id}}
                )
                
                if result.matched_count == 0:
                    return {"error": f"Task {task_id} not found"}
                
                print(f"✅ Task assigned")
                return {"status": "success", "task_id": task_id, "user_id": user_id}
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                return {"error": str(e)}
        
        # Bind tools to LLM
        tools = [get_user_goals, get_project_details, get_project_tasks, assign_task_to_user]
        llm_with_tools = llm.bind_tools(tools)
        
        print("✅ Tools bound to LLM\n")
        
        # Create the prompt
        system_prompt = """You are an expert learning path advisor with access to tools.

Your task:
1. Use get_user_goals tool to fetch the user's learning goals
2. Use get_project_details tool to fetch project information for project_id: "695caa41c485455f397017ae"
3. Use get_project_tasks tool to fetch ALL tasks for that project
4. Carefully analyze user's learning goals against the project name, description, and each task's title and description
5. Identify exactly 6 tasks in the specific order that creates an incremental learning path (foundation → intermediate → advanced)
6. Use assign_task_to_user tool to assign each of the 6 tasks to the user in the correct learning sequence

RESPONSE FORMAT - After assigning tasks, return ONLY task titles in this exact format:
1. [Task Title 1]
2. [Task Title 2]
3. [Task Title 3]
4. [Task Title 4]
5. [Task Title 5]
6. [Task Title 6]

IMPORTANT RULES:
- Read actual task content (title AND description) before recommending
- Ensure logical progression: easier concepts first, then build complexity
- Match tasks closely to user's stated learning goals
- Foundation task: Basic concepts, prerequisites, introductory material
- Intermediate task: Building on basics, practical application
- Advanced task: Complex topics, integration, real-world projects
- Assign ALL 6 tasks to the user using assign_task_to_user tool
- Return ONLY the 6 task titles as a numbered list in your final response (no explanations)"""

        user_prompt = f"""User ID: {user_id}

Please create my personalized learning path:
1. Fetch my learning goals
2. Fetch project "695caa41c485455f397017ae" and ALL its tasks
3. Analyze which tasks best match my goals
4. Select exactly 6 tasks in order: foundation → intermediate → advanced
5. Assign all 6 tasks to me using assign_task_to_user tool
6. Return ONLY the 6 task titles as a numbered list

Remember: The order matters! Start with foundational concepts, then build up to advanced topics."""

        # Initialize conversation
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        print("📊 Starting tool calling loop...\n")
        
        # Tool calling loop - LLM will call tools until it has the answer
        max_iterations = 15
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            print(f"🔄 Iteration {iteration}")
            
            # Call LLM
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)
            
            # Check if there are tool calls
            if not hasattr(response, 'tool_calls') or not response.tool_calls:
                # No more tool calls - we're done
                print(f"✅ No more tool calls - agent completed\n")
                break
            
            # Execute each tool call
            print(f"🔧 Executing {len(response.tool_calls)} tool call(s)")
            
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]
                
                # Find the tool
                tool_func = next((t for t in tools if t.name == tool_name), None)
                
                if tool_func:
                    # Execute the tool
                    result = await tool_func.ainvoke(tool_args)
                    
                    # Add tool result to messages
                    messages.append(
                        ToolMessage(
                            content=str(result),
                            tool_call_id=tool_id,
                            name=tool_name
                        )
                    )
                else:
                    print(f"❌ Tool {tool_name} not found")
            
            print()  # Empty line for readability
        
        if iteration >= max_iterations:
            print("⚠️  Max iterations reached")
        
        # Extract final response
        final_response = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                # Handle both string and list content from Gemini
                if isinstance(msg.content, str):
                    content_str = msg.content.strip()
                    if content_str:
                        final_response = content_str
                        break
                elif isinstance(msg.content, list):
                    # Content is a list of parts - join them
                    content_parts = []
                    for part in msg.content:
                        if isinstance(part, str):
                            content_parts.append(part)
                        elif hasattr(part, 'text'):
                            content_parts.append(part.text)
                        else:
                            content_parts.append(str(part))
                    content_str = ''.join(content_parts).strip()
                    if content_str:
                        final_response = content_str
                        break
        
        if not final_response:
            final_response = "I processed your request but couldn't generate a final response."
        
        print(f"{'='*60}")
        print(f"✅ Agent completed successfully")
        print(f"{'='*60}\n")
        print(f"Response:\n{final_response}\n")
        
        return {
            "response_text": final_response,
            "status": "success"
        }
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "response_text": f"An error occurred: {str(e)}",
            "status": "error"
        }