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


async def classify_user_intent(llm, user_message: str) -> str:
    """
    Classify user intent using LLM.
    
    Returns:
        - "task_assignment": User wants task recommendations based on goals
        - "general_conversation": General career/learning questions
    """
    try:
        print(f"\n🎯 Classifying intent for message: {user_message}")
        
        intent_prompt = f"""Classify the user's intent into one of these categories:

1. "task_assignment" - User has updated their goals and wants personalized task recommendations. Examples:
   - "Updated the goals. Share the revised tasks."
   - "I've set my goals, what tasks should I work on?"
   - "Based on my new goals, recommend tasks"
   - "Show me tasks for my learning path"

2. "general_conversation" - User is asking general career/learning questions. Examples:
   - "What skills do I need for data science?"
   - "How do I prepare for ML interviews?"
   - "What's the roadmap to become an AI engineer?"
   - "Can you help me with my resume?"

User message: "{user_message}"

Respond with ONLY one word: either "task_assignment" or "general_conversation"
"""

        result = await llm.ainvoke([HumanMessage(content=intent_prompt)])
        intent = result.content.strip().lower()
        
        # Handle list content from Gemini
        if isinstance(intent, list):
            content_parts = []
            for part in intent:
                if isinstance(part, str):
                    content_parts.append(part)
                elif hasattr(part, "text"):
                    content_parts.append(part.text)
                else:
                    content_parts.append(str(part))
            intent = "".join(content_parts).strip().lower()
        
        # Validate intent
        if "task_assignment" in intent:
            intent = "task_assignment"
        elif "general_conversation" in intent:
            intent = "general_conversation"
        else:
            # Default to general conversation if unclear
            intent = "general_conversation"
        
        print(f"✅ Classified intent: {intent}\n")
        return intent
        
    except Exception as e:
        print(f"❌ Error in intent classification: {str(e)}")
        import traceback
        traceback.print_exc()
        # Default to general conversation on error
        return "general_conversation"


