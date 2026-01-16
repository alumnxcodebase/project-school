# learning_agent.py

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langsmith import traceable
from datetime import datetime

from .config.settings import Config
from .prompts.loader import PromptLoader
from .utils.intent_classifier import classify_user_intent
from .utils.response_parser import parse_json_from_response, parse_llm_content
from .utils.task_validator import validate_and_enrich_tasks, format_tasks_message
from .utils.tools import create_agent_tools
from .utils.agent_name_handler import handle_agent_name_update


def get_learning_agent(db):
    """
    Initialize and return the learning agent.
    This function exists for compatibility with your existing code.
    """
    print("✅ Learning agent initialized")

    class SimpleLearningAgent:
        def __init__(self, database):
            self.db = database

        async def ainvoke(self, user_id: str, message: str = None):
            """Invoke the agent for a specific user."""
            return await run_learning_agent(self.db, user_id, message)

    return SimpleLearningAgent(db)


async def check_if_name_response(llm, user_message: str, chat_history: list) -> dict:
    """
    Check if the user's message is a name in response to the initial greeting.
    Returns dict with 'is_name' (bool) and 'extracted_name' (str)
    """
    try:
        # Get last few messages to understand context
        recent_context = "\n".join([
            f"{chat['userType']}: {chat['message']}" 
            for chat in chat_history[-5:] if chat
        ])
        
        prompt = f"""Analyze if the user's message is providing a name in response to being asked to give the AI assistant a new name.

Recent conversation:
{recent_context}

User's latest message: "{user_message}"

If the user is providing a name (could be a single word, multiple words, or a creative name), respond with:
{{"is_name": true, "name": "<extracted_name>"}}

If the user is asking a question or having a general conversation (not providing a name), respond with:
{{"is_name": false, "name": ""}}

Respond ONLY with the JSON object, nothing else."""

        result = await llm.ainvoke([HumanMessage(content=prompt)])
        response = parse_llm_content(result.content).strip()
        
        # Parse JSON response
        import json
        import re
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            return {
                'is_name': parsed.get('is_name', False),
                'extracted_name': parsed.get('name', '').strip()
            }
        
        return {'is_name': False, 'extracted_name': ''}
        
    except Exception as e:
        print(f"⚠️ Error checking if name response: {str(e)}")
        return {'is_name': False, 'extracted_name': ''}


