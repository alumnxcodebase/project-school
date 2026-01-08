import os
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

# In-memory cache for relevance results
_relevance_cache = {}

def serialize(doc):
    """Converts MongoDB _id to string 'id'."""
    if not doc: return None
    doc["id"] = str(doc.pop("_id"))
    return doc

async def is_task_relevant_to_project(project_description: str, task_title: str, project_id: str, task_id: str) -> bool:
    """
    Check if a task title is relevant to a project description using LLM.
    Results are cached to avoid redundant API calls.
    
    Args:
        project_description: The project description
        task_title: The task title to check
        project_id: Project ID for cache key
        task_id: Task ID for cache key
        
    Returns:
        True if task is relevant, False otherwise
    """
    # Create cache key
    cache_key = f"{project_id}:{task_id}"
    
    # Check cache first
    if cache_key in _relevance_cache:
        print(f"✅ Cache hit for {cache_key}")
        return _relevance_cache[cache_key]
    
    # If no description, consider it relevant (or you can return False)
    if not project_description or not project_description.strip():
        _relevance_cache[cache_key] = True
        return True
    
    try:
        # Initialize LLM
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("⚠️ GOOGLE_API_KEY not found, defaulting to True")
            _relevance_cache[cache_key] = True
            return True
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.3,  # Lower temperature for more consistent yes/no answers
            google_api_key=api_key
        )
        
        # Create prompt
        prompt = f"""Is the task title "{task_title}" relevant to this project description: "{project_description}"?

Answer only "yes" or "no"."""
        
        # Call LLM
        print(f"🔍 LLM Call - Project: '{project_description[:50]}...' | Task: '{task_title}'")
        response = await llm.ainvoke(prompt)
        result_text = response.content.strip()
        result_text_lower = result_text.lower()
        
        # Log the raw LLM response
        print(f"📝 Raw LLM Response: '{result_text}'")
        
        # Parse response
        is_relevant = result_text_lower.startswith("yes")
        
        # Cache the result
        _relevance_cache[cache_key] = is_relevant
        
        print(f"🤖 LLM check: Task '{task_title}' -> {'✅ Relevant' if is_relevant else '❌ Not Relevant'} (parsed from: '{result_text}')")
        
        return is_relevant
        
    except Exception as e:
        print(f"❌ LLM error for task relevance check: {str(e)}")
        # On error, default to True to avoid filtering out tasks
        _relevance_cache[cache_key] = True
        return True