@traceable(name="Learning Agent", tags=["agent", "career-guidance"])
async def run_learning_agent(db, user_id: str, user_message: str = None) -> dict:
    try:
        print(f"\n{'='*60}")
        print(f"🚀 Starting learning agent for user: {user_id}")
        print(f"📝 User message: {user_message}")
        print(f"{'='*60}\n")

        # CRITICAL: Check if user exists in database first
        from bson.errors import InvalidId
        try:
            user_exists = await db.users.find_one({"_id": ObjectId(user_id)})
        except InvalidId:
            # If user_id is not a valid ObjectId, user doesn't exist
            user_exists = None
            
        if not user_exists:
            print(f"⚠️ User {user_id} not found in database")
            return {
                "message": "Looks like you are not a member of the Project School.",
                "status": "user_not_found",
                "tasks": []
            }

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

        # Classify user intent using LLM
        user_intent = await classify_user_intent(llm, user_message) if user_message else "general_conversation"
        is_task_assignment_mode = (user_intent == "task_assignment")
        
        print(f"🎯 Mode: {'TASK ASSIGNMENT' if is_task_assignment_mode else 'GENERAL CONVERSATION'}\n")
        
        # Early validation for task assignment mode
        if is_task_assignment_mode:
            print("🔍 Validating prerequisites for task assignment...")
            
            # Check if user has goals set
            goals_doc = await db.goals.find_one({"userId": user_id})
            if not goals_doc or not goals_doc.get("goals"):
                print("⚠️ No goals found for user")
                return {
                    "message": "Looks like your goals are not yet set. Please update them in Project School. If you need help reach out to Vijender.",
                    "status": "no_goals",
                    "tasks": []
                }
            
            # Check if user has assigned projects
            assigned_projects_cursor = db.assignedprojects.find({"userId": user_id})
            assigned_projects = await assigned_projects_cursor.to_list(length=None)
            if not assigned_projects:
                print("⚠️ No assigned projects found for user")
                return {
                    "message": "Looks like your Study Plan has not been prepared as yet. Please connect with Vijender asap.",
                    "status": "no_projects",
                    "tasks": []
                }
            
            print("✅ Prerequisites validated - user has goals and assigned projects\n")

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
                return {"goals": [], "message": f"Error: {str(e)}"}

        @tool
        async def get_available_tasks(user_id: str) -> dict:
            """
            Fetch all available tasks from projects assigned to the user.
            Returns tasks with their IDs, titles, descriptions, and project info.
            """
            try:
                print(f"🔍 Fetching available tasks for user: {user_id}")

                # Get assigned projects for this user
                assigned_projects_cursor = db.assignedprojects.find({"userId": user_id})
                assigned_projects = await assigned_projects_cursor.to_list(length=None)

                if not assigned_projects:
                    print("⚠️ No assigned projects found")
                    return {"tasks": [], "message": "No projects assigned yet"}

                print(f"   Found {len(assigned_projects)} assigned project(s)")

                all_tasks = []

                for ap in assigned_projects:
                    project_id = ap.get("projectId")

                    # Get project details
                    project = await db.projects.find_one({"_id": ObjectId(project_id)})
                    project_name = project.get("name", "Unknown") if project else "Unknown"

                    # Get tasks for this project
                    tasks_cursor = db.tasks.find({"project_id": project_id})
                    tasks = await tasks_cursor.to_list(length=None)

                    print(f"   Project '{project_name}': {len(tasks)} task(s)")

                    for task in tasks:
                        task_info = {
                            "id": str(task["_id"]),
                            "title": task.get("name", "Untitled"),
                            "description": task.get("description", "No description"),
                            "project_id": project_id,
                            "project_name": project_name,
                        }
                        all_tasks.append(task_info)

                print(f"✅ Total available tasks: {len(all_tasks)}\n")
                return {"tasks": all_tasks}

            except Exception as e:
                print(f"❌ Error in get_available_tasks: {str(e)}")
                import traceback

                traceback.print_exc()
                return {"tasks": [], "message": f"Error: {str(e)}"}

        @tool
        async def get_user_assigned_tasks(user_id: str) -> dict:
            """
            Fetch tasks already assigned to the user.
            Used to avoid recommending duplicate tasks.
            """
            try:
                print(f"🔍 Fetching assigned tasks for user: {user_id}")

                assignment = await db.assignments.find_one({"userId": user_id})

                if not assignment or not assignment.get("tasks"):
                    print("   No tasks assigned yet")
                    return {"assigned_task_ids": []}

                assigned_ids = [
                    str(task.get("taskId"))
                    for task in assignment.get("tasks", [])
                    if task.get("taskId")
                ]

                print(f"✅ User has {len(assigned_ids)} assigned task(s)\n")
                return {"assigned_task_ids": assigned_ids}

            except Exception as e:
                print(f"❌ Error in get_user_assigned_tasks: {str(e)}")
                import traceback

                traceback.print_exc()
                return {"assigned_task_ids": []}

        # Choose tools based on mode
        if is_task_assignment_mode:
            tools = [get_user_goals, get_available_tasks, get_user_assigned_tasks]
        else:
            tools = [get_user_goals]

        # Build system prompt based on mode
        if is_task_assignment_mode:
            system_prompt = f"""You are {agent_name}, an AI learning assistant helping users grow their tech careers.

Your user has updated their learning goals. Your task is to recommend personalized tasks from their assigned projects.

PROCESS:
1. Use get_user_goals to understand their current goals
2. Use get_available_tasks to see all tasks from their assigned projects
3. Use get_user_assigned_tasks to avoid recommending duplicates
4. Select 3-5 most relevant tasks that align with their goals
5. Return ONLY a JSON array (no other text)

JSON FORMAT (return exactly this structure):
[
  {{"id": "task_id_1", "title": "Task name 1"}},
  {{"id": "task_id_2", "title": "Task name 2"}},
  {{"id": "task_id_3", "title": "Task name 3"}}
]

SELECTION CRITERIA:
- Match tasks to user's learning goals
- Choose foundational tasks for beginners
- Progress from basic to advanced
- Ensure variety across different skills
- NEVER recommend already assigned tasks
- ONLY use task IDs from get_available_tasks (never invent IDs)

CRITICAL:
- Return ONLY the JSON array, no explanations
- Use exact task IDs from database
- Verify tasks are not in assigned_task_ids list"""

            user_prompt = f"""User ID: {user_id}

The user has updated their goals and wants task recommendations.

Step 1: Get their learning goals
Step 2: Get available tasks from assigned projects
Step 3: Get already assigned tasks to avoid duplicates
Step 4: Select 3-5 best tasks matching their goals
Step 5: Return ONLY the JSON array"""

        else:
            system_prompt = f"""You are {agent_name}, a friendly AI learning assistant specializing in tech career growth.

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
            
            # Return appropriate message based on whether tasks were found
            if len(enriched_tasks) == 0:
                message_text = "Looks like your Study Plan has not been prepared as yet. Please connect with Vijender asap."
            else:
                # Format tasks in the message text for WhatsApp
                message_text = f"I've selected {len(enriched_tasks)} personalized tasks for your learning path:\n\n"
                for idx, task in enumerate(enriched_tasks, 1):
                    message_text += f"{idx}. *{task['taskName']}*\n"
                    message_text += f"   Project: {task['projectName']}\n"
                    message_text += f"   Task ID: {task['taskId']}\n\n"
            
            response_obj = {
                "message": message_text,
                "status": "success",
                "tasks": enriched_tasks,
                "messages": result["messages"],
            }
            
            return response_obj
        else:
            return {
                "message": final_response,
                "status": "success",
                "messages": result["messages"],
            }

        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback

        traceback.print_exc()
        return {
            "message": f"An error occurred: {str(e)}",
            "status": "error"
        }