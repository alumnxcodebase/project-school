import os
import sys
import logging
import asyncio
from datetime import datetime
from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("project-school")

from routers import projects, chat, goals, tasks, assignedprojects, preferences, quizzes, assessments, projectschool, me
from agents.learning_agent import get_learning_agent

load_dotenv()

async def create_db_indexes(db):
    logger.info("🔧 Starting index creation...")
    try:
        await db.chats.create_index([("userId", 1), ("timestamp", 1)])
        await db.agents.create_index([("userId", 1)], unique=True)
        await db.resources.create_index([("taskId", 1)])
        await db.resources.create_index([("projectId", 1)])
        await db.resources.create_index([("userId", 1)])
        await db.resources.create_index([("name", 1)])
        await db.assignedprojects.create_index([("userId", 1)])
        await db.assignedprojects.create_index([("userId", 1), ("sequenceId", 1)])
        await db.preferences.create_index([("userId", 1)], unique=True)
        logger.info("✅ All indexes verified/created")
    except Exception as e:
        logger.warning(f"⚠️ Index creation notice: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    mongodb_url = os.getenv("MONGODB_URL")
    db_name = os.getenv("DATABASE_NAME", "projects")

    if not mongodb_url:
        logger.error("❌ MONGODB_URL not found in environment!")

    try:
        logger.info(f"🔌 Connecting to MongoDB: {mongodb_url[:20]}...")
        client = AsyncIOMotorClient(mongodb_url)
        await client.admin.command('ping')
        db = client[db_name]
        app.state.db = db
        logger.info(f"✅ Connected to database: {db_name}")
        app.state.agent = get_learning_agent(db)
    except Exception as e:
        logger.error(f"Critical error during startup: {str(e)}")
        app.state.db = None

    main_mongodb_url = os.getenv("MAIN_MONGODB_URL")
    main_client = None

    if main_mongodb_url:
        main_mongodb_url = main_mongodb_url.strip('"').strip("'")
        try:
            log_url = main_mongodb_url.split('@')[-1] if '@' in main_mongodb_url else main_mongodb_url[:20]
            logger.info(f"🔌 Connecting to Main MongoDB: {log_url}...")
            main_client = AsyncIOMotorClient(main_mongodb_url, serverSelectionTimeoutMS=5000)
            await main_client.admin.command('ping')
            app.state.main_db = main_client.get_default_database()
        except Exception as e:
            app.state.main_db = None
    else:
        app.state.main_db = None

    logger.info("🚀 API Ready")
    yield

    if hasattr(app.state, 'db') and app.state.db is not None:
        client.close()
        logger.info("🔌 Projects Database connection closed")

    if main_client:
        main_client.close()
        logger.info("🔌 Main Database connection closed")

app = FastAPI(title="Project + Agentic AI API", lifespan=lifespan, redirect_slashes=False)

# ============================================================================
# API KEY VERIFICATION
# ============================================================================
async def verify_api_key(request: Request, x_api_key: str = Header(None)):
    db = request.app.state.db
    if not x_api_key:
        request.state.userId = ""
        request.state.userName = ""
        return None
    record = await db.api_keys.find_one({"apiKey": x_api_key, "isActive": True})
    if not record:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    request.state.userId = str(record.get("userId", ""))
    request.state.userName = str(record.get("userName", ""))
    return record

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error - Check server logs", "error": str(exc)},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*alumnx\.com|http://localhost:3000|http://127.0.0.1:3000",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    logger.info(f"✅ {request.method} {request.url.path} -> {response.status_code}")
    return response

# ============================================================================
# ROUTERS
# ============================================================================
app.include_router(goals.router, prefix="/goals", tags=["Goals"], dependencies=[Depends(verify_api_key)])
app.include_router(projects.router, prefix="/projects", tags=["Projects"], dependencies=[Depends(verify_api_key)])
app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"], dependencies=[Depends(verify_api_key)])
app.include_router(chat.router, prefix="/chat", tags=["Chat"], dependencies=[Depends(verify_api_key)])
app.include_router(assignedprojects.router, prefix="/assignedprojects", tags=["Assigned Projects"], dependencies=[Depends(verify_api_key)])
app.include_router(preferences.router, prefix="/preferences", tags=["Preferences"], dependencies=[Depends(verify_api_key)])
app.include_router(quizzes.router, prefix="/quizzes", tags=["Quizzes"], dependencies=[Depends(verify_api_key)])
app.include_router(assessments.router, prefix="/assessments", tags=["Assessments"], dependencies=[Depends(verify_api_key)])

# ✅ /me router - automatically resolves user from API key, no userId needed in request
app.include_router(me.router, prefix="/me", tags=["Me"], dependencies=[Depends(verify_api_key)])

# These are NOT protected - open access
app.include_router(projectschool.router, prefix="/api/projectschool", tags=["Project School"])

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    db_status = "Connected" if hasattr(app.state, 'db') and app.state.db is not None else "Disconnected"
    return {
        "status": "healthy",
        "database": db_status,
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)