import json
import re


def parse_json_from_response(response_text: str) -> list:
    """
    Extract JSON array from response text, handling markdown code blocks and nested text.
    Returns list of task objects with id and title.
    """
    try:
        print(f"\n📊 Parsing response:\n{response_text}\n")

        # Remove markdown code blocks if present
        cleaned = response_text.strip()
        cleaned = re.sub(r"```json\s*", "", cleaned)
        cleaned = re.sub(r"```\s*", "", cleaned)
        cleaned = cleaned.strip()

        # Extract JSON array if it's embedded in text
        # Look for pattern: [ ... ]
        json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            print(f"📌 Found JSON match:\n{json_str}\n")
        else:
            json_str = cleaned
            print(f"⚠️ No JSON match pattern found, trying full response\n")

        # Try to parse JSON
        tasks = json.loads(json_str)

        if isinstance(tasks, list):
            print(f"✅ Successfully parsed {len(tasks)} tasks\n")
            for i, task in enumerate(tasks, 1):
                print(f"   Task {i}: {task.get('title')} (ID: {task.get('id')})")
            return tasks

        print(f"⚠️ Parsed data is not a list: {type(tasks)}\n")
        return []

    except json.JSONDecodeError as e:
        print(f"❌ JSON Parse Error: {str(e)}")
        print(
            f"📝 Attempted to parse:\n{json_str if 'json_str' in locals() else response_text}\n"
        )
        return []
    except Exception as e:
        print(f"❌ Unexpected error during parsing: {str(e)}\n")
        return []


def parse_llm_content(content):
    """Parse LLM response content, handling list and string formats"""
    if isinstance(content, list):
        content_parts = []
        for part in content:
            if isinstance(part, str):
                content_parts.append(part)
            elif hasattr(part, "text"):
                content_parts.append(part.text)
            else:
                content_parts.append(str(part))
        return "".join(content_parts).strip()
    return content
