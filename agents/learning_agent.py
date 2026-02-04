# learning_agent.py

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langsmith import traceable
from datetime import datetime, timedelta
import json
import re

from .config.settings import Config
from .prompts.loader import PromptLoader
from .utils.intent_classifier import classify_user_intent
from .utils.response_parser import parse_json_from_response, parse_llm_content
from .utils.task_validator import validate_and_enrich_tasks, format_tasks_message
from .utils.tools import create_agent_tools
from .utils.agent_name_handler import handle_agent_name_update
from .utils.callback_handler import handle_button_callback, is_button_callback
from .utils.study_buddy_helper import get_user_learning_state, update_buddy_status


def get_learning_agent(db):
    """
    Initialize and return the learning agent.
    This function exists for compatibility with your existing code.
    """
    print("✅ Learning agent initialized")

    class SimpleLearningAgent:
        def __init__(self, database):
            self.db = database

        async def ainvoke(self, user_id: str, message: str = None, resume_data: dict = None):
            """Invoke the agent for a specific user."""
            return await run_learning_agent(self.db, user_id, message, resume_data)

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

IMPORTANT: Greetings like "hi", "hello", "hey", "sup", "yo" are NOT names. General questions are NOT names.

If the user is asking a question, greeting you, or having a general conversation (not providing a name), respond with:
{{"is_name": false, "name": ""}}

Respond ONLY with the JSON object, nothing else."""

        result = await llm.ainvoke([HumanMessage(content=prompt)])
        response = parse_llm_content(result.content).strip()
        
        # Parse JSON response
        
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


async def save_resume_data_directly(db, user_id: str, resume_data: dict) -> bool:
    """
    Directly save resume data to the userdata collection.
    Called when user uploads a resume.
    
    Args:
        db: Database connection
        user_id: User's ID
        resume_data: Parsed resume data from resume parser API
        
    Returns:
        bool: True if saved successfully, False otherwise
    """
    try:
        print(f"\n{'='*60}")
        print(f"📄 SAVING RESUME DATA")
        print(f"{'='*60}")
        print(f"User ID: {user_id}")
        print(f"Resume data keys: {list(resume_data.keys())}")
        
        # Create userdata document
        userdata_doc = {
            "userId": user_id,
            "resumeData": resume_data,
            "uploadedAt": datetime.now(),
            "lastUpdated": datetime.now()
        }
        
        # Upsert: update if exists, insert if doesn't
        result = await db.userdata.update_one(
            {"userId": user_id},
            {
                "$set": {
                    "resumeData": resume_data,
                    "lastUpdated": datetime.now()
                },
                "$setOnInsert": {
                    "uploadedAt": datetime.now()
                }
            },
            upsert=True
        )
        
        if result.upserted_id:
            print(f"✅ New resume data inserted with ID: {result.upserted_id}")
        elif result.modified_count > 0:
            print(f"✅ Existing resume data updated")
        else:
            print(f"⚠️ No changes made to resume data (data unchanged)")
        
        print(f"{'='*60}\n")
        return True
        
    except Exception as e:
        print(f"❌ Error saving resume data: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def extract_and_save_user_info(db, llm, user_id: str, user_text: str) -> bool:
    """
    Extract structured information from user's text and save to userdata.
    
    Args:
        db: Database connection
        llm: LLM instance
        user_id: User's ID
        user_text: User's description about themselves
        
    Returns:
        bool: True if extracted and saved successfully
    """
    try:
        print(f"\n{'='*60}")
        print(f"📝 EXTRACTING USER INFO FROM TEXT")
        print(f"{'='*60}")
        print(f"User ID: {user_id}")
        print(f"Text length: {len(user_text)} chars")
        
        # Use LLM to extract structured data
        extraction_prompt = f"""Extract structured information from the following user description.

User's message: "{user_text}"

Extract and return ONLY a JSON object with these fields (use "Not provided" if information is missing):
- about: Brief summary of the person
- interests: What excites them or what they're interested in
- careerGoals: Their career aspirations and goals
- currentRole: Their current job/role if mentioned
- skills: Any skills they mentioned
- experience: Years of experience or background mentioned

