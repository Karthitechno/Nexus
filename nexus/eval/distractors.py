"""Synthetic distractor tool generator for scaling benchmarks.
All tools produced here are marked with is_synthetic: True and distinct namespaces.
"""
from typing import List, Dict, Any, Tuple

# Flat list of (service, category, tool_id_prefix, description, method, endpoint)
BASE_TEMPLATES: List[Tuple[str, str, str, str, str, str]] = [
    # Jira
    ("synthetic_jira", "issue_tracking", "jira_create_issue", "Create a new issue, task, or bug ticket in Jira", "POST", "/rest/api/3/issue"),
    ("synthetic_jira", "issue_tracking", "jira_get_issue", "Get issue metadata, status, assignee, and comments by issue key", "GET", "/rest/api/3/issue/{issue_id}"),
    ("synthetic_jira", "issue_tracking", "jira_update_issue", "Update issue fields or description", "PUT", "/rest/api/3/issue/{issue_id}"),
    ("synthetic_jira", "issue_tracking", "jira_delete_issue", "Delete a Jira issue ticket", "DELETE", "/rest/api/3/issue/{issue_id}"),
    ("synthetic_jira", "issue_tracking", "jira_search_jql", "Search for issues using JQL query strings", "GET", "/rest/api/3/search"),
    ("synthetic_jira", "issue_tracking", "jira_transition_issue", "Move issue status along Jira workflow", "POST", "/rest/api/3/issue/{issue_id}/transitions"),
    # GitHub
    ("synthetic_github", "version_control", "github_create_pull_request", "Create pull request on repository", "POST", "/repos/{owner}/{repo}/pulls"),
    ("synthetic_github", "version_control", "github_list_pull_requests", "List open and closed PRs", "GET", "/repos/{owner}/{repo}/pulls"),
    ("synthetic_github", "version_control", "github_merge_pull_request", "Merge pull request into target branch", "PUT", "/repos/{owner}/{repo}/pulls/{pull_number}/merge"),
    ("synthetic_github", "version_control", "github_create_repository", "Create new code repository", "POST", "/user/repos"),
    ("synthetic_github", "version_control", "github_list_commits", "List commit log entries for repo", "GET", "/repos/{owner}/{repo}/commits"),
    ("synthetic_github", "version_control", "github_create_release", "Draft and publish new software release", "POST", "/repos/{owner}/{repo}/releases"),
    # AWS S3
    ("synthetic_aws_s3", "cloud_storage", "s3_create_bucket", "Provision new AWS S3 storage bucket", "PUT", "/{bucket}"),
    ("synthetic_aws_s3", "cloud_storage", "s3_list_buckets", "List all S3 buckets for the AWS account", "GET", "/"),
    ("synthetic_aws_s3", "cloud_storage", "s3_put_object", "Upload blob file or document to S3 bucket", "PUT", "/{bucket}/{key}"),
    ("synthetic_aws_s3", "cloud_storage", "s3_get_object", "Download object payload from S3 bucket", "GET", "/{bucket}/{key}"),
    ("synthetic_aws_s3", "cloud_storage", "s3_delete_object", "Remove file object from S3 bucket", "DELETE", "/{bucket}/{key}"),
    ("synthetic_aws_s3", "cloud_storage", "s3_set_bucket_cors", "Configure cross-origin resource sharing policy", "PUT", "/{bucket}?cors"),
    # Twilio
    ("synthetic_twilio", "telecom", "twilio_send_sms", "Dispatch outbound SMS text message to destination number", "POST", "/2010-04-01/Accounts/{AccountSid}/Messages.json"),
    ("synthetic_twilio", "telecom", "twilio_get_sms_status", "Retrieve delivery status for sent message SID", "GET", "/2010-04-01/Accounts/{AccountSid}/Messages/{MessageSid}.json"),
    ("synthetic_twilio", "telecom", "twilio_initiate_call", "Start programmable voice phone call", "POST", "/2010-04-01/Accounts/{AccountSid}/Calls.json"),
    ("synthetic_twilio", "telecom", "twilio_list_phone_numbers", "Browse available virtual phone numbers for purchase", "GET", "/2010-04-01/Accounts/{AccountSid}/AvailablePhoneNumbers.json"),
    # HubSpot
    ("synthetic_hubspot", "crm", "hubspot_create_contact", "Create CRM customer lead contact record", "POST", "/crm/v3/objects/contacts"),
    ("synthetic_hubspot", "crm", "hubspot_get_contact", "Retrieve CRM contact by email or contactId", "GET", "/crm/v3/objects/contacts/{contactId}"),
    ("synthetic_hubspot", "crm", "hubspot_create_deal", "Create sales pipeline deal opportunity", "POST", "/crm/v3/objects/deals"),
    ("synthetic_hubspot", "crm", "hubspot_list_deals", "List active deals in sales pipeline", "GET", "/crm/v3/objects/deals"),
    ("synthetic_hubspot", "crm", "hubspot_update_stage", "Advance sales deal stage", "PATCH", "/crm/v3/objects/deals/{dealId}"),
    # Slack
    ("synthetic_slack", "communication", "slack_post_message", "Post notification message to channel", "POST", "/api/chat.postMessage"),
    ("synthetic_slack", "communication", "slack_create_channel", "Create new team conversation channel", "POST", "/api/conversations.create"),
    ("synthetic_slack", "communication", "slack_list_channels", "List public team channels", "GET", "/api/conversations.list"),
    ("synthetic_slack", "communication", "slack_upload_file", "Upload attachment file to channel", "POST", "/api/files.upload"),
    # Zendesk
    ("synthetic_zendesk", "customer_support", "zendesk_create_ticket", "Create support ticket for customer issue", "POST", "/api/v2/tickets.json"),
    ("synthetic_zendesk", "customer_support", "zendesk_get_ticket", "Retrieve support ticket conversation thread", "GET", "/api/v2/tickets/{ticket_id}.json"),
    ("synthetic_zendesk", "customer_support", "zendesk_update_ticket", "Add agent comment or change ticket priority", "PUT", "/api/v2/tickets/{ticket_id}.json"),
    ("synthetic_zendesk", "customer_support", "zendesk_list_tickets", "Search all active unassigned support tickets", "GET", "/api/v2/tickets.json"),
    # Stripe
    ("synthetic_stripe", "merchant_billing", "stripe_create_customer", "Create customer profile in Stripe", "POST", "/v1/customers"),
    ("synthetic_stripe", "merchant_billing", "stripe_create_charge", "Process credit card charge", "POST", "/v1/charges"),
    ("synthetic_stripe", "merchant_billing", "stripe_list_subscriptions", "List recurring customer subscriptions", "GET", "/v1/subscriptions"),
    ("synthetic_stripe", "merchant_billing", "stripe_cancel_subscription", "Terminate customer billing subscription", "DELETE", "/v1/subscriptions/{sub_id}"),
]


