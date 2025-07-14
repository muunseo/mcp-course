#!/usr/bin/env python3
"""
Module 3: Slack Notification Integration
Combines all MCP primitives (Tools and Prompts) for complete team communication workflows.
"""
"모듈3"
import json
import os
import subprocess
from typing import Optional
from pathlib import Path
import requests  # 추가됨

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent  # 추가됨

# Initialize the FastMCP server
mcp = FastMCP("pr-agent-slack")

# PR template directory (shared between starter and solution)
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# Default PR templates
DEFAULT_TEMPLATES = {
    "bug.md": "Bug Fix",
    "feature.md": "Feature",
    "docs.md": "Documentation",
    "refactor.md": "Refactor",
    "test.md": "Test",
    "performance.md": "Performance",
    "security.md": "Security"
}

# File where webhook server stores events
EVENTS_FILE = Path(__file__).parent / "github_events.json"

# Type mapping for PR templates
TYPE_MAPPING = {
    "bug": "bug.md",
    "fix": "bug.md",
    "feature": "feature.md",
    "enhancement": "feature.md",
    "docs": "docs.md",
    "documentation": "docs.md",
    "refactor": "refactor.md",
    "cleanup": "refactor.md",
    "test": "test.md",
    "testing": "test.md",
    "performance": "performance.md",
    "optimization": "performance.md",
    "security": "security.md"
}

# ===== Tools from Modules 1 & 2 (Complete with output limiting) =====

