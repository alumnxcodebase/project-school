from bson import ObjectId


async def validate_and_enrich_tasks(db, user_id: str, parsed_tasks: list) -> tuple:
    """
    Validate tasks against assigned projects and enrich with project information.
    
    Returns:
        tuple: (enriched_tasks, validation_summary)
    """
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
    
    # Check for duplicates with assigned tasks
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
    
    return enriched_tasks, {
        "total_suggested": len(parsed_tasks),
        "valid": len(validated_tasks),
        "hallucinated": len(hallucinated_tasks),
        "final": len(enriched_tasks)
    }


def format_tasks_message(enriched_tasks: list) -> str:
    """Format tasks into a WhatsApp-friendly message"""
    if len(enriched_tasks) == 0:
        return "Looks like your Study Plan has not been prepared as yet. Please connect with Vijender asap."
    
    message_text = f"I've selected {len(enriched_tasks)} personalized tasks for your learning path:\n\n"
    for idx, task in enumerate(enriched_tasks, 1):
        message_text += f"{idx}. *{task['taskName']}*\n"
        message_text += f"   Project: {task['projectName']}\n"
        message_text += f"   Task ID: {task['taskId']}\n\n"
    
    return message_text
