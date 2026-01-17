# callback_handler.py

def handle_button_callback(callback: str) -> dict:
    """
    Handle button callbacks and return appropriate response with URL.
    
    Args:
        callback: The callback string from button click (can be "sfs" or "Software Finishing S")
        
    Returns:
        dict with message and status, or None if not a callback
    """
    
    # Normalize the input
    callback_lower = callback.lower().strip()
    
    # Map both callback codes AND button text to URLs
    callback_map = {
        "sfs": {
            "name": "Software Finishing School",
            "url": "https://alumnx.com/courses/software-finishing-school"
        },
        "software finishing school": {
            "name": "Software Finishing School",
            "url": "https://alumnx.com/courses/software-finishing-school"
        },
        "software finishing s": {  # Truncated version
            "name": "Software Finishing School",
            "url": "https://alumnx.com/courses/software-finishing-school"
        },
        "ps": {
            "name": "#1 + 1 on 1 Placement Support",
            "url": "https://alumnx.com/courses/placement-school"
        },
        "#1 + 1 on 1 placement support": {
            "name": "#1 + 1 on 1 Placement Support",
            "url": "https://alumnx.com/courses/placement-school"
        },
        "#1 + 1 on 1 placemen": {  # Truncated version
            "name": "#1 + 1 on 1 Placement Support",
            "url": "https://alumnx.com/courses/placement-school"
        },
        "js": {
            "name": "Job Support",
            "url": "https://alumnx.com/jobs"
        },
        "job support": {
            "name": "Job Support",
            "url": "https://alumnx.com/jobs"
        }
    }
    
    # Check if this is a recognized callback
    if callback_lower in callback_map:
        info = callback_map[callback_lower]
        
        # Format response message - simple with URL
        message = f"Great! The following resources from Alumnx AI Labs should help you.\n\n{info['name']}: {info['url']}"
        
        print(f"✅ Handled callback: {callback} → {info['name']}")
        
        return {
            "message": message,
            "status": "success",
            "callback_handled": True
        }
    
    # Not a callback we recognize
    return None


def is_button_callback(message: str) -> bool:
    """
    Check if a message is a button callback.
    
    Args:
        message: The user's message
        
    Returns:
        bool: True if it's a button callback
    """
    if not message:
        return False
    
    message_lower = message.lower().strip()
    
    # List of valid callbacks (both codes and button text)
    valid_callbacks = [
        "sfs", 
        "software finishing school",
        "software finishing s",
        "ps", 
        "#1 + 1 on 1 placement support",
        "#1 + 1 on 1 placemen",
        "js",
        "job support"
    ]
    
    return message_lower in valid_callbacks