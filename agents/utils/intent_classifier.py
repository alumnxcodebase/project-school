from langchain_core.messages import HumanMessage
from .response_parser import parse_llm_content


async def classify_user_intent(llm, user_message: str, prompt_loader) -> str:
    """
    Classify user intent using LLM.
    
    Returns:
        - "task_assignment": User wants task recommendations based on goals
        - "general_conversation": General career/learning questions
    """
    try:
        print(f"\n🎯 Classifying intent for message: {user_message}")
        
        intent_prompt = prompt_loader.format("intent_classification", user_message=user_message)

        result = await llm.ainvoke([HumanMessage(content=intent_prompt)])
        intent = parse_llm_content(result.content).lower()
        
        # Validate intent
        if "task_assignment" in intent:
            intent = "task_assignment"
        elif "buddy_response" in intent:
            intent = "buddy_response"
        elif "general_conversation" in intent:
            intent = "general_conversation"
        else:
            # Default to general conversation if unclear
            intent = "general_conversation"
        
        print(f"✅ Classified intent: {intent}\n")
        return intent
        
    except Exception as e:
        print(f"❌ Error in intent classification: {str(e)}")
        import traceback
        traceback.print_exc()
        # Default to general conversation on error
        return "general_conversation"