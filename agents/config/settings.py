import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)


class Config:
    """Application configuration"""
    
    # LLM Configuration
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    LLM_MODEL = os.getenv("LLM_MODEL", "models/gemini-2.0-flash")
    LLM_TEMPERATURE = 0.0
    
    # Agent Configuration
    DEFAULT_AGENT_NAME = "Study Buddy"
    
    # Paths - updated to point to the correct location
    PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        if not cls.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY environment variable not set")