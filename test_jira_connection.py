#!/usr/bin/env python3
"""
Test Jira Connection Script
Tests basic connectivity to your Jira instance before setting up MCP
"""

import os
import sys
from jira import JIRA
from dotenv import load_dotenv

def test_jira_connection():
    """Test basic Jira connectivity"""
    
    # Load environment variables from .env file if it exists
    load_dotenv()
    
    # Get Jira configuration from environment
    jira_url = os.getenv('JIRA_URL')
    jira_email = os.getenv('JIRA_EMAIL') 
    jira_token = os.getenv('JIRA_API_TOKEN')
    
    print("🔍 Testing Jira Connection")
    print("=" * 40)
    
    # Check if all required variables are set
    if not all([jira_url, jira_email, jira_token]):
        print("❌ Missing required environment variables:")
        if not jira_url:
            print("   - JIRA_URL not set")
        if not jira_email:
            print("   - JIRA_EMAIL not set") 
        if not jira_token:
            print("   - JIRA_API_TOKEN not set")
        print("\n💡 Please set these environment variables and try again")
        return False
    
    print(f"🎯 Jira URL: {jira_url}")
    print(f"👤 Email: {jira_email}")
    print(f"🔑 API Token: {'*' * len(jira_token[:4])}...")
    
    try:
        print("\n📡 Connecting to Jira...")
        
        # Create Jira connection
        jira = JIRA(
            server=jira_url,
            basic_auth=(jira_email, jira_token)
        )
        
        print("✅ Successfully connected to Jira!")
        
        # Test basic operations
        print("\n🔍 Testing basic operations...")
        
        # Get current user info
        current_user = jira.current_user()
        print(f"✅ Current user: {current_user}")
        
        # Test project access
        print("\n📋 Accessible projects:")
        projects = jira.projects()
        for project in projects[:5]:  # Show first 5 projects
            print(f"   - {project.key}: {project.name}")
        
        if len(projects) > 5:
            print(f"   ... and {len(projects) - 5} more projects")
        
        # Test HPCIA project specifically
        try:
            hpcia_project = jira.project('HPCIA')
            print(f"\n✅ HPCIA project found: {hpcia_project.name}")
            
            # Test search in HPCIA
            print("\n🔍 Testing search in HPCIA...")
            issues = jira.search_issues(
                'project = HPCIA', 
                maxResults=5,
                fields='key,summary,status'
            )
            
            if issues:
                print(f"✅ Found {len(issues)} issues in HPCIA (showing first 5):")
                for issue in issues:
                    print(f"   - {issue.key}: {issue.fields.summary}")
            else:
                print("📭 No issues found in HPCIA project")
                
        except Exception as e:
            print(f"⚠️  HPCIA project not accessible: {e}")
        
        print(f"\n🎉 Jira connection test successful!")
        print(f"📊 Total projects accessible: {len(projects)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to connect to Jira: {e}")
        print("\n💡 Troubleshooting tips:")
        print("   - Check your Jira URL (should include https://)")
        print("   - Verify your email address")
        print("   - Ensure your API token is correct and not expired")
        print("   - Check if your account has proper permissions")
        return False

if __name__ == "__main__":
    try:
        success = test_jira_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 Test cancelled")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

