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
        "from": {"address": "support@alumnx.com", "name": "StudyBuddy"},
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

async def send_assignment_email(assignee_email, assignee_name, assigner_name, task_title, project_name="Personal", day=None, task_type=None, task_description=None):
    """Sends an assignment notification email to the student/assignee via ZeptoMail."""
    zepto_token = os.getenv("ZEPTO_MAIL_TOKEN")
    if not zepto_token:
        logger.error("ZEPTO_MAIL_TOKEN not configured")
        return False

    current_date = datetime.now().strftime("%d %b %Y")
    
    # Construct detailed agent message
    # Greeting and sign-off alignment: We set text-align: left explicitly.
    
    line1 = "A new task has been created in Project School."
    line2 = "Review the task below."
    line3 = "If you are interested, you can Add this task, Complete it and ‘Mark as Completed’ inside Claude Desktop."
    # line2 += "<a href='https://claude.ai/download' style='color: #25586B; text-decoration: underline; font-weight: bold;'>Claude Desktop</a>"
    
    # Task Details Box - Using a table for better mobile support
    box_html = f"""
    <div style="margin: 25px 0; text-align: left;">
        <table width="100%" cellspacing="0" cellpadding="0" style="border: 1px solid #DEE6E9; border-radius: 12px; background-color: #f8fafb; border-collapse: separate !important;">
            <tr>
                <td style="padding: 24px; font-family: Lato, Helvetica, Arial, sans-serif; text-align: left;">
                    <div style="margin-bottom: 18px;">
                        <span style="color: #64748b; font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.05em;">Project Name</span>
                        <div style="color: #1e293b; font-size: 16px; font-weight: 600; margin-top: 4px;">{project_name}</div>
                    </div>
                    <div style="margin-bottom: 18px;">
                        <span style="color: #64748b; font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.05em;">Task Name</span>
                        <div style="color: #1e293b; font-size: 16px; font-weight: 600; margin-top: 4px;">{task_title}</div>
                    </div>
                    <div>
                        <span style="color: #64748b; font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.05em;">Task Details</span>
                        <div style="color: #334155; font-size: 15px; line-height: 1.5; margin-top: 4px;">{task_description or "Review and complete the assigned task steps."}</div>
                    </div>
                </td>
            </tr>
        </table>
    </div>
    """
    
    message = f"<p style='margin: 0; font-size: 16px; line-height: 1.4; color: #000; text-align: left;'>{line1}</p>"
    message += f"<p style='margin: 8px 0 0 0; font-size: 16px; line-height: 1.4; color: #000; text-align: left;'>{line2}</p>"
    message += f"<p style='margin: 8px 0 0 0; font-size: 16px; line-height: 1.4; color: #000; text-align: left;'>{line3}</p>"
    message += box_html
    # message += "<p style='margin: 0; font-size: 8px; color: #000; text-align: left;'>If you need any help or have questions, please reach out to Sravan (9390787901).</p>"

    message += "<p style='margin: 0; font-size: 16px; color: #000; text-align: left;'>Thank You,</p>"

    logger.info(f"📧 Triggering assignment email to {assignee_email} with project: {project_name}")

    zepto_payload = {
        "from": {"address": "support@alumnx.com", "name": "StudyBuddy"},
        "to": [{"email_address": {"address": assignee_email, "name": assignee_name}}],
        "template_key": "2518b.6d1e43aa616e32a8.k1.f80371c0-025f-11f1-9250-ae9c7e0b6a9f.19c2c97aadc",
        "merge_info": {
            "date": current_date,
            "name": assignee_name,
            "agent_message": message
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