import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
from dotenv import load_dotenv


from routers import projects, chat, goals, tasks, resources
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
  
   # Create unique index on agents collection to prevent duplicate userId entries
   print("🔧 Creating unique index on agents.userId...")
   try:
       await db.agents.create_index([("userId", 1)], unique=True)
       print("✅ Unique index on agents.userId created successfully")
   except Exception as e:
       # Index might already exist, that's okay
       print(f"ℹ️  Agents index: {str(e)}")
  
   # Create indexes for resources collection
   print("🔧 Creating indexes on resources collection...")
   try:
       await db.resources.create_index([("taskId", 1)])
       await db.resources.create_index([("projectId", 1)])
       await db.resources.create_index([("userId", 1)])
       print("✅ Resources indexes created successfully")
   except Exception as e:
       print(f"ℹ️  Resources indexes: {str(e)}")


   # Create indexes for resources collection
   print("🔧 Creating indexes on resources collection...")
   try:
       await db.resources.create_index([("name", 1)])
       print("✅ Resources indexes created successfully")
   except Exception as e:
       print(f"ℹ️  Resources indexes: {str(e)}")


   print("🚀 API and Agent Ready")
