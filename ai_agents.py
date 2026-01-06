"""
Test AI Agent API Endpoints
"""

import requests
import json

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
    print("Testing AI Agent API Endpoints")
    print("="*60)
    
    # Test 1: Create an AI agent
    print("\n1. Creating a new AI agent...")
    agent_data = {
        "userId": "vijender123",
        "name": "Chitti"
    }
    
    response = requests.post(f"{BASE_URL}/ai-agent", json=agent_data)
    print_response("CREATE AI AGENT", response)
    agent = response.json()
    agent_id = agent["id"]
    
    # Test 2: Create another AI agent for same user
    print("\n2. Creating another AI agent for same user...")
    agent_data_2 = {
        "userId": "vijender123",
        "name": "JARVIS"
    }
    
    response = requests.post(f"{BASE_URL}/ai-agent", json=agent_data_2)
    print_response("CREATE SECOND AI AGENT", response)
    agent_id_2 = response.json()["id"]
    
    # Test 3: Create AI agent for different user
    print("\n3. Creating AI agent for different user...")
    agent_data_3 = {
        "userId": "user456",
        "name": "Friday"
    }
    
    response = requests.post(f"{BASE_URL}/ai-agent", json=agent_data_3)
    print_response("CREATE AI AGENT FOR USER456", response)
    agent_id_3 = response.json()["id"]
    
    # Test 4: Get all AI agents
    print("\n4. Getting all AI agents...")
    response = requests.get(f"{BASE_URL}/ai-agent")
    print_response("GET ALL AI AGENTS", response)
    
    # Test 5: Get AI agents by userId (query parameter)
    print("\n5. Getting AI agents for vijender123 (query parameter)...")
    response = requests.get(f"{BASE_URL}/ai-agent?userId=vijender123")
    print_response("GET AI AGENTS FOR VIJENDER123", response)
    
    # Test 6: Get AI agents by userId (path parameter)
    print("\n6. Getting AI agents for vijender123 (path parameter)...")
    response = requests.get(f"{BASE_URL}/ai-agent/user/vijender123")
    print_response("GET AI AGENTS BY USER ID PATH", response)
    
    # Test 7: Get specific AI agent by ID
    print("\n7. Getting specific AI agent by ID...")
    response = requests.get(f"{BASE_URL}/ai-agent/{agent_id}")
    print_response("GET AI AGENT BY ID", response)
    
    # Test 8: Update an AI agent name
    print("\n8. Updating AI agent name...")
    update_data = {
        "name": "Chitti 2.0 - Upgraded Version"
    }
    response = requests.put(f"{BASE_URL}/ai-agent/{agent_id}", json=update_data)
    print_response("UPDATE AI AGENT NAME", response)
    
    # Test 9: Update userId
    print("\n9. Updating userId for an agent...")
    update_data_2 = {
        "userId": "user789"
    }
    response = requests.put(f"{BASE_URL}/ai-agent/{agent_id_2}", json=update_data_2)
    print_response("UPDATE USER ID", response)
    
    # Test 10: Get AI agents for vijender123 again (should show only 1 now)
    print("\n10. Getting AI agents for vijender123 again...")
    response = requests.get(f"{BASE_URL}/ai-agent?userId=vijender123")
    print_response("GET AI AGENTS FOR VIJENDER123 AFTER UPDATE", response)
    
    # Test 11: Delete an AI agent
    print("\n11. Deleting an AI agent...")
    response = requests.delete(f"{BASE_URL}/ai-agent/{agent_id_3}")
    print_response("DELETE AI AGENT", response)
    
    # Test 12: Verify deletion
    print("\n12. Verifying deletion (should get 404)...")
    response = requests.get(f"{BASE_URL}/ai-agent/{agent_id_3}")
    print_response("TRY TO GET DELETED AI AGENT", response)
    
    # Test 13: Get all AI agents to see final state
    print("\n13. Getting all AI agents (final state)...")
    response = requests.get(f"{BASE_URL}/ai-agent")
    print_response("GET ALL AI AGENTS - FINAL", response)
    
    print("\n" + "="*60)
    print("All tests completed!")
    print("="*60)
    print(f"\nCreated AI Agent IDs:")
    print(f"  - Agent 1 (Chitti 2.0): {agent_id}")
    print(f"  - Agent 2 (JARVIS): {agent_id_2}")
    print(f"  - Agent 3 (Friday): {agent_id_3} (deleted)")

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