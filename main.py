import os
import sys
import logging
import asyncio
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("project-school")

from routers import projects, chat, goals, tasks, assignedprojects, preferences, notices, quizzes, assessments, projectschool
from agents.learning_agent import get_learning_agent

load_dotenv()

async def create_db_indexes(db):
    """Create database indexes in the background to avoid blocking startup."""
    logger.info("🔧 Starting index creation...")
    try:
        # Chats index
        await db.chats.create_index([("userId", 1), ("timestamp", 1)])
        await db.agents.create_index([("userId", 1)], unique=True)
        await db.resources.create_index([("taskId", 1)])
        await db.resources.create_index([("projectId", 1)])
        await db.resources.create_index([("userId", 1)])
        await db.resources.create_index([("name", 1)])
        await db.assignedprojects.create_index([("userId", 1)])
        await db.assignedprojects.create_index([("userId", 1), ("sequenceId", 1)])
        await db.preferences.create_index([("userId", 1)], unique=True)
        await db.notices.create_index([("createdAt", -1)])
        logger.info("✅ All indexes verified/created")
    except Exception as e:
        logger.warning(f"⚠️ Index creation notice: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB Setup
    mongodb_url = os.getenv("MONGODB_URL")
    db_name = os.getenv("DATABASE_NAME", "projects")
    
    if not mongodb_url:
        logger.error("❌ MONGODB_URL not found in environment!")
        # We don't raise here to allow app to start so health check might show something
    
    try:
        logger.info(f"🔌 Connecting to MongoDB: {mongodb_url[:20]}...")
        client = AsyncIOMotorClient(mongodb_url)
        # Ping to verify connection
        await client.admin.command('ping')
        db = client[db_name]
        app.state.db = db
        logger.info(f"✅ Connected to database: {db_name}")

        # Initialize Agent
        
        app.state.agent = get_learning_agent(db)
    

    except Exception as e:
        logger.error(f"Critical error during startup: {str(e)}")
        # In production, we might want to continue so /health works, 
        # but the app will likely 500 on other routes.
        app.state.db = None

    # Main DB Setup (for Users)
    main_mongodb_url = os.getenv("MAIN_MONGODB_URL")
    
    # We clean quotes if user copy-pasted with quotes
    main_client = None
    
    if main_mongodb_url:
        main_mongodb_url = main_mongodb_url.strip('"').strip("'")
        try:
            # Mask credentials for logging
            log_url = main_mongodb_url.split('@')[-1] if '@' in main_mongodb_url else main_mongodb_url[:20]
            logger.info(f"🔌 Connecting to Main MongoDB: {log_url}...")
            
            main_client = AsyncIOMotorClient(main_mongodb_url, serverSelectionTimeoutMS=5000)
            # Ping
            await main_client.admin.command('ping')
            
            # Use get_default_database() which gets the DB from the URI path
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

# Add Global Exception Handler for robustness
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

# Include Routers
app.include_router(goals.router, prefix="/goals", tags=["Goals"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(assignedprojects.router, prefix="/assignedprojects", tags=["Assigned Projects"])
app.include_router(preferences.router, prefix="/preferences", tags=["Preferences"])
app.include_router(notices.router, prefix="/notices", tags=["Notice Board"])
app.include_router(quizzes.router, prefix="/quizzes", tags=["Quizzes"])
app.include_router(assessments.router, prefix="/assessments", tags=["Assessments"])
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
    # Important: bind to 0.0.0.0 for external access
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
