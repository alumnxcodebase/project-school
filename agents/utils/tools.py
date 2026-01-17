# tools.py

from langchain_core.tools import tool
from bson import ObjectId
import httpx
from datetime import datetime


def create_agent_tools(db):
    """Create and return all agent tools"""
    
    @tool
    async def get_user_goals(user_id: str) -> str:
        """Fetch the user's current learning goals from the database."""
        try:
            print(f"\n🎯 Fetching goals for user: {user_id}")
            user_doc = await db.users.find_one({"userId": user_id})
            
            if user_doc and "goals" in user_doc:
                goals = user_doc["goals"]
                print(f"✅ Found goals: {goals}")
                return f"User's learning goals: {goals}"
            else:
                print("⚠️ No goals found for user")
                return "No learning goals set yet. User should update their goals first."
        except Exception as e:
            print(f"❌ Error fetching goals: {str(e)}")
            return f"Error fetching goals: {str(e)}"

    @tool
    async def get_assigned_projects(user_id: str) -> str:
        """Get list of projects assigned to the user with project IDs and names."""
        try:
            print(f"\n📚 Fetching assigned projects for user: {user_id}")
            
            assigned_projects_cursor = db.assignedprojects.find({"userId": user_id})
            assigned_projects = await assigned_projects_cursor.to_list(length=None)
            
            if not assigned_projects:
                print("⚠️ No projects assigned to user")
                return "No projects assigned to this user yet."
            
            project_list = []
            for ap in assigned_projects:
                project_id = ap.get("projectId")
                project = await db.projects.find_one({"_id": ObjectId(project_id)})
                
                if project:
                    project_name = project.get("name", "Unknown Project")
                    project_list.append(f"Project ID: {project_id}, Name: {project_name}")
                    print(f"   ✅ {project_name} (ID: {project_id})")
            
            print(f"✅ Found {len(project_list)} assigned projects")
            return "Assigned projects:\n" + "\n".join(project_list)
            
        except Exception as e:
            print(f"❌ Error fetching assigned projects: {str(e)}")
            return f"Error fetching assigned projects: {str(e)}"

    @tool
    async def get_tasks_for_project(project_id: str) -> str:
        """Get all tasks for a specific project. Returns task IDs and names."""
        try:
            print(f"\n📋 Fetching tasks for project: {project_id}")
            
            tasks_cursor = db.tasks.find({"project_id": project_id})
            tasks = await tasks_cursor.to_list(length=None)
            
            if not tasks:
                print(f"⚠️ No tasks found for project {project_id}")
                return f"No tasks found for project {project_id}"
            
            task_list = []
            for task in tasks:
                task_id = str(task["_id"])
                task_name = task.get("name", "Unnamed Task")
                task_desc = task.get("description", "No description")
                
                task_list.append(
                    f"Task ID: {task_id}\n"
                    f"Name: {task_name}\n"
                    f"Description: {task_desc}\n"
                )
                print(f"   ✅ {task_name} (ID: {task_id})")
            
            print(f"✅ Found {len(task_list)} tasks")
            return f"Tasks for project {project_id}:\n\n" + "\n".join(task_list)
            
        except Exception as e:
            print(f"❌ Error fetching tasks: {str(e)}")
            return f"Error fetching tasks for project {project_id}: {str(e)}"

    @tool
    async def get_chat_history(user_id: str, limit: int = 20) -> str:
        """
        Fetch recent chat history for the user to provide context for answering questions.
        Use this tool when the user asks about previous conversations, names, or any past interactions.
        
        Args:
            user_id: The user's ID
            limit: Number of recent messages to fetch (default: 20)
        
        Returns:
            Formatted chat history with timestamps
        """
        try:
            print(f"\n💬 Fetching chat history for user: {user_id} (limit: {limit})")
            
            chat_history_cursor = db.chats.find(
                {"userId": user_id}
            ).sort("timestamp", -1).limit(limit)
            
            chat_history = await chat_history_cursor.to_list(length=limit)
            chat_history.reverse()  # Reverse to get chronological order
            
            if not chat_history:
                print("⚠️ No chat history found")
                return "No previous chat history found for this user."
            
            # Format chat history
            formatted_history = []
            for chat in chat_history:
                user_type = chat.get("userType", "unknown")
                message = chat.get("message", "")
                timestamp = chat.get("timestamp", "")
                
                formatted_history.append(f"{user_type.upper()}: {message}")
            
            history_text = "\n".join(formatted_history)
            print(f"✅ Retrieved {len(chat_history)} chat messages")
            print(f"📜 Chat history:\n{history_text}\n")
            
            return f"Chat history for user {user_id}:\n\n{history_text}"
            
        except Exception as e:
            print(f"❌ Error fetching chat history: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"Error fetching chat history: {str(e)}"

    @tool
    async def save_chat_history(user_id: str, message: str, user_type: str = "user") -> str:
        """
        Save a chat message to the chat history database.
        
        Args:
            user_id: The user ID (can be phone number for new users)
            message: The message content to save
            user_type: Type of user - "user" or "agent" (default: "user")
        
        Returns:
            Success or error message
        """
        try:
            print(f"\n💾 Saving chat to history...")
            print(f"   User ID: {user_id}")
            print(f"   User Type: {user_type}")
            print(f"   Message: {message[:100]}...")  # Log first 100 chars
            
            # Insert chat document into database
            chat_doc = {
                "userId": user_id,
                "userType": user_type,
                "message": message,
                "timestamp": datetime.now()
            }
            
            result = await db.chats.insert_one(chat_doc)
            
            print(f"✅ Chat saved successfully with ID: {result.inserted_id}")
            return f"Chat saved successfully for user {user_id}"
            
        except Exception as e:
            print(f"❌ Error saving chat: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"Error saving chat: {str(e)}"

    @tool
    async def save_resume_data(user_id: str, resume_data: dict) -> str:
        """
        Save parsed resume data to the userdata collection.
        This tool is automatically called when a user uploads their resume.
        
        Args:
            user_id: The user's ID (phone number)
            resume_data: Complete parsed resume data from the resume parser API
        
        Returns:
            Success or error message
        """
        try:
            print(f"\n📄 Saving resume data for user: {user_id}")
            print(f"📊 Resume data keys: {list(resume_data.keys())}")
            
            # Create userdata document
            userdata_doc = {
                "userId": user_id,
                "resumeData": resume_data,
                "uploadedAt": datetime.now(),
                "lastUpdated": datetime.now()
            }
            
            # Upsert: update if exists, insert if doesn't
            result = await db.userdata.update_one(
                {"userId": user_id},
                {
                    "$set": {
                        "resumeData": resume_data,
                        "lastUpdated": datetime.now()
                    },
                    "$setOnInsert": {
                        "uploadedAt": datetime.now()
                    }
                },
                upsert=True
            )
            
            if result.upserted_id:
                print(f"✅ New resume data inserted with ID: {result.upserted_id}")
                action = "saved"
            elif result.modified_count > 0:
                print(f"✅ Existing resume data updated")
                action = "updated"
            else:
                print(f"⚠️ No changes made to resume data")
                action = "verified"
            
            return f"Resume data {action} successfully for user {user_id}"
            
        except Exception as e:
            print(f"❌ Error saving resume data: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"Error saving resume data: {str(e)}"

    @tool
    async def get_resume_data(user_id: str) -> str:
        """
        Retrieve saved resume data for a user.
        Use this to access previously uploaded resume information.
        
        Args:
            user_id: The user's ID
        
        Returns:
            Resume data or error message
        """
        try:
            print(f"\n📄 Fetching resume data for user: {user_id}")
            
            userdata = await db.userdata.find_one({"userId": user_id})
            
            if not userdata or "resumeData" not in userdata:
                print("⚠️ No resume data found")
                return "No resume data found for this user. User should upload their resume first."
            
            resume_data = userdata["resumeData"]
            uploaded_at = userdata.get("uploadedAt", "Unknown")
            
            print(f"✅ Found resume data (uploaded: {uploaded_at})")
            
            # Format resume data for the agent
            import json
            formatted_data = json.dumps(resume_data, indent=2)
            
            return f"Resume data for user {user_id}:\n\n{formatted_data}"
            
        except Exception as e:
            print(f"❌ Error fetching resume data: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"Error fetching resume data: {str(e)}"

    return [
        get_user_goals, 
        get_assigned_projects, 
        get_tasks_for_project, 
        get_chat_history, 
        save_chat_history,
        save_resume_data,
        get_resume_data
    ]