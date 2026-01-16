from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langsmith import traceable

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

    Returns a simple object that can be invoked.
    """
    print("✅ Learning agent initialized")

    # Return a simple callable that wraps run_learning_agent
    class SimpleLearningAgent:
        def __init__(self, database):
            self.db = database

        async def ainvoke(self, user_id: str, message: str = None):
            """Invoke the agent for a specific user."""
            return await run_learning_agent(self.db, user_id, message)

    return SimpleLearningAgent(db)


@traceable(name="Learning Agent", tags=["agent", "career-guidance"])
async def run_learning_agent(db, user_id: str, user_message: str = None) -> dict:
    try:
        print(f"\n{'='*60}")
        print(f"🚀 Starting learning agent for user: {user_id}")
        print(f"📝 User message: {user_message}")
        print(f"{'='*60}\n")

        # Validate configuration
        Config.validate()

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

        # Initialize LLM
        print("🤖 Initializing Gemini LLM...")
        llm = ChatGoogleGenerativeAI(
            model=Config.LLM_MODEL,
            temperature=Config.LLM_TEMPERATURE,
        )
        print("✅ LLM initialized\n")

        # Create tools
        tools = create_agent_tools(db)

        # Handle agent name update
        if user_message and user_message.startswith("Updated the name of the agent to"):
            return {
                "message": await handle_agent_name_update(db, user_id, user_message),
                "status": "success",
            }

        # Handle save chat request for new users
        if user_message and user_message.startswith("Save chat for the new user with the phone number:"):
            print("💾 Handling save chat request for new user")
            
            # Extract phone number from message
            phone_number = user_message.replace("Save chat for the new user with the phone number:", "").strip()
            
            # Save the initial chat
            from datetime import datetime
            chat_doc = {
                "userId": phone_number,
                "userType": "user",
                "message": "Initial conversation started",
                "timestamp": datetime.now()
            }
            
            await db.chats.insert_one(chat_doc)
            print(f"✅ Initial chat saved for new user: {phone_number}")
            
            return {
                "message": f"Chat history initialized for new user {phone_number}",
                "status": "success",
                "tasks": []
            }

        # Classify user intent
        is_task_assignment_mode = False
        if user_message:
            intent = await classify_user_intent(llm, user_message, prompt_loader)
            is_task_assignment_mode = intent == "task_assignment"
        else:
            # No message means goals were just updated - default to general conversation
            is_task_assignment_mode = False

        print(f"🎯 Mode: {'TASK ASSIGNMENT' if is_task_assignment_mode else 'GENERAL CONVERSATION'}\n")

        # Load appropriate prompts
        if is_task_assignment_mode:
            system_prompt = prompt_loader.format("task_assignment_system", agent_name=agent_name)
            user_prompt = prompt_loader.format("task_assignment_user", user_id=user_id)
        else:
            system_prompt = prompt_loader.format("general_conversation_system", agent_name=agent_name)
            
            if user_message:
                user_prompt = prompt_loader.format(
                    "general_conversation_user_with_message",
                    user_message=user_message,
                    user_id=user_id
                )
            else:
                user_prompt = prompt_loader.format(
                    "general_conversation_user_no_message",
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
            print(f"📝 Raw response text:\n{final_response}\n")

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