@traceable(name="Learning Agent", tags=["agent", "career-guidance"])
async def run_learning_agent(db, user_id: str, user_message: str = None) -> dict:
    try:
        print(f"\n{'='*60}")
        print(f"🚀 Starting learning agent for user: {user_id}")
        print(f"📝 User message: {user_message}")
        print(f"{'='*60}\n")

        # Validate configuration
        Config.validate()

        # Initialize LLM early for name detection
        llm = ChatGoogleGenerativeAI(
            model=Config.LLM_MODEL,
            temperature=Config.LLM_TEMPERATURE,
        )

        # STEP 1: Check if userId exists in chat collection
        existing_chat = await db.chats.find_one({"userId": user_id})
        
        if not existing_chat:
            print("🆕 New user - no chat history found")
            
            # Insert initial welcome message
            welcome_message = "Hello! I am Study Buddy, your AI assistant from Alumnx AI Labs. Looks like we meet for the first time. Please give me a new name to get going."
            
            chat_doc = {
                "userId": user_id,
                "userType": "agent",
                "message": welcome_message,
                "timestamp": datetime.now()
            }
            
            await db.chats.insert_one(chat_doc)
            print(f"✅ Welcome message saved to chat collection")
            
            return {
                "message": welcome_message,
                "status": "success",
                "skip_save": True
            }
        
        # STEP 2: Save user's incoming message FIRST
        if user_message:
            print(f"💾 Saving user message to chat history")
            user_chat_doc = {
                "userId": user_id,
                "userType": "user",
                "message": user_message,
                "timestamp": datetime.now()
            }
            await db.chats.insert_one(user_chat_doc)
            print(f"✅ User message saved")
        
        # STEP 3: User exists - get last 20 chat messages
        print("📚 Existing user - fetching chat history")
        chat_history_cursor = db.chats.find(
            {"userId": user_id}
        ).sort("timestamp", -1).limit(20)
        
        chat_history = await chat_history_cursor.to_list(length=20)
        chat_history.reverse()  # Reverse to get chronological order
        
        print(f"📜 Retrieved {len(chat_history)} chat messages")
        
        # STEP 4: Check if user is providing a name
        name_check = await check_if_name_response(llm, user_message, chat_history)
        
        if name_check['is_name']:
            agent_name = name_check['extracted_name']
            print(f"🎯 Detected name response: {agent_name}")
            
            # Save agent name to agents collection
            await db.agents.update_one(
                {"userId": user_id},
                {
                    "$set": {
                        "agentName": agent_name,
                        "updated_at": datetime.now()
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now()
                    }
                },
                upsert=True
            )
            print(f"✅ Saved agent name: {agent_name}")
            
            # Create greeting response
            greeting = f"Hola! {agent_name} at your service.\n\nI can help you with\n> Upskilling\n> Getting a job\n> Achieving your Goals"
            
            # Define buttons in WhatsApp format
            buttons = [
                {"name": "Upskilling", "callback": "upskilling"},
                {"name": "Getting a job", "callback": "getting_job"},
                {"name": "Achieving your Goals", "callback": "achieving_goals"}
            ]
            
            # Save greeting to chat
            chat_doc = {
                "userId": user_id,
                "userType": "agent",
                "message": greeting,
                "timestamp": datetime.now()
            }
            await db.chats.insert_one(chat_doc)
            print(f"✅ Greeting saved to chat collection")
            
            return {
                "message": greeting,
                "buttons": buttons,
                "status": "success",
                "skip_save": True
            }
        
        # STEP 5: Normal conversation flow - not a name
        print("💬 Regular conversation - proceeding with normal flow")
        
        # Initialize prompt loader
        prompt_loader = PromptLoader(Config.PROMPTS_DIR)

        # Get agent name for personalized responses
        agent_doc = await db.agents.find_one({"userId": user_id})
        agent_name = (
            agent_doc.get("agentName", Config.DEFAULT_AGENT_NAME) 
            if agent_doc 
            else Config.DEFAULT_AGENT_NAME
        )
        print(f"🤖 Agent name: {agent_name}")

        # Create tools
        tools = create_agent_tools(db)

        # Classify user intent
        is_task_assignment_mode = False
        if user_message:
            intent = await classify_user_intent(llm, user_message, prompt_loader)
            is_task_assignment_mode = intent == "task_assignment"

        print(f"🎯 Mode: {'TASK ASSIGNMENT' if is_task_assignment_mode else 'GENERAL CONVERSATION'}\n")

        # Load appropriate prompts
        if is_task_assignment_mode:
            system_prompt = prompt_loader.format("task_assignment_system", agent_name=agent_name)
            user_prompt = prompt_loader.format("task_assignment_user", user_id=user_id)
        else:
            system_prompt = prompt_loader.format("general_conversation_system", agent_name=agent_name)
            user_prompt = prompt_loader.format(
                "general_conversation_user_with_message",
                user_message=user_message,
                user_id=user_id
            )

        print("🤖 Creating LangGraph ReAct agent...\n")

        # Create the ReAct agent
        agent = create_react_agent(llm, tools)

        print("✅ Agent created\n")
        print("📄 Running agent...\n")

        # Run the agent
        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            }
        )

        print("✅ Agent execution completed\n")

        # Extract final response
        final_message = result["messages"][-1]
        final_response = (
            final_message.content
            if hasattr(final_message, "content")
            else str(final_message)
        )

        # Handle list content from Gemini
        final_response = parse_llm_content(final_response)

        print(f"{'='*60}")
        print(f"✅ Agent completed successfully")
        print(f"{'='*60}\n")
        print(f"Response:\n{final_response}\n")

        # If task assignment mode, parse JSON and return structured tasks
        if is_task_assignment_mode:
            print(f"\n🔍 TASK ASSIGNMENT MODE - Parsing response")
            print(f"📄 Raw response text:\n{final_response}\n")

            parsed_tasks = parse_json_from_response(final_response)
            print(f"✅ Parsed {len(parsed_tasks)} tasks from agent response\n")

            # Validate and enrich tasks
            enriched_tasks, validation_summary = await validate_and_enrich_tasks(
                db, user_id, parsed_tasks
            )
            
            # Format message
            message_text = format_tasks_message(enriched_tasks)
            
            response_obj = {
                "message": message_text,
                "status": "success",
                "tasks": enriched_tasks,
                "messages": result["messages"],
            }
            
            return response_obj
        else:
            return {
                "message": final_response,
                "status": "success",
                "messages": result["messages"],
            }

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "message": f"An error occurred: {str(e)}",
            "status": "error"
        }