@mcp.tool()
async def analyze_file_changes(
    base_branch: str = "main",
    include_diff: bool = True,
    max_diff_lines: int = 500
) -> str:
    """Get the full diff and list of changed files in the current git repository.
    
    Args:
        base_branch: Base branch to compare against (default: main)
        include_diff: Include the full diff content (default: true)
        max_diff_lines: Maximum number of diff lines to include (default: 500)
    """
    try:
        # Get list of changed files
        files_result = subprocess.run(
            ["git", "diff", "--name-status", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Get diff statistics
        stat_result = subprocess.run(
            ["git", "diff", "--stat", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True
        )
        
        # Get the actual diff if requested
        diff_content = ""
        truncated = False
        if include_diff:
            diff_result = subprocess.run(
                ["git", "diff", f"{base_branch}...HEAD"],
                capture_output=True,
                text=True
            )
            diff_lines = diff_result.stdout.split('\n')
            
            # Check if we need to truncate
            if len(diff_lines) > max_diff_lines:
                diff_content = '\n'.join(diff_lines[:max_diff_lines])
                diff_content += f"\n\n... Output truncated. Showing {max_diff_lines} of {len(diff_lines)} lines ..."
                diff_content += "\n... Use max_diff_lines parameter to see more ..."
                truncated = True
            else:
                diff_content = diff_result.stdout
        
        # Get commit messages for context
        commits_result = subprocess.run(
            ["git", "log", "--oneline", f"{base_branch}..HEAD"],
            capture_output=True,
            text=True
        )
        
        analysis = {
            "base_branch": base_branch,
            "files_changed": files_result.stdout,
            "statistics": stat_result.stdout,
            "commits": commits_result.stdout,
            "diff": diff_content if include_diff else "Diff not included (set include_diff=true to see full diff)",
            "truncated": truncated,
            "total_diff_lines": len(diff_lines) if include_diff else 0
        }
        
        return json.dumps(analysis, indent=2)
        
    except subprocess.CalledProcessError as e:
        return json.dumps({"error": f"Git error: {e.stderr}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""
    templates = [
        {
            "filename": filename,
            "type": template_type,
            "content": (TEMPLATES_DIR / filename).read_text()
        }
        for filename, template_type in DEFAULT_TEMPLATES.items()
    ]
    
    return json.dumps(templates, indent=2)


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Let Claude analyze the changes and suggest the most appropriate PR template.
    
    Args:
        changes_summary: Your analysis of what the changes do
        change_type: The type of change you've identified (bug, feature, docs, refactor, test, etc.)
    """
    
    # Get available templates
    templates_response = await get_pr_templates()
    templates = json.loads(templates_response)
    
    # Find matching template
    template_file = TYPE_MAPPING.get(change_type.lower(), "feature.md")
    selected_template = next(
        (t for t in templates if t["filename"] == template_file),
        templates[0]  # Default to first template if no match
    )
    
    suggestion = {
        "recommended_template": selected_template,
        "reasoning": f"Based on your analysis: '{changes_summary}', this appears to be a {change_type} change.",
        "template_content": selected_template["content"],
        "usage_hint": "Claude can help you fill out this template based on the specific changes in your PR."
    }
    
    return json.dumps(suggestion, indent=2)


@mcp.tool()
async def get_recent_actions_events(limit: int = 10) -> str:
    """Get recent GitHub Actions events received via webhook.
    
    Args:
        limit: Maximum number of events to return (default: 10)
    """
    # Read events from file
    if not EVENTS_FILE.exists():
        return json.dumps([])
    
    with open(EVENTS_FILE, 'r') as f:
        events = json.load(f)
    
    # Return most recent events
    recent = events[-limit:]
    return json.dumps(recent, indent=2)


@mcp.tool()
async def get_workflow_status(workflow_name: Optional[str] = None) -> str:
    """Get the current status of GitHub Actions workflows.
    
    Args:
        workflow_name: Optional specific workflow name to filter by
    """
    # Read events from file
    if not EVENTS_FILE.exists():
        return json.dumps({"message": "No GitHub Actions events received yet"})
    
    with open(EVENTS_FILE, 'r') as f:
        events = json.load(f)
    
    if not events:
        return json.dumps({"message": "No GitHub Actions events received yet"})
    
    # Filter for workflow events
    workflow_events = [
        e for e in events 
        if e.get("workflow_run") is not None
    ]
    
    if workflow_name:
        workflow_events = [
            e for e in workflow_events
            if e["workflow_run"].get("name") == workflow_name
        ]
    
    # Group by workflow and get latest status
    workflows = {}
    for event in workflow_events:
        run = event["workflow_run"]
        name = run["name"]
        if name not in workflows or run["updated_at"] > workflows[name]["updated_at"]:
            workflows[name] = {
                "name": name,
                "status": run["status"],
                "conclusion": run.get("conclusion"),
                "run_number": run["run_number"],
                "updated_at": run["updated_at"],
                "html_url": run["html_url"]
            }
    
    return json.dumps(list(workflows.values()), indent=2)


# ===== New Module 3: Slack Integration Tools =====

@mcp.tool()
async def send_slack_notification(message: str) -> str:
    """Slack 채널에 메시지 전송"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return "Error: SLACK_WEBHOOK_URL 환경변수가 설정되어 있지 않습니다."
    try:
        response = requests.post(
            webhook_url,
            json={"text": message, "mrkdwn": True}
        )
        if response.status_code == 200:
            return "Slack 알림 전송 성공"
        else:
            return f"Slack 알림 전송 실패: HTTP {response.status_code}"
    except Exception as e:
        return f"알림 전송 중 오류 발생: {str(e)}"


# ===== New Module 3: Slack Formatting Prompts =====

@mcp.prompt()
def format_ci_failure_alert() -> str:
    return """
    :rotating_light: *CI Failure Alert* :rotating_light:

    CI 워크플로우가 실패했습니다:
    *Workflow*: workflow_name
    *Branch*: branch_name
    *Status*: Failed
    *View Details*: <LOGS_LINK|View Logs>

    로그를 확인하고 문제를 해결해 주세요.

    Slack 마크다운 포맷팅을 사용하며, 간결하게 작성하세요.
    """

@mcp.prompt()
def format_ci_success_summary() -> str:
    return """
    :white_check_mark: *Deployment Successful* :white_check_mark:

    다음 저장소에 배포가 성공했습니다: [Repository Name]

    *변경 사항:*
    - 주요 기능 또는 수정 1
    - 주요 기능 또는 수정 2

    *링크:*
    <PR_LINK|View Changes>

    축하 메시지이면서도 유익한 정보를 담도록 작성하세요.
    Slack 마크다운 포맷팅을 사용합니다.
    """


if __name__ == "__main__":
    # Run MCP server normally
    print("Starting PR Agent Slack MCP server...")
    print("Make sure to set SLACK_WEBHOOK_URL environment variable")
    print("To receive GitHub webhooks, run the webhook server separately:")
    print("  python webhook_server.py")
    mcp.run()
