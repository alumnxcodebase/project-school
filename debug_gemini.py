# debug_gemini.py
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=api_key)

# Test gemini-2.5-pro
print("\n🧪 Testing gemini-2.5-flash:")
try:
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content("Say 'Hello' in one word")
    print(f"  ✅ Success: {response.text}")
except Exception as e:
    print(f"  ❌ Error: {e}")

# Test gemini-2.5-flash (faster alternative)
print("\n🧪 Testing gemini-2.5-flash:")
try:
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content("Say 'Hi' in one word")
    print(f"  ✅ Success: {response.text}")
except Exception as e:
    print(f"  ❌ Error: {e}")