#!/usr/bin/env python3
"""
MCP Jira Server Starter
Starts an MCP server that provides Jira functionality to AI assistants
"""

import os
import sys
import asyncio
import json
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from jira import JIRA

# MCP imports (you'll need to install mcp package)
try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        Resource,
        Tool,
        TextContent,
        ImageContent,
        EmbeddedResource,
    )
except ImportError:
    print("❌ MCP package not installed. Run: pip install mcp")
    sys.exit(1)

class JiraMCPServer:
    """MCP Server for Jira integration"""
    
    def __init__(self):
        self.jira = None
        self.server = Server("jira-mcp-server")
        self.setup_tools()
    
    def setup_tools(self):
        """Setup MCP tools for Jira operations"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            """List available Jira tools"""
            return [
                Tool(
                    name="jira_search",
                    description="Search for Jira issues using JQL",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "jql": {
                                "type": "string",
                                "description": "JQL query to search for issues"
                            },
                            "limit": {
                                "type": "integer", 
                                "description": "Maximum number of results",
                                "default": 50
                            },
                            "fields": {
                                "type": "string",
                                "description": "Comma-separated list of fields to return",
                                "default": "key,summary,status,priority,assignee,reporter"
                            }
                        },
                        "required": ["jql"]
                    }
                ),
                Tool(
                    name="jira_get_issue",
                    description="Get detailed information about a specific Jira issue",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {
                                "type": "string",
                                "description": "Jira issue key (e.g., HPCIA-1234)"
                            },
                            "fields": {
                                "type": "string", 
                                "description": "Comma-separated list of fields to return",
                                "default": "*all"
                            }
                        },
                        "required": ["issue_key"]
                    }
                ),
                Tool(
                    name="jira_get_projects",
                    description="List all accessible Jira projects",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls"""
            
            if not self.jira:
                await self.connect_to_jira()
            
            try:
                if name == "jira_search":
                    return await self.search_issues(arguments)
                elif name == "jira_get_issue":
                    return await self.get_issue(arguments)
                elif name == "jira_get_projects":
                    return await self.get_projects(arguments)
                else:
                    return [TextContent(
                        type="text",
                        text=f"Unknown tool: {name}"
                    )]
            except Exception as e:
                return [TextContent(
                    type="text", 
                    text=f"Error executing {name}: {str(e)}"
                )]
    
    async def connect_to_jira(self):
        """Connect to Jira using environment variables"""
        
        # Load environment variables
        load_dotenv()
        
        jira_url = os.getenv('JIRA_URL')
        jira_email = os.getenv('JIRA_EMAIL')
        jira_token = os.getenv('JIRA_API_TOKEN')
        
        if not all([jira_url, jira_email, jira_token]):
            raise Exception("Missing Jira credentials. Please set JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN")
        
        self.jira = JIRA(
            server=jira_url,
            basic_auth=(jira_email, jira_token)
        )
    
    async def search_issues(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Search for Jira issues"""
        
        jql = arguments.get('jql', '')
        limit = arguments.get('limit', 50)
        fields = arguments.get('fields', 'key,summary,status,priority,assignee,reporter')
        
        try:
            issues = self.jira.search_issues(
                jql,
                maxResults=limit,
                fields=fields
            )
            
            # Convert issues to JSON format
            issues_data = {
                "total": len(issues),
                "issues": []
            }
            
            for issue in issues:
                issue_dict = {
                    "key": issue.key,
                    "fields": {}
                }
                
                # Extract requested fields
                for field in fields.split(','):
                    field = field.strip()
                    if hasattr(issue.fields, field):
                        value = getattr(issue.fields, field)
                        if hasattr(value, '__dict__'):
                            # Convert complex objects to dict
                            issue_dict["fields"][field] = {
                                "name": getattr(value, 'name', str(value)),
                                "displayName": getattr(value, 'displayName', getattr(value, 'name', str(value)))
                            }
                        else:
                            issue_dict["fields"][field] = value
                
                issues_data["issues"].append(issue_dict)
            
            return [TextContent(
                type="text",
                text=json.dumps(issues_data, indent=2, default=str)
            )]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Search failed: {str(e)}"
            )]
    
    async def get_issue(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Get detailed issue information"""
        
        issue_key = arguments.get('issue_key', '')
        fields = arguments.get('fields', '*all')
        
        try:
            issue = self.jira.issue(issue_key, fields=fields)
            
            # Convert issue to dict
            issue_dict = {
                "key": issue.key,
                "fields": {}
            }
            
            # Get all fields if *all requested
            if fields == '*all':
                for field_name in dir(issue.fields):
                    if not field_name.startswith('_'):
                        try:
                            value = getattr(issue.fields, field_name)
                            if value is not None:
                                if hasattr(value, '__dict__'):
                                    issue_dict["fields"][field_name] = {
                                        "name": getattr(value, 'name', str(value)),
                                        "displayName": getattr(value, 'displayName', getattr(value, 'name', str(value)))
                                    }
                                else:
                                    issue_dict["fields"][field_name] = value
                        except:
                            pass
            
            return [TextContent(
                type="text",
                text=json.dumps(issue_dict, indent=2, default=str)
            )]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Failed to get issue {issue_key}: {str(e)}"
            )]
    
    async def get_projects(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Get list of accessible projects"""
        
        try:
            projects = self.jira.projects()
            
            projects_data = {
                "total": len(projects),
                "projects": [
                    {
                        "key": project.key,
                        "name": project.name,
                        "projectTypeKey": getattr(project, 'projectTypeKey', 'unknown')
                    }
                    for project in projects
                ]
            }
            
            return [TextContent(
                type="text",
                text=json.dumps(projects_data, indent=2)
            )]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Failed to get projects: {str(e)}"
            )]

async def main():
    """Main function to start the MCP server"""
    
    print("🚀 Starting Jira MCP Server...")
    print("=" * 40)
    
    # Check environment variables
    load_dotenv()
    
    required_vars = ['JIRA_URL', 'JIRA_EMAIL', 'JIRA_API_TOKEN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("💡 Please set these variables and try again")
        return
    
    print("✅ Environment variables configured")
    print(f"🎯 Jira URL: {os.getenv('JIRA_URL')}")
    print(f"👤 Email: {os.getenv('JIRA_EMAIL')}")
    
    # Create and start server
    server_instance = JiraMCPServer()
    
    print("📡 MCP Server starting on stdio...")
    print("💡 Use this server with your AI assistant for Jira integration")
    
    async with stdio_server() as (read_stream, write_stream):
        await server_instance.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="jira-mcp-server",
                server_version="1.0.0",
                capabilities=server_instance.server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities=None,
                )
            )
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 MCP Server stopped")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)



