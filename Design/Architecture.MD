# System Architecture & Design Documentation

## 1. High-Level System Architecture

The system is designed with a **clear separation of concerns**, moving from the client-facing API gateway through validation and reasoning layers to the persistent data store.

### Architecture Layers

#### API Gateway (FastAPI)
- Orchestrated in `main.py`
- Manages:
  - Application lifespan
  - Middleware
  - Primary database connection

#### Modular Routers
- Located in the `/routers` directory
- Files include:
  - `chat.py`
  - `goals.py`
  - `projects.py`
  - `tasks.py`
- Responsibilities:
  - Domain-specific logic
  - Endpoint routing
  - Service orchestration

#### Data Validation (Pydantic)
- Defined in:
  - `models.py`
  - Local schemas within routers
- Ensures:
  - Incoming JSON payloads match required formats
  - Type safety before reaching business logic

#### Agentic Brain (LangChain & LangGraph)
- Implemented in `learning_agent.py`
- Responsibilities:
  - LangChain interfaces with the Gemini LLM
  - LangGraph orchestrates a state-driven **ReAct** (Reason + Act) pattern
  - Tool-calling and multi-step reasoning

#### Persistence Layer (MongoDB)
- Uses **Motor (AsyncIOMotorClient)**
- Provides:
  - Asynchronous, non-blocking data storage
  - Persistence for chats, goals, projects, tasks, and assignments

---

## 2. Request Lifecycle (Flow Diagram – Textual)

The following sequence describes the **end-to-end lifecycle** of a user request, specifically for **task recommendation**.

1. **Entry**
   - User sends a `POST` request to `/chat/agent`

2. **Validation**
   - FastAPI validates input using the `AgentRequest` Pydantic model
   - Validates:
     - `userId`
     - `message` content

3. **Handoff**
   - Validated request is passed to `run_learning_agent`
   - Located in the Agent Layer

4. **Reasoning (LangGraph)**
   - Agent determines user intent
   - If task assignment is needed, enters **Task Assignment Mode**

5. **Tools (Actions)**
   - Agent invokes tools such as:
     - `get_user_goals`
     - `get_project_tasks`
   - Performs async queries against MongoDB

6. **LLM Synthesis**
   - LangChain sends:
     - Retrieved context
     - System instructions
   - Gemini LLM generates the final response

7. **Parsing**
   - Raw LLM output is parsed into structured JSON
   - Produces a list of recommended tasks

8. **Storage**
   - Entire interaction is stored in the `chats` collection
   - Enables history tracking and conversational context

---

## 3. Key Component Interaction Table

| Component   | Code Implementation | Primary Responsibility |
|------------|---------------------|------------------------|
| FastAPI | `app = FastAPI(...)` in `main.py` | Application lifecycle, middleware, request routing |
| Pydantic | `class Task(BaseModel)` in `models.py` | Data integrity, type safety, schema validation |
| Routers | `APIRouter()` in `tasks.py`, `chat.py`, etc. | API endpoint grouping and orchestration |
| LangGraph | `create_react_agent` in `learning_agent.py` | Multi-step reasoning and action loops |
| LangChain | `ChatGoogleGenerativeAI` in `learning_agent.py` | High-level interface to Gemini LLM |
| Database (Motor) | `AsyncIOMotorClient` in `main.py` | Async, non-blocking MongoDB access |

---

## 4. Database Schema Design

The database uses **specialized collections** to provide the AI agent with sufficient context for personalized guidance.

### Collections

#### Projects
- Stores metadata for:
  - Learning tracks
  - Curricula
  - Skill paths

#### Tasks
- Contains granular units of work
- Each task is associated with a `project_id`

#### Assignments
- Maps tasks to users
- Tracks:
  - `userId`
  - Completion status (`isCompleted`)
  - User/admin comments

#### Goals
- Stores user-defined career or learning objectives
- Used by the AI to:
  - Filter tasks
  - Improve relevance

#### Chats
- Maintains full user–agent conversation history
- Enables:
  - Context-aware responses
  - Conversational continuity

---

## 5. Summary

This architecture ensures:
- Clear separation of concerns
- Strong input validation
- Scalable agent reasoning
- Asynchronous, high-performance persistence
- Context-aware AI-driven task recommendations

