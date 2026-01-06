# Project + AI Agent Management API

A production-ready FastAPI application with MongoDB Atlas for comprehensive project management, task tracking, goal management, AI agent operations, and chat history.

## 🎯 Features

- ✅ **Projects Management** - Complete CRUD operations for projects
- ✅ **Tasks Management** - Task tracking within projects
- ✅ **Goals Tracking** - User-specific goal management
- ✅ **AI Agents** - Manage AI agents for different users
- ✅ **Chat History** - Store and retrieve user chat conversations
- ✅ **MongoDB Atlas Integration** - Scalable cloud database
- ✅ **Async Operations** - High-performance async endpoints
- ✅ **CORS Enabled** - Ready for frontend integration
- ✅ **Modern Lifespan Management** - Proper startup/shutdown handling
- ✅ **Auto-indexed Collections** - Optimized query performance
- ✅ **Interactive API Docs** - Built-in Swagger UI

## 📋 Prerequisites

- Python 3.8 or higher
- MongoDB Atlas account (free tier available)
- pip (Python package manager)

## 🚀 Quick Start

### 1. Setup Project Directory

```bash
mkdir project-ai-management
cd project-ai-management
```

### 2. Install Dependencies

```bash
# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file in the project root:

```env
MONGODB_URL=mongodb+srv://agriculture_admin:YOUR_PASSWORD_HERE@agriculture.ayck7vs.mongodb.net/?appName=Agriculture
DATABASE_NAME=projects
```

**Important:** Replace `YOUR_PASSWORD_HERE` with your actual MongoDB password!

### 4. Verify MongoDB Connection

```bash
python test_connection.py
```

Expected output:
```
✅ Successfully connected to MongoDB Atlas!
📁 Existing collections in 'projects' database:
   (Collections will be created automatically)
```

### 5. Start the API Server

```bash
python main.py
```

Expected output:
```
✅ Connected to MongoDB: projects
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 6. Access the API

- **API Root**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 📚 API Endpoints

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API information |
| GET | `/health` | Health check |

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/project` | Create a new project |
| GET | `/project` | Get all projects |

### Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/project-tasks` | Create a new task |

### Goals

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/goals` | Create a new goal |
| GET | `/goals` | Get all goals (optional userId filter) |

### AI Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ai-agent` | Create a new AI agent |
| GET | `/ai-agent` | Get all AI agents (optional userId filter) |

### Chat History

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat` | Save a chat message |
| GET | `/chat/{user_id}` | Get chat history for a user |

## 🧪 Testing

### Test Projects

```bash
python projects.py
```

### Test Goals

```bash
python goals.py
```

### Test AI Agents

```bash
python ai_agents.py
```

## 📝 Usage Examples

### Create a Project

```bash
curl -X POST "http://localhost:8000/project" \
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
  "id": "677c1a2d3e4f567890abcdef",
  "name": "AI Training Platform",
  "description": "Full Stack AI Engineer Program",
  "status": "active",
  "start_date": "2025-01-10T00:00:00",
  "end_date": "2025-03-31T00:00:00",
  "created_at": "2025-01-07T10:00:00",
  "updated_at": "2025-01-07T10:00:00"
}
```

### Create a Task

```bash
curl -X POST "http://localhost:8000/project-tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "677c1a2d3e4f567890abcdef",
    "title": "Setup Development Environment",
    "description": "Install Python, FastAPI, and MongoDB",
    "status": "in_progress",
    "priority": "high",
    "assigned_to": "developer@example.com"
  }'
```

### Create a Goal

```bash
curl -X POST "http://localhost:8000/goals" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user123",
    "goals": "Complete Full Stack AI Engineer Course by March 2025"
  }'
```

### Get Goals for a User

```bash
curl -X GET "http://localhost:8000/goals?userId=user123"
```

### Create an AI Agent

```bash
curl -X POST "http://localhost:8000/ai-agent" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "vijender",
    "name": "Chitti"
  }'
```

### Get AI Agents for a User

```bash
curl -X GET "http://localhost:8000/ai-agent?userId=vijender"
```

### Save a Chat Message

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user123",
    "userType": "student",
    "message": "Hello, I need help with Python async programming"
  }'
```

