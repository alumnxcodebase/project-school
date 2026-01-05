# Project Management API with MongoDB

A production-ready FastAPI application with MongoDB for managing projects and tasks with full CRUD operations.

## Features

- ✅ Complete CRUD operations for Projects and Tasks
- ✅ MongoDB integration with Motor (async driver)
- ✅ Environment variable configuration
- ✅ Automatic database indexing for performance
- ✅ Project-Task relationship management
- ✅ Project statistics endpoint
- ✅ Input validation with Pydantic
- ✅ Auto-generated API documentation
- ✅ CORS enabled for frontend integration

## Prerequisites

- Python 3.8 or higher
- MongoDB (local installation or MongoDB Atlas account)
- pip (Python package manager)

## Installation

### 1. Clone/Create Project Directory

```bash
mkdir project-management-api
cd project-management-api
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure MongoDB Connection

**You already have a MongoDB Atlas cluster!** 

Edit the `.env` file and replace `<db_password>` with your actual password:

```env
MONGODB_URL=mongodb+srv://agriculture_admin:YOUR_ACTUAL_PASSWORD@agriculture.ayck7vs.mongodb.net/?appName=Agriculture
DATABASE_NAME=projects
```

**Database Structure:**
- Database name: `projects`
- Collection 1: `projects` (stores project documents)
- Collection 2: `tasks` (stores task documents)

**Test the connection:**
```bash
python test_connection.py
```

### 5. Start MongoDB (if using local)

```bash
# On macOS with Homebrew
brew services start mongodb-community

# On Ubuntu/Linux
sudo systemctl start mongod

# On Windows
net start MongoDB
```

## Running the Application

```bash
python main.py
```

Or using uvicorn directly:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at: `http://localhost:8000`

## API Documentation

Interactive API documentation:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## MongoDB Collections

The application automatically creates two collections:
- `projects` - Stores project documents
- `tasks` - Stores task documents with project_id references

Indexes are automatically created on:
- `projects.name`
- `projects.status`
- `tasks.project_id`
- `tasks.status`
- `tasks.priority`

## API Endpoints

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/project` | Create a new project |
| GET | `/project` | Get all projects |
| GET | `/project/{project_id}` | Get a specific project |
| PUT | `/project/{project_id}` | Update a project |
| DELETE | `/project/{project_id}` | Delete a project |
| GET | `/project/{project_id}/stats` | Get project statistics |

### Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/project-tasks` | Create a new task |
| GET | `/project-tasks` | Get all tasks (optional project_id filter) |
| GET | `/project-tasks/{task_id}` | Get a specific task |
| PUT | `/project-tasks/{task_id}` | Update a task |
| DELETE | `/project-tasks/{task_id}` | Delete a task |

## Usage Examples

### 1. Create a Project

```bash
curl -X POST "http://localhost:8000/save-project" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AI Training Platform",
    "description": "Full Stack AI Engineer Program",
    "status": "active",
    "start_date": "2025-01-10T00:00:00",
    "end_date": "2025-03-31T00:00:00"
  }'
```

**Response:**
```json
{
  "id": "677b2c8d1234567890abcdef",
  "name": "AI Training Platform",
  "description": "Full Stack AI Engineer Program",
  "status": "active",
  "start_date": "2025-01-10T00:00:00",
  "end_date": "2025-03-31T00:00:00",
  "created_at": "2025-01-06T10:30:00",
  "updated_at": "2025-01-06T10:30:00"
}
```

### 2. Create a Task

```bash
curl -X POST "http://localhost:8000/save-project-tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "677b2c8d1234567890abcdef",
    "title": "Develop RAG System Module",
    "description": "Create comprehensive content on RAG systems",
    "status": "in_progress",
    "priority": "high",
    "assigned_to": "vijender@alumnxai.com",
    "due_date": "2025-01-20T00:00:00"
  }'
```

### 3. Get All Projects

```bash
curl -X GET "http://localhost:8000/save-project"
```

### 4. Get Tasks for a Project

```bash
curl -X GET "http://localhost:8000/save-project-tasks?project_id=677b2c8d1234567890abcdef"
```

