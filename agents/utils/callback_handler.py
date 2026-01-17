# callback_handler.py

def handle_button_callback(callback: str) -> dict:
    """
    Handle button callbacks and return appropriate response with URL.
    
    Args:
        callback: The callback string from button click (sfs, ps, js)
        
    Returns:
        dict with message and status, or None if not a callback
    """
    
    # Map callbacks to their URLs and names
    callback_map = {
        "sfs": {
            "name": "Software Finishing School",
            "url": "https://alumnx.com/courses/software-finishing-school"
        },
        "ps": {
            "name": "#1 + 1 on 1 Placement Support",
            "url": "https://alumnx.com/courses/placement-school"
        },
        "js": {
            "name": "Job Support",
            "url": "https://alumnx.com/jobs"
        }
    }
    
    # Check if this is a recognized callback
    if callback.lower() in callback_map:
        info = callback_map[callback.lower()]
        
        # Format response message
        message = (
            f"Great! The following resources from Alumnx AI Labs should help you.\n\n"
            f"{info['name']}: {info['url']}"
        )
        
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
    
    # List of valid callbacks
    valid_callbacks = ["sfs", "ps", "js"]
    
    return message.strip().lower() in valid_callbacks