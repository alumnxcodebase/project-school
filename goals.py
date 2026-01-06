"""
Test Goals API Endpoints
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

def print_response(title, response):
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"Status Code: {response.status_code}")
    if response.status_code != 204:
        print(f"Response: {json.dumps(response.json(), indent=2, default=str)}")
    print()

def main():
    print("Testing Goals API Endpoints")
    print("="*60)
    
    # Test 1: Create a goal
    print("\n1. Creating a new goal...")
    goal_data = {
        "userId": "user123",
        "goals": "Complete Full Stack AI Engineer Course by March 2025"
    }
    
    response = requests.post(f"{BASE_URL}/goals", json=goal_data)
    print_response("CREATE GOAL", response)
    goal = response.json()
    goal_id = goal["id"]
    
    # Test 2: Create another goal for same user
    print("\n2. Creating another goal for same user...")
    goal_data_2 = {
        "userId": "user123",
        "goals": "Build 3 AI projects for portfolio"
    }
    
    response = requests.post(f"{BASE_URL}/goals", json=goal_data_2)
    print_response("CREATE SECOND GOAL", response)
    goal_id_2 = response.json()["id"]
    
    # Test 3: Create goal for different user
    print("\n3. Creating goal for different user...")
    goal_data_3 = {
        "userId": "user456",
        "goals": "Master RAG systems and deploy to production"
    }
    
    response = requests.post(f"{BASE_URL}/goals", json=goal_data_3)
    print_response("CREATE GOAL FOR USER456", response)
    goal_id_3 = response.json()["id"]
    
    # Test 4: Get all goals
    print("\n4. Getting all goals...")
    response = requests.get(f"{BASE_URL}/goals")
    print_response("GET ALL GOALS", response)
    
    # Test 5: Get goals by userId (query parameter)
    print("\n5. Getting goals for user123 (query parameter)...")
    response = requests.get(f"{BASE_URL}/goals?userId=user123")
    print_response("GET GOALS FOR USER123", response)
    
    # Test 6: Get goals by userId (path parameter)
    print("\n6. Getting goals for user123 (path parameter)...")
    response = requests.get(f"{BASE_URL}/goals/user/user123")
    print_response("GET GOALS BY USER ID PATH", response)
    
    # Test 7: Get specific goal by ID
    print("\n7. Getting specific goal by ID...")
    response = requests.get(f"{BASE_URL}/goals/{goal_id}")
    print_response("GET GOAL BY ID", response)
    
    # Test 8: Update a goal
    print("\n8. Updating a goal...")
    update_data = {
        "goals": "Complete Full Stack AI Engineer Course by March 2025 - IN PROGRESS"
    }
    response = requests.put(f"{BASE_URL}/goals/{goal_id}", json=update_data)
    print_response("UPDATE GOAL", response)
    
    # Test 9: Update userId
    print("\n9. Updating userId...")
    update_data_2 = {
        "userId": "user789"
    }
    response = requests.put(f"{BASE_URL}/goals/{goal_id_2}", json=update_data_2)
    print_response("UPDATE USER ID", response)
    
    # Test 10: Get goals for user123 again (should show only 1 now)
    print("\n10. Getting goals for user123 again...")
    response = requests.get(f"{BASE_URL}/goals?userId=user123")
    print_response("GET GOALS FOR USER123 AFTER UPDATE", response)
    
    # Test 11: Delete a goal
    print("\n11. Deleting a goal...")
    response = requests.delete(f"{BASE_URL}/goals/{goal_id_3}")
    print_response("DELETE GOAL", response)
    
    # Test 12: Verify deletion
    print("\n12. Verifying deletion (should get 404)...")
    response = requests.get(f"{BASE_URL}/goals/{goal_id_3}")
    print_response("TRY TO GET DELETED GOAL", response)
    
    # Test 13: Get all goals to see final state
    print("\n13. Getting all goals (final state)...")
    response = requests.get(f"{BASE_URL}/goals")
    print_response("GET ALL GOALS - FINAL", response)
    
    print("\n" + "="*60)
    print("All tests completed!")
    print("="*60)
    print(f"\nCreated Goal IDs:")
    print(f"  - Goal 1: {goal_id}")
    print(f"  - Goal 2: {goal_id_2}")
    print(f"  - Goal 3: {goal_id_3} (deleted)")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Could not connect to the API server.")
        print("Please make sure the FastAPI server is running on http://localhost:8000")
        print("Start the server with: python main.py")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()