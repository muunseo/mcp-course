#!/usr/bin/env python3
"""
Module 2: GitHub Actions Integration - STARTER CODE
Extend your PR Agent with webhook handling and MCP Prompts for CI/CD workflows.
"""

import json
import os
import subprocess
from typing import Optional
from pathlib import Path
from datetime import datetime

from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("pr-agent-actions")

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

# Path to events file where webhook_server.py stores events
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


# ===== Module 1 Tools (Already includes output limiting fix from Module 1) =====

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
            
            # Check if we need to truncate (learned from Module 1)
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


# ===== Module 2: New GitHub Actions Tools =====

@mcp.tool()
async def get_recent_actions_events(limit: int = 10) -> str:
    """Get recent GitHub Actions events received via webhook.
    
    Args:
        limit: Maximum number of events to return (default: 10)
    """
    if not EVENTS_FILE.exists():
        return json.dumps([])
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        events = json.load(f)
    # 최신 이벤트가 리스트로 저장되어 있다고 가정
    recent_events = events[-limit:]
    return json.dumps(recent_events, indent=2)


@mcp.tool()
async def get_workflow_status(workflow_name: Optional[str] = None) -> str:
    """Get the current status of GitHub Actions workflows.
    
    Args:
        workflow_name: Optional specific workflow name to filter by
    """
    if not EVENTS_FILE.exists():
        return json.dumps({})
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        events = json.load(f)

    workflow_events = [e for e in events if e.get("event") == "workflow_run"]
    if workflow_name:
        workflow_events = [e for e in workflow_events if e.get("workflow_run", {}).get("name") == workflow_name]

    latest_status = {}
    for e in workflow_events:
        name = e.get("workflow_run", {}).get("name")
        updated_at = e.get("workflow_run", {}).get("updated_at")
        status = e.get("workflow_run", {}).get("status")
        conclusion = e.get("workflow_run", {}).get("conclusion")

        # 최신 상태 갱신 (최신 시간 기준)
        if name:
            if (name not in latest_status) or (updated_at > latest_status[name]["updated_at"]):
                latest_status[name] = {
                    "updated_at": updated_at,
                    "status": status,
                    "conclusion": conclusion
                }
    return json.dumps(latest_status, indent=2)


# ===== Module 2: MCP Prompts =====

@mcp.prompt()
async def analyze_ci_results():
    return """
You are a CI/CD assistant. Using the following tools:
- get_recent_actions_events()
- get_workflow_status()

Analyze the recent GitHub Actions events and workflow statuses.
Provide a summary of the latest CI results, including any failures or important alerts.
"""


@mcp.prompt()
async def create_deployment_summary():
    return """
You are a deployment assistant. Using CI/CD results, create a clear and concise deployment summary for the team.
Include key changes, deployment status, and any issues to be aware of.
"""


@mcp.prompt()
async def generate_pr_status_report():
    return """
You are a PR status assistant. Combine code change details with CI/CD workflow statuses.
Generate a comprehensive status report that summarizes the PR’s changes and build/test results.
"""


@mcp.prompt()
async def troubleshoot_workflow_failure():
    return """
You are a troubleshooting assistant. Help analyze a failing GitHub Actions workflow.
Guide through possible causes, logs to check, and suggestions to fix the failure.
"""



if __name__ == "__main__":
    print("Starting PR Agent MCP server...")
    print("NOTE: Run webhook_server.py in a separate terminal to receive GitHub events")
    mcp.run()
