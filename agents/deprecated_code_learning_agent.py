from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from models import AgentState
import os
from dotenv import load_dotenv
from bson import ObjectId

# Load environment variables first
load_dotenv()


def get_learning_agent(db):
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment variables")

    print(f"🔑 Using API Key: {api_key[:10]}...")

    # Use gemini-2.5-flash with tools
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.7,
        google_api_key=api_key
    )

    print("✅ LLM initialized with model: gemini-2.5-flash")

    # Define tools for the agent
    @tool
    async def get_project_details(project_id: str) -> dict:
        """
        Fetch project details including name, description, and status.
        
        Args:
            project_id: The MongoDB ObjectId of the project as a string
            
        Returns:
            Dictionary with project details
        """
        try:
            project = await db.projects.find_one({"_id": ObjectId(project_id)})
            if not project:
                return {"error": f"Project {project_id} not found"}
            
            return {
                "id": str(project["_id"]),
                "name": project.get("name"),
                "description": project.get("description", "No description"),
                "status": project.get("status"),
                "created_at": str(project.get("created_at"))
            }
        except Exception as e:
            return {"error": str(e)}

    @tool
    async def get_project_tasks(project_id: str) -> list:
        """
        Fetch all tasks for a specific project.
        
        Args:
            project_id: The project ID to fetch tasks for
            
        Returns:
            List of tasks with their details
        """
        try:
            tasks_cursor = db.tasks.find({"project_id": project_id})
            tasks = await tasks_cursor.to_list(length=None)
            
            return [
                {
                    "id": str(task["_id"]),
                    "title": task.get("title"),
                    "status": task.get("status"),
                    "assigned_to": task.get("assigned_to", "Unassigned")
                }
                for task in tasks
            ]
        except Exception as e:
            return [{"error": str(e)}]

    @tool
    async def get_user_goals(user_id: str) -> dict:
        """
        Fetch the learning goals for a specific user.
        
        Args:
            user_id: The user ID to fetch goals for
            
        Returns:
            Dictionary with user goals
        """
        try:
            goals_doc = await db.goals.find_one({"userId": user_id})
            if not goals_doc:
                return {"goals": [], "message": "No goals set"}
            
            goals_data = goals_doc.get("goals", [])
            if isinstance(goals_data, str):
                goals = [goals_data] if goals_data.strip() else []
            elif isinstance(goals_data, list):
                goals = goals_data
            else:
                goals = []
                
            return {"goals": goals}
        except Exception as e:
            return {"error": str(e)}

    @tool
    async def assign_task_to_user(user_id: str, task_id: str) -> dict:
        """
        Assign a specific task to a user by updating the task's assigned_to field.
        
        Args:
            user_id: The user ID to assign the task to
            task_id: The task ID (MongoDB ObjectId as string) to assign
            
        Returns:
            Dictionary with assignment status
        """
        try:
            if not ObjectId.is_valid(task_id):
                return {"error": "Invalid task ID format"}
            
            result = await db.tasks.update_one(
                {"_id": ObjectId(task_id)},
                {"$set": {"assigned_to": user_id}}
            )
            
            if result.matched_count == 0:
                return {"error": f"Task {task_id} not found"}
            
            return {
                "status": "success",
                "message": f"Task {task_id} assigned to user {user_id}",
                "task_id": task_id,
                "user_id": user_id
            }
        except Exception as e:
            return {"error": str(e)}

    # Bind tools to LLM
    tools = [get_project_details, get_project_tasks, get_user_goals, assign_task_to_user]
    llm_with_tools = llm.bind_tools(tools)

    async def analyze_state(state: AgentState):
        """Supervisor Node: Analyzes user state and fetches goals"""
        user_id = state["userId"]
        goals_doc = await db.goals.find_one({"userId": user_id})

        # Handle goals - can be either string or list from backend
        goals = []
        if goals_doc and "goals" in goals_doc:
            goals_data = goals_doc["goals"]
            if isinstance(goals_data, str):
                goals = [goals_data] if goals_data.strip() else []
            elif isinstance(goals_data, list):
                goals = goals_data
            else:
                goals = []

        print(f"📊 Analyzed state for user: {user_id}")
        print(f"   Goals parsed: {goals}")

        return {
            "goals": goals,
            "active_task": None
        }

    def check_goals(state: AgentState) -> str:
        """Conditional routing: Check if user has goals"""
        goals = state.get('goals', [])
        
        if not goals or len(goals) == 0:
            print("⚠️ No goals found - routing to no_goals")
            return "without_goals"
        else:
            print(f"✅ Found {len(goals)} goal(s) - routing to agent")
            return "with_goals"

    async def call_agent(state: AgentState):
        """Agent node: LLM decides which tools to use"""
        user_id = state["userId"]
        goals = state.get('goals', [])
        
        # Format goals
        if len(goals) == 1:
            goal_text = goals[0]
        else:
            goal_text = '\n'.join(f"{i+1}. {goal}" for i, goal in enumerate(goals))

        system_msg = """You are an expert learning path advisor with access to tools.

Your task:
1. Use get_project_details tool to fetch project information for project_id: "695caa41c485455f397017ae"
2. Use get_project_tasks tool to fetch ALL tasks for that project
3. Analyze user's learning goals against project name, description, and each task's title/description
4. Identify exactly 3 tasks in the specific order that creates an incremental learning path (foundation → intermediate → advanced)
5. Use assign_task_to_user tool to assign each of the 3 tasks to the user in the correct learning sequence

RESPONSE FORMAT - After assigning tasks, return ONLY task titles in this exact format:
1. [Task Title 1]
2. [Task Title 2]
3. [Task Title 3]

IMPORTANT:
- Read actual content before recommending
- Ensure logical progression (easier → harder)
- Assign all 3 tasks to the user using assign_task_to_user tool
- Return ONLY the 3 task titles as a numbered list in your final response"""

        user_prompt = f"""User ID: {user_id}

User's Learning Goals:
{goal_text}

Fetch project and tasks for "695caa41c485455f397017ae", identify the top 3 tasks for my learning path, assign them to me using assign_task_to_user tool, then return ONLY the 3 task titles as a numbered list."""

        messages = state.get("messages", [])
        messages = [
            SystemMessage(content=system_msg),
            HumanMessage(content=user_prompt)
        ] + messages

        print(f"🤖 Agent starting with {len(tools)} tools available...")

        return {"messages": messages}

    async def call_model(state: AgentState):
        """Call LLM with tools"""
        messages = state["messages"]
        
        print(f"💭 Calling LLM with {len(messages)} messages...")
        response = await llm_with_tools.ainvoke(messages)
        print(f"📝 LLM response type: {type(response)}")
        
        return {"messages": [response]}

    async def execute_tools(state: AgentState):
        """Execute tool calls from LLM response"""
        messages = state["messages"]
        last_message = messages[-1]
        
        print(f"🔧 Checking for tool calls...")
        
        if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
            print("   No tool calls found")
            return {"messages": []}
        
        print(f"   Found {len(last_message.tool_calls)} tool call(s)")
        
        tool_messages = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            print(f"   Executing: {tool_name}({tool_args})")
            
            # Find and execute the tool
            tool_func = None
            for t in tools:
                if t.name == tool_name:
                    tool_func = t
                    break
            
            if tool_func:
                result = await tool_func.ainvoke(tool_args)
                print(f"   ✅ Result: {str(result)[:100]}...")
                
                tool_messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_id,
                        name=tool_name
                    )
                )
            else:
                print(f"   ❌ Tool {tool_name} not found")
        
        return {"messages": tool_messages}

    def should_continue(state: AgentState) -> str:
        """Decide if agent should continue or finish"""
        messages = state["messages"]
        last_message = messages[-1]
        
        # If LLM made tool calls, continue to execute them
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            print("🔄 Tool calls detected, continuing to execute_tools")
            return "continue"
        
        # Otherwise, we're done
        print("✅ No more tool calls, finishing")
        return "end"

    async def format_response(state: AgentState):
        """Format final response for user - excludes extras/debug info"""
        messages = state["messages"]
        
        # Find the last AI message with actual content
        response_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                response_content = msg.content
                break
        
        if not response_content:
            response_content = "I've analyzed your goals and project, but couldn't generate a proper response."
        
        print(f"📊 Final response: {response_content[:100]}...")
        
        # Return only response_text, excluding messages and other debug info
        return {
            "response_text": response_content
        }

    async def no_goals_handler(state: AgentState):
        """Handle case when user has no goals set"""
        no_goals_message = (
            "I noticed you haven't set any goals yet. "
            "To get started, please set your learning goals first. "
            "You can do this by using the goals endpoint to define what you want to achieve!"
        )
        
        print("📝 Returning no goals message")
        
        # Return only response_text, excluding messages
        return {
            "response_text": no_goals_message
        }

    # Build the workflow graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("supervisor", analyze_state)
    workflow.add_node("agent", call_agent)
    workflow.add_node("call_model", call_model)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("format_response", format_response)
    workflow.add_node("no_goals", no_goals_handler)
    
    # Set entry point
    workflow.set_entry_point("supervisor")
    
    # Add conditional edge from supervisor
    workflow.add_conditional_edges(
        "supervisor",
        check_goals,
        {
            "without_goals": "no_goals",
            "with_goals": "agent"
        }
    )
    
    # Agent workflow
    workflow.add_edge("agent", "call_model")
    
    # Add conditional edge after model call
    workflow.add_conditional_edges(
        "call_model",
        should_continue,
        {
            "continue": "execute_tools",
            "end": "format_response"
        }
    )
    
    # After executing tools, call model again
    workflow.add_edge("execute_tools", "call_model")
    
    # End edges
    workflow.add_edge("format_response", END)
    workflow.add_edge("no_goals", END)

    print("🔄 Agentic workflow compiled successfully with tool support")
    return workflow.compile()