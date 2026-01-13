# Project + Agentic AI Management API

A production-ready FastAPI application powered by MongoDB Atlas that supports:

- Project & Task Management (CRUD)
- Goal Tracking
- AI Agent Registry
- Agentic AI Chat (context-aware)
- Chat History Storage

---

## Features

- Projects & Tasks CRUD
- Goals management
- AI Agent registry
- Agentic chat using LangGraph
- MongoDB Atlas (async via Motor)
- FastAPI lifespan management
- Pydantic v2 compatible

---

## Prerequisites

- Python 3.9+
- MongoDB Atlas or local MongoDB
- pip / virtualenv

---

## Installation

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate
pip install -r requirements.txt
```

---

## Environment Variables (.env)

```env
MONGODB_URL=mongodb+srv://<username>:<password>@cluster.mongodb.net/?appName=Agriculture
DATABASE_NAME=projects
```

---

## Run the App

```bash
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## API Docs

- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health

---

## Core Endpoints

### Projects

- POST /project
- GET /project
- GET /project/{id}
- PUT /project/{id}
- DELETE /project/{id}
- GET /project/{id}/stats

### Tasks

- POST /project-tasks
- GET /project-tasks
- PUT /project-tasks/{id}
- DELETE /project-tasks/{id}

### Goals

- POST /goals
- GET /goals?userId=

### AI Agents

- POST /ai-agent
- GET /ai-agent?userId=

### Chat

- POST /chat
- GET /chat/{userId}
- POST /chat/agent

---

## License

MIT
##Change Made by Bhavana
