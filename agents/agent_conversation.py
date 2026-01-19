from datetime import datetime, date
from bson import ObjectId
import httpx


async def check_and_send_task_reminders(db, user_id: str):
    """
    Get active tasks and send WhatsApp reminders.
    """
    try:
        print(f"\n📅 Checking active tasks for user: {user_id}")
        
        # Get user details
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        user_name = user.get("fullName", user.get("userName", "Student")) if user else "Student"
        
        # Get user's assignments
        assignment = await db.assignments.find_one({"userId": user_id})
        
        if not assignment or not assignment.get("tasks"):
            print("ℹ️ No tasks found for user")
            return {
                "status": "success",
                "message": "No tasks assigned to user",
                "reminders_sent": 0,
                "tasks": []
            }
        
        print(f"📋 Total tasks in assignment: {len(assignment.get('tasks', []))}")
        
        # Filter active tasks
        active_tasks = []
        
        for idx, task_assignment in enumerate(assignment.get("tasks", [])):
            task_status = task_assignment.get("taskStatus")
            print(f"   Task {idx + 1}: taskStatus = '{task_status}' (type: {type(task_status)})")
            
            if task_status == "active":
                
                # Get task details
                task_id = task_assignment.get("taskId")
                print(f"   Found active task with taskId: {task_id}")
                task = await db.tasks.find_one({"_id": ObjectId(task_id)})
                
                if task:
                    task_name = task.get("name", task.get("title", "Unnamed Task"))
                    active_tasks.append(task_name)
                    print(f"   ✅ Active task: {task_name}")
                else:
                    print(f"   ⚠️ Task document not found for taskId: {task_id}")
        
        if not active_tasks:
            print("ℹ️ No active tasks")
            return {
                "status": "success",
                "message": "No active tasks",
                "reminders_sent": 0,
                "tasks": []
            }
        
        # Prepare task list
        task_count = len(active_tasks)
        task_list = "\n".join([f"{idx}. {task_name}" for idx, task_name in enumerate(active_tasks, 1)])
        
        # Prepare message variables
        task_message = f"You have {task_count} task{'s' if task_count > 1 else ''} to complete:\n\n{task_list}"
        
        print(f"\n📱 Sending WhatsApp reminder for {task_count} tasks")
        
        # Call WhatsApp API with multiple message variables
        whatsapp_payload = {
            "userIds": user_id,
            "templateId": "6926",
            "messageVariables": {
                "1": user_name,
                "2": "",
                "3": task_message
            }
        }
        
        print(f"📤 Payload: {whatsapp_payload}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.alumnx.com/api/communication/dispatchWhatsappByUserId",
                json=whatsapp_payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            response_text = await response.aread()
            print(f"📥 Response status: {response.status_code}")
            print(f"📥 Response body: {response_text.decode()}")
            
            if response.status_code == 200:
                print("✅ WhatsApp reminder sent successfully")
                result = response.json()
                return {
                    "status": "success",
                    "message": f"Reminder sent for {task_count} tasks",
                    "reminders_sent": task_count,
                    "tasks": active_tasks,
                    "whatsapp_response": result
                }
            else:
                print(f"❌ WhatsApp API error: {response.status_code}")
                return {
                    "status": "error",
                    "message": f"WhatsApp API error: {response.status_code} - {response_text.decode()}",
                    "reminders_sent": 0,
                    "tasks": active_tasks
                }
                
    except Exception as e:
        print(f"❌ Error in task reminder check: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e),
            "reminders_sent": 0,
            "tasks": []
        }