### Get Chat History

```bash
curl -X GET "http://localhost:8000/chat/user123"
```

## 📊 Data Models

### Project Schema

```json
{
  "id": "ObjectId (auto-generated)",
  "name": "string (required)",
  "description": "string (optional)",
  "status": "string (default: active)",
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
  "project_id": "string (required)",
  "title": "string (required)",
  "description": "string (optional)",
  "status": "string (default: pending)",
  "priority": "string (default: medium)",
  "assigned_to": "string (optional)",
  "due_date": "datetime (optional)",
  "created_at": "datetime (auto)",
  "updated_at": "datetime (auto)"
}
```

### Goal Schema

```json
{
  "id": "ObjectId (auto-generated)",
  "userId": "string (required)",
  "goals": "string (required)",
  "created_at": "datetime (auto)",
  "updated_at": "datetime (auto)"
}
```

### AI Agent Schema

```json
{
  "id": "ObjectId (auto-generated)",
  "userId": "string (required)",
  "name": "string (required)",
  "created_at": "datetime (auto)",
  "updated_at": "datetime (auto)"
}
```

### Chat Schema

```json
{
  "id": "ObjectId (auto-generated)",
  "userId": "string (required)",
  "userType": "string (required)",
  "message": "string (required)",
  "timestamp": "datetime (auto)"
}
```

## 📁 Project Structure

```
project-ai-management/
├── main.py              # FastAPI application
├── test_connection.py   # MongoDB connection test
├── projects.py          # Test script for projects
├── goals.py             # Test script for goals
├── ai_agents.py         # Test script for AI agents
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables (create this)
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## 🗄️ MongoDB Collections

The API automatically creates and manages these collections:

| Collection | Description | Indexes |
|------------|-------------|---------|
| `projects` | Project documents | name, status |
| `tasks` | Task documents | project_id |
| `goals` | User goals | - |
| `ai_agents` | AI agent configurations | - |
| `chats` | Chat message history | userId + timestamp (compound) |

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| MONGODB_URL | MongoDB Atlas connection string | - | Yes |
| DATABASE_NAME | Database name | projects | No |

### MongoDB Atlas Setup

1. **Create Account**: https://www.mongodb.com/cloud/atlas
2. **Create Free Cluster**: Select M0 (free tier)
3. **Database User**: Create with username and password
4. **Network Access**: Add your IP or use `0.0.0.0/0` (for testing only)
5. **Get Connection String**: Click "Connect" → "Connect your application"
6. **Update `.env`**: Paste connection string and replace `<password>`

## 🆕 Key Improvements in This Version

### 1. Modern Lifespan Management
- Uses FastAPI's `lifespan` context manager (recommended approach)
- Replaces deprecated `@app.on_event("startup")` and `@app.on_event("shutdown")`
- Proper resource cleanup on shutdown

### 2. Pydantic V2 Compatibility
- Uses `ConfigDict` instead of `Config` class
- Compatible with Pydantic 2.x

### 3. Enhanced Indexing
- Compound index on `chats` collection: `(userId, timestamp)`
- Optimized for chat history queries sorted by time

### 4. Chat Feature
- New `/chat` endpoint for storing conversation history
- Retrieve chat history per user in chronological order
- Support for different user types (student, teacher, admin, etc.)

### 5. Cleaner Code Structure
- More concise endpoint implementations
- Better error handling
- Consistent response patterns

## 🐛 Troubleshooting

### Connection Errors

**Problem**: Cannot connect to MongoDB
```bash
# Solution 1: Test connection
python test_connection.py

# Solution 2: Check .env file
# Make sure password is correct and no < > brackets remain

# Solution 3: Verify IP whitelist
# In MongoDB Atlas → Network Access → Add current IP
```

### Startup Errors

**Problem**: Server fails to start
```bash
# Check for syntax errors
python -m py_compile main.py

# Verify all dependencies installed
pip install -r requirements.txt

