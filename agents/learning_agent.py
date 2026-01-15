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
                    "status": project.get("status"),
                }
                print(f"✅ Project found: {result['name']}")
                return result
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                return {"error": str(e)}

        @tool
        async def get_project_tasks(user_id: str) -> list:
            """Fetch up to 10 available tasks from all assigned projects in sequence order."""
            try:
                print(f"\n{'='*60}")
                print(f"🔍 FETCHING TASKS FROM ASSIGNED PROJECTS FOR USER: {user_id}")
                print(f"{'='*60}")
                
                # Get assigned projects in sequence order
                assigned_projects_cursor = db.assignedprojects.find(
                    {"userId": user_id}
                ).sort("sequenceId", 1)
                assigned_projects = await assigned_projects_cursor.to_list(length=None)

                if not assigned_projects:
                    print("⚠️ No projects assigned to user")
                    return []

                print(f"\n📦 User has {len(assigned_projects)} assigned projects")

                # Get user's assignments to identify completed/assigned tasks
                assignment = await db.assignments.find_one({"userId": user_id})
                completed_task_ids = set()
                assigned_task_ids = set()

                if assignment and assignment.get("tasks"):
                    for task_assignment in assignment["tasks"]:
                        task_id = str(task_assignment.get("taskId", ""))
                        assigned_task_ids.add(task_id)
                        if task_assignment.get("isCompleted", False):
                            completed_task_ids.add(task_id)

                print(f"   User has {len(assigned_task_ids)} assigned tasks ({len(completed_task_ids)} completed)")

                # Collect available tasks from all projects in sequence
                all_available_tasks = []
                
                for ap in assigned_projects:
                    project_id = ap.get("projectId")
                    
                    # Get all tasks for this project
                    tasks_cursor = db.tasks.find({"project_id": project_id})
                    tasks = await tasks_cursor.to_list(length=None)
                    
                    # Get project details
                    project = await db.projects.find_one({"_id": ObjectId(project_id)})
                    project_name = project.get("name", "Unknown Project") if project else "Unknown Project"
                    
                    print(f"   Project: {project_name} (Seq: {ap.get('sequenceId')}) - {len(tasks)} tasks")
                    
                    # Filter available tasks
                    for task in tasks:
                        task_id = str(task["_id"])
                        if task_id not in completed_task_ids and task_id not in assigned_task_ids:
                            all_available_tasks.append({
                                "id": task_id,
                                "title": task.get("title", "Untitled Task"),
                                "description": task.get("description", "No description"),
                                "status": task.get("status"),
                                "project_id": project_id,
                                "project_name": project_name
                            })

                # Limit to 10 tasks
                result = all_available_tasks[:10]
                
                print(f"\n📋 AVAILABLE TASKS (UP TO 10):")
                print(f"{'-'*60}")
                for i, task in enumerate(result, 1):
                    print(f"{i}. {task['title']}")
                    print(f"   ID: {task['id']}")
                    print(f"   Project: {task['project_name']}")
                    print(f"   Description: {task['description'][:80]}...")
                    print()
                
                print(f"{'-'*60}")
                print(f"✅ Returning {len(result)} tasks (from {len(all_available_tasks)} total available)")
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
                return {"error": str(e)}

        # Determine mode based on message
        is_task_assignment_mode = (
            user_message and "Updated the goals. Share the revised tasks." in user_message
        )

        if is_task_assignment_mode:
            print("🎯 MODE: Task Assignment")
            tools = [get_user_goals, get_user_assigned_tasks, get_project_tasks]

            system_prompt = f"""You are {agent_name}, an intelligent learning advisor.

            CRITICAL OBJECTIVE: Recommend EXACTLY 6 new learning tasks based on user's goals.

            STRICT WORKFLOW - FOLLOW EVERY STEP:
            1. Call get_user_goals to understand what user wants to learn
            2. Call get_user_assigned_tasks to get list of task IDs to AVOID
            3. Call get_project_tasks to get available tasks from assigned projects
            4. EXCLUDE any task IDs in assigned_task_ids (from step 2)
            5. From REMAINING tasks, select exactly 6 that match user's goals
            6. Return ONLY those 6 tasks in JSON format

            ABSOLUTE RULES - NEVER VIOLATE:
            ❌ DO NOT create fictional tasks
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

            Execute the steps:
            1. Get user goals
            2. Get assigned tasks
            3. Get all available project tasks
            4. Filter out assigned tasks
            5. Select 6 best unassigned tasks for user's goals
            6. Return ONLY JSON array with those 6 tasks

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

            # Server-side validation: Verify tasks exist in assigned projects
            print(f"\n{'='*60}")
            print(f"🛡️ SERVER-SIDE VALIDATION")
            print(f"{'='*60}")
            
            # Get all tasks from assigned projects for validation
            assigned_projects_cursor = db.assignedprojects.find({"userId": user_id})
            assigned_projects = await assigned_projects_cursor.to_list(length=None)
            
            valid_task_ids = set()
            project_info = {}
            
            for ap in assigned_projects:
                project_id = ap.get("projectId")
                project_tasks_cursor = db.tasks.find({"project_id": project_id})
                project_tasks = await project_tasks_cursor.to_list(length=None)
                
                # Get project details
                project = await db.projects.find_one({"_id": ObjectId(project_id)})
                project_name = project.get("name", "Unknown") if project else "Unknown"
                
                for task in project_tasks:
                    task_id = str(task["_id"])
                    valid_task_ids.add(task_id)
                    project_info[task_id] = {
                        "project_id": project_id,
                        "project_name": project_name
                    }
            
            print(f"\n📦 Total valid tasks across all assigned projects: {len(valid_task_ids)}")
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

            # Enrich tasks with project information
            enriched_tasks = []
            for task in validated_tasks:
                task_id = task.get("id")
                proj_info = project_info.get(task_id, {})
                enriched_task = {
                    "taskId": task_id,
                    "taskName": task.get("title"),
                    "projectId": proj_info.get("project_id", ""),
                    "projectName": proj_info.get("project_name", "Unknown Project"),
                }
                enriched_tasks.append(enriched_task)
                print(f"   ✓ {enriched_task['taskName']} (Project: {enriched_task['projectName']})")

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
        return {
            "response_text": f"An error occurred: {str(e)}",
            "status": "error"
        }