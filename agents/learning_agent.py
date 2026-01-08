from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool as langchain_tool
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

    @langchain_tool
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

    @langchain_tool
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

    @langchain_tool
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


    @langchain_tool
    async def create_tasks_from_goals(user_id: str, project_id: str, goals_text: str) -> dict:

        """
        Analyze existing project tasks, identify top 2 relevant ones, and create new tasks based on user goals.
        
        Args:
            user_id: The user ID to assign the new tasks to
            project_id: The project ID where tasks will be created
            goals_text: User learning goals as comma-separated text like 'Learn Python,Build APIs,Master MongoDB'
            
        Returns:
            Dictionary with top relevant tasks and newly created tasks
        """
        try:
            print(f"🚀 create_tasks_from_goals called!")
            print(f"   user_id: {user_id}")
            print(f"   project_id: {project_id}")
            print(f"   goals_text: {goals_text}")
            
            # Parse goals from comma-separated string
            user_goals = [g.strip() for g in goals_text.split(',') if g.strip()]
            print(f"   Parsed {len(user_goals)} goals: {user_goals}")
            
            # Step 1: Fetch all existing tasks for the project
            tasks_cursor = db.tasks.find({"project_id": project_id})
            existing_tasks = await tasks_cursor.to_list(length=None)
            
            print(f"   Found {len(existing_tasks)} existing tasks in project")
            
            if not existing_tasks:
                return {
                    "success": False,
                    "message": "No existing tasks found in project",
                    "created_tasks": [],
                    "top_relevant_tasks": []
                }
            
            # Step 2: Pick top 2 relevant tasks
            
            top_relevant_tasks = existing_tasks[:min(2, len(existing_tasks))]
            
            print(f"   Selected top {len(top_relevant_tasks)} relevant tasks:")
            for task in top_relevant_tasks:
                print(f"      - {task.get('title')}")
            
            # Step 3: Create new tasks based on each goal
            new_tasks = []
            
            for i, goal in enumerate(user_goals):
                print(f"   Creating task {i+1}/{len(user_goals)} for goal: {goal}")
                
                # Prepare task document
                task_doc = {
                    "project_id": project_id,
                    "title": f"Learn: {goal}",
                    "status": "pending",
                    "assigned_to": user_id,
                    "description": f"Task automatically created from learning goal: {goal}",
                    "created_by": "agent",
                    "priority": "medium"
                }
                
                # Insert into MongoDB
                result = await db.tasks.insert_one(task_doc)
                print(f"      ✅ Inserted task with ID: {result.inserted_id}")
                
                # Fetch back the created task
                created_task = await db.tasks.find_one({"_id": result.inserted_id})
                
                # Add to results
                new_tasks.append({
                    "id": str(created_task["_id"]),
                    "title": created_task["title"],
                    "status": created_task["status"],
                    "assigned_to": created_task["assigned_to"]
                })
            
            # Step 4: Prepare response
            result_data = {
                "success": True,
                "top_relevant_tasks": [
                    {
                        "id": str(t["_id"]),
                        "title": t.get("title"),
                        "status": t.get("status"),
                        "assigned_to": t.get("assigned_to", "Unassigned")
                    }
                    for t in top_relevant_tasks
                ],
                "created_tasks": new_tasks,
                "total_created": len(new_tasks),
                "message": f"Successfully created {len(new_tasks)} new task(s) based on {len(user_goals)} goal(s)"
            }
            
            print(f"   ✅ Done! Created {len(new_tasks)} tasks")
            return result_data
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"   ❌ Error in create_tasks_from_goals:")
            print(error_details)
            return {
                "success": False,
                "error": str(e),
                "created_tasks": [],
                "top_relevant_tasks": []
            }

    # Register all tools - ORDER MATTERS: define before use!
    tools = tools = [

        get_project_details, 

        get_project_tasks, 

        get_user_goals, 

        create_tasks_from_goals

    ]
    llm_with_tools = llm.bind_tools(tools)
    
    print(f"✅ Registered {len(tools)} tools with LLM:")
    for t in tools:
        print(f"   - {t.name}")
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
        # Format goals as comma-separated string for the tool

        goals_as_text = ','.join(goals)


        # Format goals for display in prompt
        
        if len(goals) == 1:
            goal_text = goals[0]
        else:
            goal_text = '\n'.join(f"{i+1}. {goal}" for i, goal in enumerate(goals))

        system_msg = """You are an expert learning path advisor with access to tools.

            Your task:
            1. Use get_project_details tool to fetch project information for project_id: "695caa41c485455f397017ae"
            2. Use get_project_tasks tool to fetch all tasks for that project
            3. Analyze if the user's goals align with the project tasks

            4. 🆕 IMPORTANT - CREATE TASKS:
            5. Provide a summary of what tasks were created

            Be thorough - call ALL the tools in sequence."""

        user_prompt = f"""User ID: {user_id}

            User's Learning Goals:
            {goal_text}

            
            Instructions:

            1. Fetch project details for "695caa41c485455f397017ae"

            2. Fetch all tasks for that project

            3. Call create_tasks_from_goals with user_id="{user_id}", project_id="695caa41c485455f397017ae", goals_text="{goals_as_text}"

            4. Summarize what you did"""

        messages = state.get("messages", [])
        messages = [
            SystemMessage(content=system_msg),
            HumanMessage(content=user_prompt)
        ] + messages

        print(f"🤖 Agent starting with {len(tools)} tools available")

        return {"messages": messages}

    async def call_model(state: AgentState):
        """Call LLM with tools"""
        messages = state["messages"]
        
        print(f"💭 Calling LLM with {len(messages)} messages...")
        response = await llm_with_tools.ainvoke(messages)
        print(f"📝 LLM response type: {type(response)}")

        # Check if LLM wants to use tools

        if hasattr(response, 'tool_calls') and response.tool_calls:

            print(f"   🔧 LLM requested {len(response.tool_calls)} tool call(s):")

            for tc in response.tool_calls:

                print(f"      - {tc['name']}")

        else:

            print(f"   💬 LLM returned text response")
        
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
                print(f"   ✅ Result: {str(result)[:150]}...")
                
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
        print("✅ No more tool calls, finishing workflow")
        return "end"

    async def format_response(state: AgentState):
        """Format final response for user"""
        messages = state["messages"]
        
        # Find the last AI message with actual content
        response_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                response_content = msg.content
                break
        
        if not response_content:
            response_content = "I've analyzed your goals and created personalized tasks for you!"
        
        print(f"📊 Final response ({len(response_content)} chars)")
        
        return {
            "response_text": response_content,
            "messages": []
        }

    async def no_goals_handler(state: AgentState):
        """Handle case when user has no goals set"""
        no_goals_message = (
            "I noticed you haven't set any goals yet. "
            "To get started, please set your learning goals first. "
            "You can do this by using the goals endpoint to define what you want to achieve!"
        )
        
        print("📝 Returning no goals message")
        
        return {
            "response_text": no_goals_message,
            "messages": [AIMessage(content=no_goals_message)]
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

    print("🔄 Agentic workflow compiled successfully with NEW create_tasks_from_goals tool")
    return workflow.compile()

    

    