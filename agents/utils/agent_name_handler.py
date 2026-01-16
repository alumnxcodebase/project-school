async def handle_agent_name_update(db, user_id: str, message: str) -> str:
    """
    Handle agent name update messages.
    Extracts the agent name from the message and returns a personalized greeting.

    Expected message format: "Updated the name of the agent to <agent_name>"
    Returns: "Hello! I'm <agent_name>. How can I help you today?"
    """
    try:
        print(f"🔄 Processing agent name update for user: {user_id}")
        print(f"📝 Message: {message}")

        # Extract agent name from the message
        # Format: "Updated the name of the agent to <agent_name>"
        prefix = "Updated the name of the agent to "

        if message.startswith(prefix):
            agent_name = message[len(prefix) :].strip()
            print(f"✅ Extracted agent name: {agent_name}")

            # Create personalized greeting
            greeting = f"Hello! I'm {agent_name}. How can I help you today?"
            print(f"💬 Generated greeting: {greeting}")

            return greeting
        else:
            print("⚠️ Message format didn't match expected pattern")
            return "Hello! How can I help you today?"

    except Exception as e:
        print(f"❌ Error in handle_agent_name_update: {str(e)}")
        import traceback

        traceback.print_exc()
        return "Hello! How can I help you today?"
