import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"


def print_response(title, response):
    print(f"\n{'=' * 60}")
    print(title)
    print(f"{'=' * 60}")
    print(f"Status Code: {response.status_code}")
    if response.status_code != 204:
        try:
            print(f"Response: {json.dumps(response.json(), indent=2, default=str)}")
        except Exception:
            print("Response (raw):", response.text)
    print()


def main():
    print("Testing Project Management API with MongoDB")
    print("=" * 60)

    # 1. Health check
    print("\n1. Health Check...")
    response = requests.get(f"{BASE_URL}/health")
    print_response("HEALTH CHECK", response)

    if response.status_code != 200:
        print("❌ Health check failed")
        return

    # 2. Create a project
    print("\n2. Creating a new project...")
    project_data = {
        "name": "Alumnx AI Training Platform",
        "description": "Full Stack AI Engineer Program Development",
        "status": "active",
        "start_date": datetime.now().isoformat(),
        "end_date": (datetime.now() + timedelta(days=90)).isoformat()
    }

    response = requests.post(f"{BASE_URL}/project", json=project_data)
    print_response("CREATE PROJECT", response)

    if response.status_code != 201:
        print("❌ Project creation failed")
        return

    project = response.json()

    if "id" not in project:
        print("❌ 'id' missing in project response")
        print("Actual response:", project)
        return

    project_id = project["id"]

    # 3. Create tasks
    print("\n3. Creating tasks for the project...")
    tasks_data = [
        {
            "project_id": project_id,
            "title": "Setup RAG System Infrastructure",
            "description": "Setup vector database and embedding models",
            "status": "completed",
            "priority": "high",
            "assigned_to": "vijender@alumnxai.com",
            "due_date": (datetime.now() + timedelta(days=7)).isoformat()
        },
        {
            "project_id": project_id,
            "title": "Develop AI Agents Module",
            "description": "Build autonomous AI agents with LangChain",
            "status": "in_progress",
            "priority": "high",
            "assigned_to": "team@alumnxai.com",
            "due_date": (datetime.now() + timedelta(days=14)).isoformat()
        },
        {
            "project_id": project_id,
            "title": "Create LLM Fine-tuning Workshop",
            "description": "Hands-on workshop for model fine-tuning",
            "status": "pending",
            "priority": "medium",
            "assigned_to": "vijender@alumnxai.com",
            "due_date": (datetime.now() + timedelta(days=21)).isoformat()
        },
        {
            "project_id": project_id,
            "title": "Build Assessment Platform",
            "description": "MCQ and coding assessment system",
            "status": "pending",
            "priority": "urgent",
            "due_date": (datetime.now() + timedelta(days=28)).isoformat()
        }
    ]

    task_ids = []

    for task_data in tasks_data:
        response = requests.post(f"{BASE_URL}/project-tasks", json=task_data)
        print_response(f"CREATE TASK: {task_data['title']}", response)

        if response.status_code != 201:
            print(f"❌ Task creation failed: {task_data['title']}")
            continue

        task_response = response.json()

        if "id" not in task_response:
            print(f"❌ 'id' missing for task: {task_data['title']}")
            print(task_response)
            continue

        task_ids.append(task_response["id"])

    if len(task_ids) < 2:
        print("❌ Not enough tasks created to continue remaining tests")
        return

    # 4. Get all projects
    print("\n4. Getting all projects...")
    response = requests.get(f"{BASE_URL}/project")
    print_response("GET ALL PROJECTS", response)

    # 5. Get specific project
    print("\n5. Getting specific project...")
    response = requests.get(f"{BASE_URL}/project/{project_id}")
    print_response("GET PROJECT BY ID", response)

    # 6. Get all tasks for project
    print("\n6. Getting all tasks for the project...")
    response = requests.get(f"{BASE_URL}/project-tasks?project_id={project_id}")
    print_response("GET TASKS BY PROJECT", response)

    # 7. Update a task
    print("\n7. Updating task status...")
    update_data = {
        "status": "completed",
        "description": "AI Agents module completed with practical examples"
    }
    response = requests.put(
        f"{BASE_URL}/project-tasks/{task_ids[1]}",
        json=update_data
    )
    print_response("UPDATE TASK", response)

    # 8. Get project statistics
    print("\n8. Getting project statistics...")
    response = requests.get(f"{BASE_URL}/project/{project_id}/stats")
    print_response("PROJECT STATISTICS", response)

    # 9. Update project
    print("\n9. Updating project...")
    project_update = {
        "description": "Full Stack AI Engineer Program - Phase 1 in progress",
        "status": "active"
    }
    response = requests.put(
        f"{BASE_URL}/project/{project_id}",
        json=project_update
    )
    print_response("UPDATE PROJECT", response)

    # 10. Get specific task
    print("\n10. Getting specific task...")
    response = requests.get(f"{BASE_URL}/project-tasks/{task_ids[0]}")
    print_response("GET TASK BY ID", response)

    print("\n" + "=" * 60)
    print("✅ All tests completed successfully!")
    print("=" * 60)
    print(f"\nProject ID: {project_id}")
    print(f"Task IDs: {task_ids}")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Could not connect to the API server.")
        print("Please make sure:")
        print("1. MongoDB is running")
        print("2. .env file is configured with MONGODB_URL")
        print("3. FastAPI server is running: python main.py")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
