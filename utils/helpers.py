import os
import httpx
import logging
from datetime import datetime

logger = logging.getLogger("alumnx")

def serialize(doc):
    """Converts MongoDB _id to string 'id'."""
    if not doc: return None
    doc["id"] = str(doc.pop("_id"))
    return doc

async def send_task_completion_email(assigner_email, assigner_name, assignee_name, task_title):
    """Sends a completion notification email to the assigner via ZeptoMail."""
    zepto_token = os.getenv("ZEPTO_MAIL_TOKEN")
    if not zepto_token:
        logger.error("ZEPTO_MAIL_TOKEN not configured")
        return False

    current_date = datetime.now().strftime("%d %b %Y")
    zepto_payload = {
        "from": {"address": "support@alumnx.com", "name": "Alumnx AI Labs"},
        "to": [{"email_address": {"address": assigner_email, "name": assigner_name}}],
        "template_key": "2518b.6d1e43aa616e32a8.k1.f80371c0-025f-11f1-9250-ae9c7e0b6a9f.19c2c97aadc",
        "merge_info": {
            "date": current_date,
            "name": assigner_name,
            "agent_message": f"{assignee_name} has completed the task '{task_title}' assigned by you."
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.zeptomail.in/v1.1/email/template",
                json=zepto_payload,
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                    "authorization": zepto_token
                },
                timeout=10.0
            )
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"✅ Completion email sent to assigner {assigner_email}")
                return True
            else:
                logger.error(f"❌ ZeptoMail error: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"⚠️ Completion email failed for {assigner_email}: {e}")
        return False

async def send_assignment_email(assignee_email, assignee_name, assigner_name, task_title):
    """Sends an assignment notification email to the student/assignee via ZeptoMail."""
    zepto_token = os.getenv("ZEPTO_MAIL_TOKEN")
    if not zepto_token:
        logger.error("ZEPTO_MAIL_TOKEN not configured")
        return False

    current_date = datetime.now().strftime("%d %b %Y")
    zepto_payload = {
        "from": {"address": "support@alumnx.com", "name": "Alumnx AI Labs"},
        "to": [{"email_address": {"address": assignee_email, "name": assignee_name}}],
        "template_key": "2518b.6d1e43aa616e32a8.k1.f80371c0-025f-11f1-9250-ae9c7e0b6a9f.19c2c97aadc",
        "merge_info": {
            "date": current_date,
            "name": assignee_name,
            "agent_message": f"{assigner_name} has assigned you a task: '{task_title}'. Please login to complete it."
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.zeptomail.in/v1.1/email/template",
                json=zepto_payload,
                headers={"accept": "application/json", "content-type": "application/json", "authorization": zepto_token},
                timeout=10.0
            )
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"✅ Assignment email sent to student {assignee_email}")
                return True
            else:
                logger.error(f"❌ ZeptoMail error: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"⚠️ Assignment email failed for {assignee_email}: {e}")
        return False

async def notify_task_deletion(targets, task_title, deleter_name, deleter_email):
    """
    Notifies both assigners and assignees that a task has been deleted.
    'targets' is a list of dicts: [{'assignee_email', 'assignee_name', 'assigner_email', 'assigner_name'}]
    """
    zepto_token = os.getenv("ZEPTO_MAIL_TOKEN")
    if not zepto_token:
        logger.error("ZEPTO_MAIL_TOKEN not configured")
        return False

    current_date = datetime.now().strftime("%d %b %Y")
    success = True

    try:
        async with httpx.AsyncClient() as client:
            for target in targets:
                # 1. Notify Assignee
                assignee_email = target.get("assignee_email")
                if assignee_email:
                    assignee_payload = {
                        "from": {"address": "support@alumnx.com", "name": "Alumnx AI Labs"},
                        "to": [{"email_address": {"address": assignee_email, "name": target.get("assignee_name", "Student")}}],
                        "template_key": "2518b.6d1e43aa616e32a8.k1.f80371c0-025f-11f1-9250-ae9c7e0b6a9f.19c2c97aadc",
                        "merge_info": {
                            "date": current_date,
                            "name": target.get("assignee_name", "Student"),
                            "agent_message": f"The task '{task_title}' assigned to you has been deleted by {deleter_name}."
                        }
                    }
                    await client.post("https://api.zeptomail.in/v1.1/email/template", json=assignee_payload, headers={"authorization": zepto_token}, timeout=10.0)

                # 2. Notify Assigner (if different from deleter)
                assigner_email = target.get("assigner_email")
                if assigner_email and assigner_email != deleter_email:
                    assigner_payload = {
                        "from": {"address": "support@alumnx.com", "name": "Alumnx AI Labs"},
                        "to": [{"email_address": {"address": assigner_email, "name": target.get("assigner_name", "Admin")}}],
                        "template_key": "2518b.6d1e43aa616e32a8.k1.f80371c0-025f-11f1-9250-ae9c7e0b6a9f.19c2c97aadc",
                        "merge_info": {
                            "date": current_date,
                            "name": target.get("assigner_name", "Admin"),
                            "agent_message": f"The task '{task_title}' that you assigned to {target.get('assignee_name', 'Student')} has been deleted by {deleter_name}."
                        }
                    }
                    await client.post("https://api.zeptomail.in/v1.1/email/template", json=assigner_payload, headers={"authorization": zepto_token}, timeout=10.0)
        
        return True
    except Exception as e:
        logger.error(f"⚠️ Deletion notification failed: {e}")
        return False