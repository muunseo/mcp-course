import json
import subprocess
from pathlib import Path
import asyncio
from typing import Any, Sequence

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)

# 서버 인스턴스 생성
server = Server("pr-agent")

# 템플릿 디렉토리 경로
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """사용 가능한 도구 목록 반환"""
    return [
        Tool(
            name="analyze_file_changes",
            description="Git diff를 분석하여 파일 변경사항을 확인합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "base_branch": {
                        "type": "string",
                        "description": "비교할 기준 브랜치",
                        "default": "main"
                    },
                    "include_diff": {
                        "type": "boolean",
                        "description": "diff 내용 포함 여부",
                        "default": True
                    },
                    "max_diff_lines": {
                        "type": "integer",
                        "description": "최대 diff 라인 수",
                        "default": 500
                    }
                }
            }
        ),
        Tool(
            name="get_pr_templates",
            description="사용 가능한 PR 템플릿 목록을 가져옵니다",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="suggest_template",
            description="변경사항에 따라 적절한 PR 템플릿을 제안합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "changes_summary": {
                        "type": "string",
                        "description": "변경사항 요약"
                    },
                    "change_type": {
                        "type": "string",
                        "description": "변경 유형 (bug, feature, docs, refactor, test)"
                    }
                },
                "required": ["changes_summary", "change_type"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """도구 호출 처리"""
    
    if name == "analyze_file_changes":
        base_branch = arguments.get("base_branch", "main")
        include_diff = arguments.get("include_diff", True)
        max_diff_lines = arguments.get("max_diff_lines", 500)
        
        try:
            # Git diff 실행
            result = subprocess.run(
                ["git", "diff", f"{base_branch}...HEAD"],
                capture_output=True,
                text=True,
                cwd=Path.cwd()
            )
            diff_output = result.stdout
            diff_lines = diff_output.split('\n')
            
            # 라인 수 제한
            if len(diff_lines) > max_diff_lines:
                diff_output = '\n'.join(diff_lines[:max_diff_lines])
                diff_output += f"\n\n... Output truncated. Showing {max_diff_lines} of {len(diff_lines)} lines ..."
            
            # 통계 정보
            stats_result = subprocess.run(
                ["git", "diff", "--stat", f"{base_branch}...HEAD"],
                capture_output=True,
                text=True,
                cwd=Path.cwd()
            )
            
            # 변경된 파일 목록
            files_result = subprocess.run(
                ["git", "diff", "--name-only", f"{base_branch}...HEAD"],
                capture_output=True,
                text=True,
                cwd=Path.cwd()
            )
            files_changed = files_result.stdout.strip().split('\n') if files_result.stdout.strip() else []
            
            response = {
                "stats": stats_result.stdout,
                "total_diff_lines": len(diff_lines),
                "diff": diff_output if include_diff else "Set include_diff=true to see full diff",
                "files_changed": files_changed,
            }
            
            return [TextContent(type="text", text=json.dumps(response, indent=2))]
            
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]
    
    elif name == "get_pr_templates":
        try:
            templates = {}
            
            # 템플릿 디렉토리가 존재하는지 확인
            if TEMPLATES_DIR.exists():
                for template_file in TEMPLATES_DIR.glob("*.md"):
                    name = template_file.stem
                    content = template_file.read_text(encoding="utf-8")
                    templates[name] = content
            else:
                templates = {"note": f"Template directory not found: {TEMPLATES_DIR}"}
            
            return [TextContent(type="text", text=json.dumps({"templates": templates}, indent=2))]
            
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]
    
    elif name == "suggest_template":
        changes_summary = arguments.get("changes_summary", "")
        change_type = arguments.get("change_type", "").lower()
        
        try:
            mapping = {
                "bug": "bugfix",
                "feature": "feature",
                "docs": "documentation",
                "refactor": "refactor",
                "test": "test",
            }
            suggestion = mapping.get(change_type, "general")
            
            response = {
                "suggested_template": suggestion,
                "summary": changes_summary,
                "change_type": change_type
            }
            
            return [TextContent(type="text", text=json.dumps(response, indent=2))]
            
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]
    
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

# 또는 이렇게 시도해보세요
async def main():
    from mcp.server.models import InitializationOptions
    
    async with stdio_server() as (read_stream, write_stream):
        init_options = InitializationOptions(
            server_name="pr-agent",
            server_version="1.0.0",
            capabilities={}
        )
        await server.run(read_stream, write_stream, init_options)

# MCP 서버 인스턴스 (uvicorn용)
mcp = server

if __name__ == "__main__":
    asyncio.run(main())