def generate_synthetic_distractors(target_count: int) -> List[Dict[str, Any]]:
    """Generate up to `target_count` synthetic distractor tools with guaranteed unique IDs."""
    distractors: List[Dict[str, Any]] = []
    num_templates = len(BASE_TEMPLATES)
    
    for index in range(target_count):
        service, category, prefix, description, method, endpoint = BASE_TEMPLATES[index % num_templates]
        cycle = index // num_templates
        suffix = f"_{cycle}" if cycle > 0 else ""
        
        tool_id = f"synth_{prefix}{suffix}"
        name = f"Synthetic {prefix.replace('_', ' ').title()}{suffix}"
        desc = f"[SYNTHETIC DISTRACTOR] {description} (Variant {cycle})"
        tool_endpoint = f"/synthetic{endpoint}{suffix}"
        risk = "HIGH" if method in ["POST", "PUT", "DELETE", "PATCH"] else "LOW"
        
        tool = {
            "tool_id": tool_id,
            "name": name,
            "service": service,
            "category": category,
            "description": desc,
            "method": method,
            "endpoint": tool_endpoint,
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Resource identifier"},
                    "query": {"type": "string", "description": "Search filter string"}
                },
                "required": []
            },
            "request_schema": {},
            "permission": "synthetic.execute",
            "risk_level": risk,
            "is_active": True,
            "is_synthetic": True,
            "example_queries": [
                f"How do I run {tool_id}?",
                f"Execute {name} for id 100",
                f"Call {method} {tool_endpoint}"
            ],
            "original_definition": {
                "source": "synthetic_generator",
                "version": "1.0",
                "index": index
            }
        }
        distractors.append(tool)
        
    return distractors
