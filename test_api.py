#!/bin/bash

# API Testing Script using cURL
# Usage: chmod +x test_api.sh && ./test_api.sh

BASE_URL="http://localhost:8000"
USER_ID="test_user_001"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 API Testing Suite${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Base URL: ${BASE_URL}"
echo -e "Test User: ${USER_ID}"
echo ""

# Counter for tests
PASSED=0
FAILED=0

# Function to test endpoint
test_endpoint() {
    local name=$1
    local method=$2
    local endpoint=$3
    local data=$4
    
    echo -e "\n${YELLOW}Testing: ${name}${NC}"
    echo "Endpoint: ${method} ${endpoint}"
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "${BASE_URL}${endpoint}")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}${endpoint}" \
            -H "Content-Type: application/json" \
            -d "${data}")
    elif [ "$method" = "PUT" ]; then
        response=$(curl -s -w "\n%{http_code}" -X PUT "${BASE_URL}${endpoint}" \
            -H "Content-Type: application/json" \
            -d "${data}")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo -e "${GREEN}✅ PASS (Status: ${http_code})${NC}"
        echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}❌ FAIL (Status: ${http_code})${NC}"
        echo "$body"
        FAILED=$((FAILED + 1))
    fi
}

# 1. Health Check
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}1. HEALTH CHECK${NC}"
echo -e "${BLUE}========================================${NC}"
test_endpoint "Health Check" "GET" "/health"

# 2. Goals
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}2. GOALS ENDPOINTS${NC}"
echo -e "${BLUE}========================================${NC}"

test_endpoint "Create Goals" "POST" "/goals/" '{
  "userId": "'"${USER_ID}"'",
  "goals": [
    "Learn Python and FastAPI",
    "Build a full-stack application",
    "Master LangGraph and AI agents"
  ]
}'

test_endpoint "Get User Goals" "GET" "/goals/?userId=${USER_ID}"

# 3. Projects
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}3. PROJECTS ENDPOINTS${NC}"
echo -e "${BLUE}========================================${NC}"

PROJECT_RESPONSE=$(curl -s -X POST "${BASE_URL}/projects/" \
    -H "Content-Type: application/json" \
    -d '{
  "name": "AI Learning Platform",
  "description": "Build a platform with FastAPI, LangGraph, and AI agents",
  "status": "active"
}')

PROJECT_ID=$(echo "$PROJECT_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

test_endpoint "Create Project" "POST" "/projects/" '{
  "name": "AI Learning Platform",
  "description": "Build a platform with FastAPI, LangGraph, and AI agents",
  "status": "active"
}'

test_endpoint "List Projects" "GET" "/projects/"

if [ -n "$PROJECT_ID" ]; then
    test_endpoint "Get Project by ID" "GET" "/projects/${PROJECT_ID}"
    test_endpoint "Get Project Stats" "GET" "/projects/${PROJECT_ID}/stats"
    
    # 4. Tasks
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}4. TASKS ENDPOINTS${NC}"
    echo -e "${BLUE}========================================${NC}"
    
    TASK_RESPONSE=$(curl -s -X POST "${BASE_URL}/tasks/" \
        -H "Content-Type: application/json" \
        -d '{
      "project_id": "'"${PROJECT_ID}"'",
      "title": "Set up FastAPI backend with MongoDB",
      "status": "in_progress",
      "assigned_to": "'"${USER_ID}"'"
    }')
    
    TASK_ID=$(echo "$TASK_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
    
    test_endpoint "Create Task" "POST" "/tasks/" '{
      "project_id": "'"${PROJECT_ID}"'",
      "title": "Set up FastAPI backend with MongoDB",
      "status": "in_progress",
      "assigned_to": "'"${USER_ID}"'"
    }'
    
    test_endpoint "Get User Tasks" "GET" "/tasks/user/${USER_ID}"
    
    if [ -n "$TASK_ID" ]; then
        test_endpoint "Update Task" "PUT" "/tasks/${TASK_ID}" '{
          "status": "completed",
          "title": "Set up FastAPI backend with MongoDB - DONE"
        }'
    fi
fi

# 5. Chat
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}5. CHAT ENDPOINTS${NC}"
echo -e "${BLUE}========================================${NC}"

test_endpoint "Chat with Agent" "POST" "/chat/agent" '{
  "userId": "'"${USER_ID}"'",
  "userType": "user",
  "message": "Hello! Can you help me understand my current goals?",
  "timestamp": "'"$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")"'"
}'

sleep 1

test_endpoint "Get Chat History" "GET" "/chat/history/${USER_ID}"

test_endpoint "Follow-up Chat" "POST" "/chat/agent" '{
  "userId": "'"${USER_ID}"'",
  "userType": "user",
  "message": "What should I focus on next?",
  "timestamp": "'"$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")"'"
}'

# Summary
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}TEST SUMMARY${NC}"
echo -e "${BLUE}========================================${NC}"
TOTAL=$((PASSED + FAILED))
echo -e "Total Tests: ${TOTAL}"
echo -e "${GREEN}Passed: ${PASSED}${NC}"
echo -e "${RED}Failed: ${FAILED}${NC}"

if [ $TOTAL -gt 0 ]; then
    SUCCESS_RATE=$(awk "BEGIN {printf \"%.1f\", (${PASSED}/${TOTAL})*100}")
    echo -e "Success Rate: ${SUCCESS_RATE}%"
fi

if [ -n "$PROJECT_ID" ]; then
    echo -e "\n${BLUE}Created Test Data:${NC}"
    echo -e "Project ID: ${PROJECT_ID}"
    [ -n "$TASK_ID" ] && echo -e "Task ID: ${TASK_ID}"
fi

echo -e "\n${BLUE}========================================${NC}"

# Exit with appropriate code
if [ $FAILED -eq 0 ]; then
    exit 0
else
    exit 1
fi