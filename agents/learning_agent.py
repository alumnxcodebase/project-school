from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langsmith import traceable
import os
from dotenv import load_dotenv
from bson import ObjectId
import json
import re

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
            agent_name = message[len(prefix) :].strip()
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


def parse_json_from_response(response_text: str) -> list:
    """
    Extract JSON array from response text, handling markdown code blocks and nested text.
    Returns list of task objects with id and title.
    """
    try:
        print(f"\n📊 Parsing response:\n{response_text}\n")

        # Remove markdown code blocks if present
        cleaned = response_text.strip()
        cleaned = re.sub(r"```json\s*", "", cleaned)
        cleaned = re.sub(r"```\s*", "", cleaned)
        cleaned = cleaned.strip()

        # Extract JSON array if it's embedded in text
        # Look for pattern: [ ... ]
        json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            print(f"📌 Found JSON match:\n{json_str}\n")
        else:
            json_str = cleaned
            print(f"⚠️ No JSON match pattern found, trying full response\n")

        # Try to parse JSON
        tasks = json.loads(json_str)

        if isinstance(tasks, list):
            print(f"✅ Successfully parsed {len(tasks)} tasks\n")
            for i, task in enumerate(tasks, 1):
                print(f"   Task {i}: {task.get('title')} (ID: {task.get('id')})")
            return tasks

        print(f"⚠️ Parsed data is not a list: {type(tasks)}\n")
        return []

    except json.JSONDecodeError as e:
        print(f"❌ JSON Parse Error: {str(e)}")
        print(
            f"📝 Attempted to parse:\n{json_str if 'json_str' in locals() else response_text}\n"
        )
        return []
    except Exception as e:
        print(f"❌ Unexpected error during parsing: {str(e)}\n")
        return []


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
        agent_name = (
            agent_doc.get("agentName", "Study Buddy") if agent_doc else "Study Buddy"
        )
        print(f"🤖 Agent name: {agent_name}")

        # Initialize LLM
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found")

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-exp", temperature=0.7, google_api_key=api_key
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
                    "status": project.get("status"),
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
                print(f"\n{'='*60}")
                print(f"🔍 FETCHING ALL TASKS FOR PROJECT: {project_id}")
                print(f"{'='*60}")
                
                tasks_cursor = db.tasks.find({"project_id": project_id})
                tasks = await tasks_cursor.to_list(length=None)

                result = [
                    {
                        "id": str(task["_id"]),
                        "title": task.get("title"),
                        "description": task.get("description", "No description"),
                        "status": task.get("status"),
                    }
                    for task in tasks
                ]
                
                print(f"\n📋 AVAILABLE TASKS IN PROJECT:")
                print(f"{'-'*60}")
                for i, task in enumerate(result, 1):
                    print(f"{i}. {task['title']}")
                    print(f"   ID: {task['id']}")
                    print(f"   Description: {task['description'][:80]}...")
                    print()
                
                print(f"{'-'*60}")
                print(f"✅ Total tasks in project: {len(result)}")
                print(f"{'='*60}\n")
                
                return result
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                import traceback
                traceback.print_exc()
                return [{"error": str(e)}]

        @tool
        async def get_user_assigned_tasks(user_id: str) -> dict:
            """Fetch all tasks already assigned to the user (both completed and pending)."""
            try:
                print(f"\n{'='*60}")
                print(f"🔍 FETCHING ASSIGNED TASKS FOR USER: {user_id}")
                print(f"{'='*60}")
                
                assignment = await db.assignments.find_one({"userId": user_id})

                if not assignment or not assignment.get("tasks"):
                    print("✅ No tasks assigned to user yet")
                    print(f"{'='*60}\n")
                    return {"assigned_task_ids": [], "completed_task_ids": []}

                assigned_task_ids = []
                completed_task_ids = []

                print(f"\n📋 TASK DETAILS:")
                print(f"{'-'*60}")
                
                for idx, task in enumerate(assignment.get("tasks", []), 1):
                    task_id = task.get("taskId")
                    task_name = task.get("taskName", "Unknown")
                    is_completed = task.get("isCompleted", False)
                    
                    if task_id:
                        assigned_task_ids.append(task_id)
                        status_emoji = "✅" if is_completed else "⏳"
                        status_text = "COMPLETED" if is_completed else "PENDING"
                        
                        print(f"{status_emoji} Task {idx}: [{status_text}]")
                        print(f"   ID: {task_id}")
                        print(f"   Name: {task_name}")
                        print()
                        
                        if is_completed:
                            completed_task_ids.append(task_id)

                print(f"{'-'*60}")
                print(f"📊 SUMMARY:")
                print(f"   Total assigned: {len(assigned_task_ids)}")
                print(f"   Completed: {len(completed_task_ids)}")
                print(f"   Pending: {len(assigned_task_ids) - len(completed_task_ids)}")
                print(f"\n🚫 FILTER OUT THESE TASK IDs:")
                for task_id in assigned_task_ids:
                    print(f"   - {task_id}")
                print(f"{'='*60}\n")
                
                return {
                    "assigned_task_ids": assigned_task_ids,
                    "completed_task_ids": completed_task_ids,
                }
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                import traceback
                traceback.print_exc()
                return {
                    "error": str(e),
                    "assigned_task_ids": [],
                    "completed_task_ids": [],
                }

        # Determine mode based on user message
        is_task_assignment_mode = user_message and (
            "updated the goals" in user_message.lower()
            or "share the revised tasks" in user_message.lower()
            or "share tasks" in user_message.lower()
        )

        if is_task_assignment_mode:
            print("🎯 MODE: Task Assignment")
            tools = [
                get_user_goals,
                get_project_details,
                get_project_tasks,
                get_user_assigned_tasks,
            ]
        
            system_prompt = f"""You are {agent_name}, an expert learning path advisor.

            CRITICAL INSTRUCTION: You MUST ONLY select tasks that exist in the project. Do NOT make up or create new tasks.

            STEPS TO FOLLOW:
            1. Call get_user_goals(user_id="{user_id}") to fetch user's goals
            2. Call get_user_assigned_tasks(user_id="{user_id}") to get assigned task IDs
            3. Call get_project_details(project_id="695caa41c485455f397017ae")
            4. Call get_project_tasks(project_id="695caa41c485455f397017ae") to get ALL available tasks
            5. From the project tasks, FILTER OUT tasks whose ID is in assigned_task_ids
            6. From the REMAINING tasks (NOT assigned yet), select EXACTLY 6 tasks
            7. Match selected tasks to user's goals
            8. Return ONLY those 6 tasks in JSON format

            ABSOLUTE RULES - NEVER VIOLATE:
            ❌ DO NOT create fictional tasks (e.g., "Quantum Computing" if not in project)
            ❌ DO NOT modify task titles or IDs
            ❌ DO NOT suggest tasks already in assigned_task_ids
            ✅ ONLY use task IDs and titles EXACTLY as returned by get_project_tasks
            ✅ Select from UNASSIGNED tasks only
            ✅ Return exactly 6 tasks

            OUTPUT FORMAT - RESPOND WITH ONLY THIS JSON:
            [
            {{"id": "actual_task_id_from_project", "title": "Actual Task Title from project"}},
            {{"id": "actual_task_id_from_project", "title": "Actual Task Title from project"}},
            {{"id": "actual_task_id_from_project", "title": "Actual Task Title from project"}},
            {{"id": "actual_task_id_from_project", "title": "Actual Task Title from project"}},
            {{"id": "actual_task_id_from_project", "title": "Actual Task Title from project"}},
            {{"id": "actual_task_id_from_project", "title": "Actual Task Title from project"}}
            ]
            
            NO markdown, NO explanation, NO other text - ONLY the JSON array."""

            user_prompt = f"""User ID: {user_id}
Project ID: 695caa41c485455f397017ae

Execute the steps:
1. Get user goals
2. Get assigned tasks
3. Get project details  
4. Get all project tasks
5. Filter out assigned tasks
6. Select 6 best unassigned tasks for user's goals
7. Return ONLY JSON array with those 6 tasks

Remember: Use ONLY tasks from get_project_tasks response. Do NOT invent tasks."""

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
        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            }
        )

        print("✅ Agent execution completed\n")

        # Extract final response
        final_message = result["messages"][-1]
        final_response = (
            final_message.content
            if hasattr(final_message, "content")
            else str(final_message)
        )

        # Handle list content from Gemini
        if isinstance(final_response, list):
            content_parts = []
            for part in final_response:
                if isinstance(part, str):
                    content_parts.append(part)
                elif hasattr(part, "text"):
                    content_parts.append(part.text)
                else:
                    content_parts.append(str(part))
            final_response = "".join(content_parts).strip()

        print(f"{'='*60}")
        print(f"✅ Agent completed successfully")
        print(f"{'='*60}\n")
        print(f"Response:\n{final_response}\n")

        # If task assignment mode, parse JSON and return structured tasks
        if is_task_assignment_mode:
            print(f"\n🔍 TASK ASSIGNMENT MODE - Parsing response")
            print(f"📝 Raw response text:\n{final_response}\n")

            parsed_tasks = parse_json_from_response(final_response)
            print(f"✅ Parsed {len(parsed_tasks)} tasks from agent response\n")

            # Server-side validation: Verify tasks exist in project
            print(f"\n{'='*60}")
            print(f"🛡️ SERVER-SIDE VALIDATION")
            print(f"{'='*60}")
            
            # Get all project tasks for validation
            project_tasks_cursor = db.tasks.find({"project_id": "695caa41c485455f397017ae"})
            all_project_tasks = await project_tasks_cursor.to_list(length=None)
            valid_task_ids = {str(task["_id"]) for task in all_project_tasks}
            
            print(f"\n📦 Project has {len(valid_task_ids)} total tasks")
            print(f"🔍 Validating {len(parsed_tasks)} suggested tasks...\n")
            
            # Filter out hallucinated tasks
            validated_tasks = []
            hallucinated_tasks = []
            
            for task in parsed_tasks:
                task_id = str(task.get("id", ""))
                if task_id in valid_task_ids:
                    validated_tasks.append(task)
                    print(f"✅ VALID: {task.get('title')} (ID: {task_id})")
                else:
                    hallucinated_tasks.append(task)
                    print(f"❌ INVALID/HALLUCINATED: {task.get('title')} (ID: {task_id})")
            
            if hallucinated_tasks:
                print(f"\n⚠️ WARNING: LLM hallucinated {len(hallucinated_tasks)} tasks!")
                print(f"   Filtered them out. Using only {len(validated_tasks)} valid tasks.")
            
            # Also check for duplicates with assigned tasks
            assignment = await db.assignments.find_one({"userId": user_id})
            if assignment and assignment.get("tasks"):
                assigned_ids = {str(t.get("taskId")) for t in assignment.get("tasks", []) if t.get("taskId")}
                
                print(f"\n🚫 Checking for duplicates with {len(assigned_ids)} assigned tasks...")
                
                original_count = len(validated_tasks)
                validated_tasks = [
                    task for task in validated_tasks 
                    if str(task.get("id")) not in assigned_ids
                ]
                
                if original_count != len(validated_tasks):
                    print(f"⚠️ Removed {original_count - len(validated_tasks)} duplicate tasks")
            
            print(f"\n✅ Final validated tasks: {len(validated_tasks)}")
            print(f"{'='*60}\n")

            # Get project info for response
            project_doc = await db.projects.find_one(
                {"_id": ObjectId("695caa41c485455f397017ae")}
            )
            project_name = (
                project_doc.get("name", "Project School")
                if project_doc
                else "Project School"
            )
            project_id = "695caa41c485455f397017ae"

            print(f"📦 Project: {project_name} ({project_id})\n")

            # Enrich tasks with project information
            enriched_tasks = []
            for task in validated_tasks:
                enriched_task = {
                    "taskId": task.get("id"),
                    "taskName": task.get("title"),
                    "projectId": project_id,
                    "projectName": project_name,
                }
                enriched_tasks.append(enriched_task)
                print(f"   ✓ {enriched_task['taskName']}")

            print(f"\n📤 Returning {len(enriched_tasks)} validated tasks\n")
            
            response_obj = {
                "response_text": f"I've selected {len(enriched_tasks)} personalized tasks for your learning path. Here they are:",
                "status": "success",
                "tasks": enriched_tasks,
                "messages": result["messages"],
            }
            
            return response_obj
        else:
            return {
                "response_text": final_response,
                "status": "success",
                "messages": result["messages"],
            }

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback

        traceback.print_exc()
        return {"response_text": f"An error occurred: {str(e)}", "status": "error"}