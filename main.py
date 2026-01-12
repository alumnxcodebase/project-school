import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from routers import projects, chat, goals,tasks
from agents.learning_agent import get_learning_agent

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB Setup
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL"))
    db = client[os.getenv("DATABASE_NAME", "projects")]
    app.state.db = db

    # Initialize Agent
    app.state.agent = get_learning_agent(db)

    # Indexes
    await db.chats.create_index([("userId", 1), ("timestamp", 1)])

    print("🚀 API and Agent Ready")
    yield
    client.close()


app = FastAPI(title="Project + Agentic AI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(goals.router, prefix="/goals", tags=["Goals"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": "2026-01-06T15:24:00Z"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)