# Check MongoDB connection string
# Connection string should be one line, no line breaks
```

### 404 Errors

**Problem**: Endpoints return 404 Not Found
```bash
# Solution: Check endpoint paths
# Correct paths:
#   /project (not /save-project)
#   /project-tasks (not /save-project-tasks)
#   /goals
#   /ai-agent
#   /chat

# Visit http://localhost:8000/docs to see all available endpoints
```

### Import Errors

**Problem**: ModuleNotFoundError
```bash
# Activate virtual environment first
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Then install dependencies
pip install -r requirements.txt
```

## 🔒 Security Best Practices

### Development
- ✅ Use `.env` file for sensitive data
- ✅ Never commit `.env` to version control
- ✅ Use `0.0.0.0/0` for MongoDB IP whitelist (testing only)

### Production
- ✅ Use environment variables on hosting platform
- ✅ Whitelist only necessary IPs in MongoDB Atlas
- ✅ Configure CORS for specific domains only
- ✅ Enable MongoDB authentication
- ✅ Use HTTPS/TLS for API connections
- ✅ Implement rate limiting
- ✅ Add API authentication (JWT tokens)

## 📈 Performance Optimization

### Database Indexes
The application automatically creates indexes on startup:
- `projects.name` - Fast project lookup by name
- `projects.status` - Filter projects by status
- `tasks.project_id` - Retrieve all tasks for a project
- `chats.(userId, timestamp)` - Efficient chat history queries

### Async Operations
- All database operations are asynchronous
- Non-blocking I/O for better concurrency
- Handles multiple requests efficiently

### Connection Pooling
- Motor driver manages connection pool automatically
- Optimized for production workloads
- Automatic connection recovery

## 🚢 Deployment

### Local Development
```bash
python main.py
```

### Production with Uvicorn
```bash
# Single worker
uvicorn main:app --host 0.0.0.0 --port 8000

# Multiple workers for better performance
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker Deployment
```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Environment Variables in Production
Set these on your hosting platform (Heroku, AWS, Railway, etc.):
```bash
MONGODB_URL=mongodb+srv://...
DATABASE_NAME=projects
```

## 🧪 Testing Strategy

### Manual Testing
1. Use interactive docs: http://localhost:8000/docs
2. Click "Try it out" on any endpoint
3. Fill in request body
4. Click "Execute"

### Automated Testing
Run the provided test scripts:
```bash
python projects.py   # Test project endpoints
python goals.py      # Test goal endpoints
python ai_agents.py  # Test AI agent endpoints
```

### Testing Chat Feature
```python
import requests

BASE_URL = "http://localhost:8000"

# Create chat messages
messages = [
    {"userId": "user123", "userType": "student", "message": "Hello!"},
    {"userId": "user123", "userType": "ai", "message": "Hi! How can I help?"},
]

for msg in messages:
    requests.post(f"{BASE_URL}/chat", json=msg)

# Retrieve chat history
response = requests.get(f"{BASE_URL}/chat/user123")
print(response.json())
```

## 📊 Monitoring

### Health Check Endpoint
```bash
curl http://localhost:8000/health
```

### Check Database Connection
```python
# The server prints connection status on startup
✅ Connected to MongoDB: projects
```

### Monitor Logs
```bash
# The server logs all requests
INFO:     127.0.0.1:52000 - "POST /project HTTP/1.1" 201 Created
```

## 🎓 Built For

This API powers the **Alumnx AI Labs** platform - providing comprehensive project management, AI agent orchestration, and student interaction tracking for the Full Stack AI Engineer Program.

## 📝 API Versioning

Current Version: **2.0.0**

Version includes:
- Modern FastAPI patterns (lifespan management)
- Pydantic V2 compatibility
- Chat feature
- Enhanced indexing

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

MIT License - Free to use for personal and commercial projects.

## 📞 Support

- **Documentation**: http://localhost:8000/docs
- **MongoDB Issues**: Check connection string and IP whitelist
- **API Issues**: Check endpoint paths in interactive docs

## 🙏 Acknowledgments

- FastAPI for the excellent web framework
- MongoDB Atlas for scalable database hosting
- Motor for async MongoDB operations
- Pydantic for data validation

---

**Made with ❤️ for Alumnx AI Labs - Empowering the next generation of AI Engineers**