### 5. Update a Task

```bash
curl -X PUT "http://localhost:8000/save-project-tasks/677b2c9d1234567890abcdef" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "completed",
    "description": "RAG system module completed with examples"
  }'
```

### 6. Get Project Statistics

```bash
curl -X GET "http://localhost:8000/save-project/677b2c8d1234567890abcdef/stats"
```

**Response:**
```json
{
  "total_tasks": 5,
  "pending": 2,
  "in_progress": 2,
  "completed": 1,
  "blocked": 0
}
```

## Data Models

### Project Schema
```json
{
  "id": "ObjectId (auto-generated)",
  "name": "string (required, 1-200 chars)",
  "description": "string (optional)",
  "status": "active|completed|on_hold|cancelled (default: active)",
  "start_date": "datetime (optional)",
  "end_date": "datetime (optional)",
  "created_at": "datetime (auto)",
  "updated_at": "datetime (auto)"
}
```

### Task Schema
```json
{
  "id": "ObjectId (auto-generated)",
  "project_id": "string (required, must be valid project ID)",
  "title": "string (required, 1-200 chars)",
  "description": "string (optional)",
  "status": "pending|in_progress|completed|blocked (default: pending)",
  "priority": "low|medium|high|urgent (default: medium)",
  "assigned_to": "string (optional)",
  "due_date": "datetime (optional)",
  "created_at": "datetime (auto)",
  "updated_at": "datetime (auto)"
}
```

## Testing with Python

Create a test file `test_mongodb.py`:

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Create project
project = {
    "name": "Full Stack AI Engineer Course",
    "description": "Alumnx AI Labs training program",
    "status": "active"
}

response = requests.post(f"{BASE_URL}/save-project", json=project)
project_result = response.json()
project_id = project_result["id"]
print(f"Created Project: {project_id}")

# Create task
task = {
    "project_id": project_id,
    "title": "RAG System Development",
    "status": "in_progress",
    "priority": "high"
}

response = requests.post(f"{BASE_URL}/save-project-tasks", json=task)
task_result = response.json()
print(f"Created Task: {task_result['id']}")

# Get statistics
response = requests.get(f"{BASE_URL}/save-project/{project_id}/stats")
print("Stats:", response.json())
```

## Your MongoDB Configuration

You're connected to MongoDB Atlas cluster:
- **Cluster**: agriculture.ayck7vs.mongodb.net
- **User**: agriculture_admin
- **Database**: projects
- **Collections**: projects, tasks (auto-created)

The collections will be automatically created when you first add data.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| MONGODB_URL | MongoDB connection string | mongodb://localhost:27017 |
| DATABASE_NAME | Database name | project_management |

## Error Handling

The API returns appropriate HTTP status codes:
- `200` - Success
- `201` - Created
- `204` - No Content (successful deletion)
- `400` - Bad Request (invalid input)
- `404` - Not Found
- `500` - Internal Server Error
- `503` - Service Unavailable (database connection issue)

## Performance Tips

1. **Indexing**: Indexes are automatically created on frequently queried fields
2. **Pagination**: Use `skip` and `limit` parameters for large datasets
3. **Connection Pooling**: Motor handles connection pooling automatically
4. **Async Operations**: All database operations are asynchronous for better performance

## Troubleshooting

**Connection Error:**
```
Error connecting to MongoDB: [Errno 61] Connection refused
```
- Check if MongoDB is running
- Verify connection string in .env file
- Check firewall settings

**Invalid ObjectId:**
```
Invalid project ID format
```
- Ensure you're using MongoDB ObjectId format (24 hex characters)
- Don't use UUIDs from previous version

**Authentication Failed:**
```
Authentication failed
```
- Verify username/password in connection string
- Check database user permissions in MongoDB Atlas

## Future Enhancements

- [ ] User authentication with JWT
- [ ] Role-based access control
- [ ] Task comments and attachments
- [ ] Email notifications
- [ ] Advanced search and filtering
- [ ] Real-time updates with WebSockets
- [ ] Data export (CSV, Excel)
- [ ] Task dependencies and subtasks

## License

MIT License


Updated by Deepanshu Sonwane .