Return ONLY the JSON object, nothing else."""

        result = await llm.ainvoke([HumanMessage(content=extraction_prompt)])
        response = parse_llm_content(result.content).strip()
        
        print(f"LLM response:\n{response}\n")
        
        # Extract JSON from response
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            extracted_data = json.loads(json_match.group(0))
            print(f"✅ Extracted data: {list(extracted_data.keys())}")
            
            # Save to userdata collection
            userdata_doc = {
                "userId": user_id,
                "resumeData": extracted_data,
                "uploadedAt": datetime.now(),
                "lastUpdated": datetime.now(),
                "dataSource": "text_input"
            }
            
            result = await db.userdata.update_one(
                {"userId": user_id},
                {
                    "$set": {
                        "resumeData": extracted_data,
                        "lastUpdated": datetime.now(),
                        "dataSource": "text_input"
                    },
                    "$setOnInsert": {
                        "uploadedAt": datetime.now()
                    }
                },
                upsert=True
            )
            
            print(f"✅ User info saved to userdata collection")
            print(f"{'='*60}\n")
            return True
        else:
            print(f"⚠️ Could not extract JSON from LLM response")
            return False
            
    except Exception as e:
        print(f"❌ Error extracting user info: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def extract_response_type_and_buttons(response_text: str) -> tuple:
    """
    Extract response type tag from agent's response and determine buttons.
    
    Args:
        response_text: The agent's response text
        
    Returns:
        tuple: (cleaned_response, buttons_list)
    """
    # Look for [RESPONSE_TYPE: ...] tag
    pattern = r'\[RESPONSE_TYPE:\s*(\w+)\]'
    match = re.search(pattern, response_text, re.IGNORECASE)
    
    buttons = []
    cleaned_response = response_text
    
    if match:
        response_type = match.group(1).lower()
        # Remove the tag from the response
        cleaned_response = re.sub(pattern, '', response_text, flags=re.IGNORECASE).strip()
        
        print(f"📌 Detected response type: {response_type}")
        
        if response_type == "show_program_buttons":
            # User is aligned - show program buttons
            buttons = [
                {"name": "Software Finishing School", "callback": "sfs"},
                {"name": "#1 + 1 on 1 Placement Support", "callback": "ps"},
                {"name": "Job Support", "callback": "js"}
            ]
            print(f"✅ Adding {len(buttons)} program buttons")
        elif response_type == "not_aligned":
            # User is not aligned - no buttons
            print(f"⚠️ User not aligned with Alumnx focus - no buttons")
        else:
            print(f"⚠️ Unknown response type: {response_type}")
    else:
        print(f"ℹ️ No response type tag found in agent response")
    
    # Global cleanup for any other tags (SCENARIO, NEXT_CONTACT, DAYS, RESPONSE_TYPE, etc.)
    cleaned_response = re.sub(r'\[(?:SCENARIO|NEXT_CONTACT|DAYS|RESPONSE_TYPE):.*?\]', '', cleaned_response).strip()
    
    return cleaned_response, buttons


@traceable(name="Learning Agent", tags=["agent", "career-guidance"])
async def run_learning_agent(
    db, 
    user_id: str, 
    user_message: str = None, 
    resume_data: dict = None
) -> dict:
    """
    Run the learning agent for a user.
    
    Args:
        db: Database connection
        user_id: User's ID (phone number)
        user_message: Optional message from user
        resume_data: Optional resume data from resume parser
        
    Returns:
        dict: Response with message, status, tasks, buttons, etc.
    """
    try:
        print(f"\n{'='*60}")
        print(f"🚀 Starting learning agent for user: {user_id}")
        print(f"📝 User message: {user_message}")
        print(f"📄 Resume data: {'Yes' if resume_data else 'No'}")
        print(f"{'='*60}\n")

        # Validate configuration
        Config.validate()

        # Initialize LLM early for name detection
        llm = ChatGoogleGenerativeAI(
            model=Config.LLM_MODEL,
            temperature=Config.LLM_TEMPERATURE,
        )

        # ============================================================
        # STEP 0: Handle Resume Data if Present
        # ============================================================
        if resume_data:
            print(f"\n📄 RESUME DATA DETECTED - Saving to database")
            save_success = await save_resume_data_directly(db, user_id, resume_data)
            
            if save_success:
                print(f"✅ Resume data saved successfully")
                # Update the message to inform the agent
                if not user_message or user_message == "User uploaded the resume.":
                    user_message = "User uploaded the resume."
            else:
                print(f"⚠️ Failed to save resume data")
                if not user_message or user_message == "User uploaded the resume.":
                    user_message = "User tried to upload resume but there was an error saving it."

        # ============================================================
        # STEP 1: Check if userId exists in chat collection
        # ============================================================
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
        
        # ============================================================
        # STEP 1.2: Check for Proactive Study Buddy Nudge
        # ============================================================
        learning_state = await get_user_learning_state(db, user_id)
        
        # Get agent name for personalized responses
        agent_doc = await db.agents.find_one({"userId": user_id})
        agent_name = agent_doc.get("agentName", Config.DEFAULT_AGENT_NAME) if agent_doc else Config.DEFAULT_AGENT_NAME
        
        # 🚨 FIX: If the stored agent name is "Frontend" (accidental assignment), fallback to "Study Buddy"
        if agent_name == "Frontend":
            agent_name = Config.DEFAULT_AGENT_NAME

        if not user_message:
            # Check if user is in "postponed" status and if time has passed
            current_time = datetime.now()
            next_contact = learning_state.get("next_contact_date")
            buddy_status = learning_state.get("buddy_status", "active")

            if buddy_status == "postponed" and next_contact and next_contact > current_time:
                print(f"🤫 Skipping proactive nudge: User is postponed until {next_contact}")
                return {"message": "", "status": "skip", "skip_save": True} # Return skip status

            # Case 1: Preferences set but no active tasks
            if not learning_state["has_active_tasks"] and learning_state["has_preferences"]:
                print("💡 Proactive Nudge: User has preferences but 0 active tasks")
                prefs_list = ", ".join(learning_state["preferences"])
                nudge_message = f"Hello! I am {agent_name}. Here are your preferences: {prefs_list}. Looks like there are no active task in your active task tab. What would you like to focus on today?"
                
                # Let the router handle saving this message
                return {"message": nudge_message, "status": "success", "skip_save": False}
            
            # Case 2: Active tasks already exist
            elif learning_state["has_active_tasks"]:
                print("💡 Proactive Reminder: User has active tasks")
                nudge_message = f"Hello! I am {agent_name}. I see there are active tasks in your bucket, please complete it to move forward with your learning journey!"
                
                # Let the router handle saving this message
                return {"message": nudge_message, "status": "success", "skip_save": False}
            
            # Case 3: No preferences and no tasks
            else:
                nudge_message = f"Hello! I am {agent_name}. I see your learning dashboard is empty. Would you like to tell me about your career goals so I can suggest some skills to focus on?"
                return {"message": nudge_message, "status": "success", "skip_save": False}
        
        # ============================================================
        # STEP 1.5: Handle Button Callbacks FIRST (sfs, ps, js)
        # ============================================================
        if user_message and is_button_callback(user_message):
            print(f"🔘 Button callback detected: {user_message}")
            callback_response = handle_button_callback(user_message)
            
            if callback_response:
                # Save user's callback message
                user_chat_doc = {
                    "userId": user_id,
                    "userType": "user",
                    "message": user_message,
                    "timestamp": datetime.now()
                }
                await db.chats.insert_one(user_chat_doc)
                
                # Save callback response to chat
                agent_chat_doc = {
                    "userId": user_id,
                    "userType": "agent",
                    "message": callback_response["message"],
                    "timestamp": datetime.now()
                }
                await db.chats.insert_one(agent_chat_doc)
                print(f"✅ Callback response saved to chat")
                
                # Return callback response with skip_save flag
                return {
                    **callback_response,
                    "skip_save": True  # Already saved above
                }
        
        # ============================================================
        # STEP 2: Save user's incoming message
        # ============================================================
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
        
        # ============================================================
        # STEP 3: User exists - get last 20 chat messages
        # ============================================================
        print("📚 Existing user - fetching chat history")
        chat_history_cursor = db.chats.find(
            {"userId": user_id}
        ).sort("timestamp", -1).limit(20)
        
        chat_history = await chat_history_cursor.to_list(length=20)
        chat_history.reverse()  # Reverse to get chronological order
        
        print(f"📜 Retrieved {len(chat_history)} chat messages")
        
        # ============================================================
        # STEP 4: Check if user is providing a name
        # ============================================================
        name_check = {'is_name': False, 'extracted_name': ''}
        
        # Only check for name if user actually sent a message
        if user_message and len(user_message.strip()) > 1:
            name_check = await check_if_name_response(llm, user_message, chat_history)
        
        if name_check['is_name'] and name_check['extracted_name']:
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
            
            # Create greeting asking for user info or resume
            greeting = f"{agent_name} at your service!\n\nPlease tell me something about yourself, what excites you, your career goals or just attach your Resume here and Submit, so that I can get to know you better."
            
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
                "buttons": [],  # No buttons at this stage
                "status": "success",
                "skip_save": True
            }
        
        # ============================================================
        # STEP 5: Normal conversation flow - not a name
        # ============================================================
        print("💬 Regular conversation - proceeding with normal flow")
        
        # ============================================================
        # STEP 5.5: Check if user is providing info about themselves
        # ============================================================
        # Check if user has already provided their info/resume
        existing_userdata = await db.userdata.find_one({"userId": user_id})
        
        if not existing_userdata and user_message and not resume_data:
            # User hasn't provided info yet, and they're sending text (not resume)
            # Extract and save their information
            print(f"📝 User providing information about themselves")
            
            extraction_success = await extract_and_save_user_info(
                db, llm, user_id, user_message
            )
            
            if extraction_success:
                print(f"✅ User info extracted and saved")
                # Set a flag so we know to proceed with goal alignment
                user_message = f"User provided information about themselves: {user_message}"
            else:
                print(f"⚠️ Could not extract user info, proceeding normally")
        
        # Initialize prompt loader
        prompt_loader = PromptLoader(Config.PROMPTS_DIR)

        # agent_name is already defined above in STEP 1.2
        print(f"🤖 Agent name: {agent_name}")

        # Create tools
        tools = create_agent_tools(db)

        # Classify user intent
        is_task_assignment_mode = False
        intent = "general_conversation" # Default intent
        
        if user_message:
            intent = await classify_user_intent(llm, user_message, prompt_loader)
            is_task_assignment_mode = intent == "task_assignment"
        else:
            # Fallback for null message when no proactive nudge was triggered
            print("ℹ️ Message is null and no nudge triggered. Using default greeting.")
            fallback_message = f"Hello! I am {agent_name}, your learning coach. I see there are no active tasks or specific suggestions right now. Would you like to discuss your career goals or set new preferences?"
            return {
                "message": fallback_message,
                "status": "success",
                "skip_save": False
            }

        print(f"🎯 Mode: {'TASK ASSIGNMENT' if is_task_assignment_mode else 'GENERAL CONVERSATION'}\n")

        # Load appropriate prompts
        if is_task_assignment_mode:
            system_prompt = prompt_loader.format("task_assignment_system", agent_name=agent_name)
            user_prompt = prompt_loader.format("task_assignment_user", user_id=user_id)
        elif intent == "buddy_response":
            # Fetch context for buddy response
            learning_state = await get_user_learning_state(db, user_id)
            
            # Format last 5 messages for context
            context_messages = chat_history[-6:-1] if len(chat_history) > 1 else []
            history_transcript = "\n".join([
                f"{'User' if m.get('userType') == 'user' else 'Agent'}: {m.get('message')}" 
                for m in context_messages
            ])
            
            system_prompt = prompt_loader.format(
                "buddy_response_system", 
                agent_name=agent_name,
                preferences=", ".join(learning_state["preferences"]),
                active_tasks_count=len(learning_state["active_tasks"]),
                completed_tasks_count=len(learning_state["completed_tasks"]),
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                next_contact_date=learning_state.get("next_contact_date").strftime("%Y-%m-%d %H:%M:%S") if learning_state.get("next_contact_date") else "None"
            )
            
            user_prompt = f"User ID: {user_id}\n\nRecent Conversation Context:\n{history_transcript}\n\nUser is responding: {user_message}"
        else:
            system_prompt = prompt_loader.format("general_conversation_system", agent_name=agent_name)
            
            # Add user info context if available (from resume upload OR text input)
            user_info_context = ""
            
            if resume_data:
                # Resume was just uploaded
                user_info_context = f"\n\nNote: The user just uploaded their resume with the following information:\n{json.dumps(resume_data, indent=2)}\n\nPlease acknowledge the upload and provide relevant career guidance based on the information. Then evaluate if their background and goals align with Alumnx's focus (React, Data Science, AI/ML, Software Engineering)."
            elif existing_userdata and existing_userdata.get("resumeData"):
                # User previously provided info (text or resume)
                stored_data = existing_userdata.get("resumeData")
                data_source = existing_userdata.get("dataSource", "resume")
                
                if data_source == "text_input":
                    user_info_context = f"\n\nNote: The user previously provided information about themselves:\n{json.dumps(stored_data, indent=2)}\n\nUse this information to provide personalized career guidance and evaluate if their goals align with Alumnx's focus (React, Data Science, AI/ML, Software Engineering)."
                else:
                    user_info_context = f"\n\nNote: The user's background information:\n{json.dumps(stored_data, indent=2)}\n\nUse this information to provide personalized career guidance and evaluate if their goals align with Alumnx's focus (React, Data Science, AI/ML, Software Engineering)."
            
            user_prompt = prompt_loader.format(
                "general_conversation_user_with_message",
                user_message=user_message,
                user_id=user_id
            ) + user_info_context

        print("🤖 Creating LangGraph ReAct agent...\n")

        # Create the ReAct agent
        agent = create_react_agent(llm, tools)

        print("✅ Agent created\n")
        print("🔄 Running agent...\n")

        # Run the agent
        # We wrap the prompts in a way that encourages tool use
        print(f"--- SYSTEM PROMPT ---\n{system_prompt}\n")
        print(f"--- USER PROMPT ---\n{user_prompt}\n")
        
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
                "show_task_list": True, # Explicitly show the selection UI
                "messages": result["messages"],
            }
            
            return response_obj
        else:
            # ENHANCED TASK REFRESH TRIGGER
            # Check if any tool was called during this turn that might have changed tasks
            tool_called = False
            for m in result["messages"]:
                if hasattr(m, 'tool_calls') and m.tool_calls:
                    for tc in m.tool_calls:
                        if tc.get('name') in ['assign_task_to_user_tool', 'get_first_task_by_skill']:
                            tool_called = True
                            break
                if tool_called: break

            if intent == "buddy_response":
                print("🔄 Post-processing Buddy Response for state updates")
                buttons = []
                tasks = [] # Initialize tasks list
                
                if "[SCENARIO: BUSY]" in final_response:
                    await update_buddy_status(db, user_id, "busy")
                elif "[SCENARIO: POSTPONE]" in final_response:
                    # Try to extract time or days from LLM response
                    time_match = re.search(r'\[NEXT_CONTACT: (.*?)\]', final_response)
                    if time_match:
                        try:
                            from dateutil import parser
                            next_contact = parser.parse(time_match.group(1))
                            print(f"🕒 Extracted specific next contact: {next_contact}")
                        except:
                            next_contact = datetime.now() + timedelta(days=3)
                    else:
                        days_match = re.search(r'\[DAYS: (\d+)\]', final_response)
                        days = int(days_match.group(1)) if days_match else 3
                        next_contact = datetime.now() + timedelta(days=days)
                    
                    await update_buddy_status(db, user_id, "postponed", next_contact)
                elif "ASSIGN_CONFIRM" in final_response or "NEXT_TASK" in final_response or tool_called:
                    await update_buddy_status(db, user_id, "active")
                    # FETCH LATEST TASKS FOR AUTO-REFRESH
                    latest_state = await get_user_learning_state(db, user_id)
                    tasks = latest_state["active_tasks"]
                    print(f"📊 Task change detected: returning {len(tasks)} active tasks for UI refresh")
                
                # Strip all metadata tags from final response (Scenario, Next Contact, Days, Response Type)
                cleaned_response = re.sub(r'\[(?:SCENARIO|NEXT_CONTACT|DAYS|RESPONSE_TYPE):.*?\]', '', final_response).strip()
                
                return {
                    "message": cleaned_response,
                    "buttons": buttons,
                    "tasks": tasks,
                    "show_task_list": False, # DO NOT show selection UI for auto-assignments
                    "status": "success",
                    "messages": result["messages"],
                }
            else:
                cleaned_response, buttons = extract_response_type_and_buttons(final_response)
                
                tasks = []
                if tool_called:
                    latest_state = await get_user_learning_state(db, user_id)
                    tasks = latest_state["active_tasks"]
                    print(f"📊 Tool-based task change detected in {intent} mode: returning {len(tasks)} tasks")

                return {
                    "message": cleaned_response,
                    "buttons": buttons,
                    "tasks": tasks,
                    "show_task_list": False,
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