#!/usr/bin/env python3
"""
Copy CIPOE Links to VIRTSTRAT from Linked CNV Items

This script:
1. Finds all VIRTSTRAT → CNV → CIPOE chains
2. For each CIPOE link on a CNV that's linked to a VIRTSTRAT
3. Copies that CIPOE link to the VIRTSTRAT (if not already linked)
4. Adds a comment indicating links were added (Red Hat Employee visibility)
5. For link-limited CIPOE items (e.g., IBM), adds a review notice

Usage:
    python copy_cipoe_links_to_virtstrat.py --dry-run              # Preview changes
    python copy_cipoe_links_to_virtstrat.py --execute              # Execute as nwilker
    python copy_cipoe_links_to_virtstrat.py --execute --bot        # Execute as VME bot
    python copy_cipoe_links_to_virtstrat.py --exclude CIPOE-30227  # Exclude specific CIPOE

Link Direction (IMPORTANT):
    Links are created with Account link type:
    - VIRTSTRAT shows "impacts account" → CIPOE
    - CIPOE shows "account is impacted by" ← VIRTSTRAT
    
    API call (counterintuitive):
        jira.create_issue_link(
            type="Account",
            inwardIssue=virtstrat_key,  # Shows "impacts account" on VIRTSTRAT
            outwardIssue=cipoe_key       # Shows "account is impacted by" on CIPOE
        )
"""

from jira import JIRA
import argparse
import os
import sys
from datetime import datetime
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# scripts/ → skill/ → skills/ → .cursor/ → repo root
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..', '..'))
JIRA_BASE_URL = "https://redhat.atlassian.net/browse"
LOG_FILE = os.path.join(REPO_ROOT, "cipoe_link_copy.log")

# CIPOE issues known to have 2000 link limit reached
LINK_LIMITED_CIPOE = {'CIPOE-30227'}

COMMENT_MARKER = 'Missing CIPOE links were added from linked CNV items'
CLAUDE_ATTRIBUTION = '\n\n---\n*This comment was added via Claude AI assistant.*'
# Legacy text from prior automation runs (used to detect existing review comments)
LEGACY_COMMENT_MARKER = 'CIPOE links copied from linked CNV items by Claude automation'


def _read_env_file(path):
    """Load KEY=VALUE pairs from an env file into a dict (no export required)."""
    values = {}
    if not os.path.exists(path):
        return values
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            if line.startswith('export '):
                line = line[len('export '):]
            key, _, val = line.partition('=')
            values[key.strip()] = val.strip().strip('"').strip("'")
    return values


class Logger:
    """Simple logger that writes to both console and file"""
    
    def __init__(self, log_file):
        self.log_file = log_file
        self.log_handle = None
    
    def start(self):
        self.log_handle = open(self.log_file, 'a')
        self.log_handle.write("\n" + "=" * 80 + "\n")
    
    def log(self, message=""):
        print(message)
        if self.log_handle:
            self.log_handle.write(message + "\n")
            self.log_handle.flush()
    
    def close(self):
        if self.log_handle:
            self.log_handle.write("=" * 80 + "\n\n")
            self.log_handle.close()


def jira_link(key):
    return f"[{key}]({JIRA_BASE_URL}/{key})"


def get_jira_connection(use_bot=False):
    """Get Jira connection using either personal or bot credentials (repo-root env files)."""
    jira_url = 'https://redhat.atlassian.net'

    if use_bot:
        email = 'vme-automation-bot@redhat.com'
        env_file = os.path.join(REPO_ROOT, '.env_vme_automation_bot')
        env = _read_env_file(env_file)
        token = env.get('JIRA_API_TOKEN') or os.environ.get('VME_BOT_JIRA_TOKEN', '')
        email = env.get('JIRA_USERNAME') or env.get('JIRA_EMAIL') or email
        jira_url = env.get('JIRA_URL') or jira_url
        if not token:
            raise ValueError(
                "VME bot token not found. Set VME_BOT_JIRA_TOKEN or create "
                f"{env_file} (see env.bot.example)"
            )
    else:
        # Prefer shared .env_jira, then legacy .env_wilker_jira
        env = {}
        for name in ('.env_jira', '.env_wilker_jira'):
            path = os.path.join(REPO_ROOT, name)
            if os.path.exists(path):
                env = _read_env_file(path)
                break
        email = (
            env.get('JIRA_USERNAME')
            or env.get('JIRA_EMAIL')
            or os.environ.get('JIRA_USERNAME')
            or os.environ.get('JIRA_EMAIL')
            or 'nwilker@redhat.com'
        )
        token = env.get('JIRA_API_TOKEN') or os.environ.get('JIRA_API_TOKEN', '')
        jira_url = env.get('JIRA_URL') or os.environ.get('JIRA_URL') or jira_url
        if not token:
            raise ValueError(
                "Jira token not found. Create .env_jira in the repo root "
                "(see env.jira.example) or set JIRA_API_TOKEN"
            )

    jira = JIRA(server=jira_url, basic_auth=(email, token))
    return jira, email


def remove_executor_watchers(jira, issue_keys, logger):
    """Remove the executing user as watcher from touched VIRTSTRAT issues."""
    if not issue_keys:
        return

    try:
        account_id = jira.myself()['accountId']
    except Exception as e:
        logger.log(f"\nCould not resolve executor account for watcher cleanup: {e}")
        return

    logger.log("\n" + "-" * 70)
    logger.log("Removing executor from watchers on touched VIRTSTRAT items...")
    logger.log("-" * 70)

    removed = 0
    for issue_key in sorted(issue_keys):
        try:
            watchers = jira.watchers(issue_key)
            watcher_list = watchers.watchers if hasattr(watchers, 'watchers') else []
            is_watching = any(getattr(w, 'accountId', None) == account_id for w in watcher_list)
            if is_watching:
                jira.remove_watcher(issue_key, account_id)
                logger.log(f"  ✓ Removed watcher from {issue_key}")
                removed += 1
        except Exception as e:
            logger.log(f"  ✗ Error removing watcher from {issue_key}: {e}")

    if removed == 0:
        logger.log("  No watcher cleanup needed")


def has_existing_review_comment(jira, issue_key):
    """Check if a VIRTSTRAT issue already has a Claude automation review comment"""
    try:
        comments = jira.comments(issue_key)
        for comment in comments:
            body = comment.body if hasattr(comment, 'body') else ''
            if (COMMENT_MARKER in body or LEGACY_COMMENT_MARKER in body) and 'link limits' in body:
                return True
    except Exception:
        pass
    return False


def find_links_to_copy(jira, logger, exclude_cipoe=None):
    """Find all CIPOE links that should be copied from CNV to VIRTSTRAT"""
    
    exclude_cipoe = exclude_cipoe or set()
    
    logger.log("=" * 70)
    logger.log("Finding CIPOE links to copy from CNV to VIRTSTRAT")
    logger.log("=" * 70)
    
    if exclude_cipoe:
        logger.log(f"\nExcluding CIPOE items: {exclude_cipoe}")
    
    # Step 1: Get all VIRTSTRAT Features with their links
    logger.log("\nStep 1: Fetching VIRTSTRAT Features...")
    virtstrat_issues = jira.search_issues(
        'project = VIRTSTRAT AND issuetype = Feature',
        maxResults=500,
        fields='key,summary,issuelinks'
    )
    logger.log(f"Found {len(virtstrat_issues)} VIRTSTRAT Features")
    
    # Step 2: Build map of VIRTSTRAT → CNV links and existing CIPOE links
    logger.log("\nStep 2: Analyzing VIRTSTRAT links...")
    virtstrat_cnv_map = {}
    virtstrat_existing_cipoe = {}
    all_cnv_keys = set()
    
    for vs_issue in virtstrat_issues:
        cnv_links = []
        existing_cipoe = set()
        
        if hasattr(vs_issue.fields, 'issuelinks') and vs_issue.fields.issuelinks:
            for link in vs_issue.fields.issuelinks:
                linked_issue = getattr(link, 'inwardIssue', None) or getattr(link, 'outwardIssue', None)
                if linked_issue:
                    if linked_issue.key.startswith('CNV-'):
                        cnv_links.append(linked_issue.key)
                        all_cnv_keys.add(linked_issue.key)
                    elif linked_issue.key.startswith('CIPOE-'):
                        existing_cipoe.add(linked_issue.key)
        
        if cnv_links:
            virtstrat_cnv_map[vs_issue.key] = {
                'summary': vs_issue.fields.summary,
                'cnv_links': cnv_links
            }
            virtstrat_existing_cipoe[vs_issue.key] = existing_cipoe
    
    logger.log(f"Found {len(virtstrat_cnv_map)} VIRTSTRAT items with CNV links")
    logger.log(f"Total unique CNV issues to check: {len(all_cnv_keys)}")
    
    # Step 3: Get CIPOE links from each CNV
    logger.log("\nStep 3: Checking CNV issues for CIPOE links...")
    cnv_cipoe_map = {}
    checked = 0
    
    for cnv_key in sorted(all_cnv_keys):
        checked += 1
        if checked % 10 == 0:
            logger.log(f"  Checked {checked}/{len(all_cnv_keys)} CNV issues...")
        
        try:
            cnv_issue = jira.issue(cnv_key, fields='issuelinks,summary')
            cipoe_links = []
            
            if hasattr(cnv_issue.fields, 'issuelinks') and cnv_issue.fields.issuelinks:
                for link in cnv_issue.fields.issuelinks:
                    linked_issue = getattr(link, 'inwardIssue', None) or getattr(link, 'outwardIssue', None)
                    if linked_issue and linked_issue.key.startswith('CIPOE-'):
                        cipoe_key = linked_issue.key
                        if cipoe_key not in exclude_cipoe:
                            cipoe_links.append({
                                'key': cipoe_key,
                                'summary': linked_issue.fields.summary if hasattr(linked_issue.fields, 'summary') else '',
                                'link_limited': cipoe_key in LINK_LIMITED_CIPOE
                            })
            
            if cipoe_links:
                cnv_cipoe_map[cnv_key] = cipoe_links
                
        except Exception as e:
            logger.log(f"  ✗ Error checking {cnv_key}: {e}")
    
    logger.log(f"\nFound {len(cnv_cipoe_map)} CNV issues with CIPOE links")
    
    # Step 4: Determine which links need to be created
    logger.log("\nStep 4: Determining links to create...")
    links_to_create = []
    virtstrat_has_review_comment = {}  # Cache for review comment checks
    skipped_due_to_existing_comment = 0
    
    for vs_key, vs_data in virtstrat_cnv_map.items():
        existing_cipoe = virtstrat_existing_cipoe.get(vs_key, set())
        
        for cnv_key in vs_data['cnv_links']:
            if cnv_key in cnv_cipoe_map:
                for cipoe_info in cnv_cipoe_map[cnv_key]:
                    cipoe_key = cipoe_info['key']
                    
                    if cipoe_key not in existing_cipoe:
                        # For link-limited CIPOE, check if review comment already exists
                        if cipoe_info['link_limited']:
                            if vs_key not in virtstrat_has_review_comment:
                                virtstrat_has_review_comment[vs_key] = has_existing_review_comment(jira, vs_key)
                            
                            if virtstrat_has_review_comment[vs_key]:
                                skipped_due_to_existing_comment += 1
                                existing_cipoe.add(cipoe_key)
                                continue
                        
                        links_to_create.append({
                            'virtstrat_key': vs_key,
                            'virtstrat_summary': vs_data['summary'],
                            'cnv_key': cnv_key,
                            'cipoe_key': cipoe_key,
                            'cipoe_summary': cipoe_info['summary'],
                            'link_limited': cipoe_info['link_limited']
                        })
                        existing_cipoe.add(cipoe_key)
    
    if skipped_due_to_existing_comment > 0:
        logger.log(f"\nSkipped {skipped_due_to_existing_comment} link-limited CIPOE entries (review comment already exists)")
    
    # Track items waiting for link limit to clear
    waiting_for_limit = []
    for vs_key, vs_data in virtstrat_cnv_map.items():
        if vs_key in virtstrat_has_review_comment and virtstrat_has_review_comment[vs_key]:
            for cnv_key in vs_data['cnv_links']:
                if cnv_key in cnv_cipoe_map:
                    for cipoe_info in cnv_cipoe_map[cnv_key]:
                        if cipoe_info['link_limited']:
                            waiting_for_limit.append({
                                'virtstrat_key': vs_key,
                                'cipoe_key': cipoe_info['key'],
                                'cnv_key': cnv_key
                            })
    
    if waiting_for_limit:
        logger.log("\n" + "-" * 70)
        logger.log("WAITING FOR LINK LIMIT TO CLEAR")
        logger.log("-" * 70)
        logger.log(f"{len(waiting_for_limit)} link(s) pending - will be created when CIPOE link limit is cleared:\n")
        logger.log("| VIRTSTRAT | CIPOE (at limit) | Source CNV |")
        logger.log("|-----------|------------------|------------|")
        for item in waiting_for_limit:
            logger.log(f"| {item['virtstrat_key']} | {item['cipoe_key']} | {item['cnv_key']} |")
        logger.log("\nNote: These VIRTSTRAT items already have a review comment. Once the")
        logger.log(f"link limit is cleared on {LINK_LIMITED_CIPOE}, re-run this script to")
        logger.log("create the actual links. Consider removing CIPOE from LINK_LIMITED_CIPOE")
        logger.log("set in the script once links can be created.")
        logger.log("-" * 70)
    
    return links_to_create


def copy_links(jira, links_to_create, logger, dry_run=True):
    """Create the CIPOE links on VIRTSTRAT issues"""
    
    logger.log("\n" + "=" * 70)
    if dry_run:
        logger.log("DRY RUN - Previewing links to create (no changes will be made)")
    else:
        logger.log("EXECUTING - Creating links in Jira")
    logger.log("=" * 70)
    
    if not links_to_create:
        logger.log("\nNo new links to create - all CIPOE links are already on VIRTSTRAT items.")
        return
    
    # Group by VIRTSTRAT for better display
    by_virtstrat = defaultdict(list)
    for link in links_to_create:
        by_virtstrat[link['virtstrat_key']].append(link)
    
    logger.log(f"\n{len(links_to_create)} new links to create across {len(by_virtstrat)} VIRTSTRAT items:\n")
    
    # Display summary table
    logger.log("| VIRTSTRAT | CIPOE to Add | Source CNV | Customer | Action |")
    logger.log("|-----------|--------------|------------|----------|--------|")
    for link in links_to_create:
        customer = link['cipoe_summary'][:25] + "..." if len(link['cipoe_summary']) > 25 else link['cipoe_summary']
        action = "Link + Review Comment" if link['link_limited'] else "Link + Comment"
        logger.log(f"| {link['virtstrat_key']} | {link['cipoe_key']} | {link['cnv_key']} | {customer} | {action} |")
    
    if dry_run:
        # Show which VIRTSTRATs will get review comments
        review_vs = set(l['virtstrat_key'] for l in links_to_create if l['link_limited'])
        if review_vs:
            logger.log("\n" + "-" * 70)
            logger.log(f"{len(review_vs)} VIRTSTRAT items will get a special review comment:")
            logger.log("-" * 70)
            for vs in sorted(review_vs):
                logger.log(f"  {vs}")
            logger.log("\nReview comment text (Red Hat Employee visibility):")
            logger.log(f'  "{COMMENT_MARKER}. N link(s) added.')
            logger.log('   Please review the linked RFE as not all CIPOE links were able')
            logger.log('   to be included at this time due to link limits."')
            logger.log('   + Claude AI assistant attribution')
        
        logger.log("\n" + "-" * 70)
        logger.log("This is a DRY RUN. To execute these changes, run with --execute")
        logger.log("-" * 70)
        return
    
    # Execute the link creation
    logger.log("\n" + "-" * 70)
    logger.log("Creating links...")
    logger.log("-" * 70)
    
    created = 0
    errors = 0
    virtstrat_success = defaultdict(list)
    virtstrat_needs_review = set()
    
    for link in links_to_create:
        vs_key = link['virtstrat_key']
        cipoe_key = link['cipoe_key']
        customer = link['cipoe_summary'][:30] + "..." if len(link['cipoe_summary']) > 30 else link['cipoe_summary']
        
        try:
            # Create link with correct direction:
            # VIRTSTRAT shows "impacts account" → CIPOE
            # CIPOE shows "account is impacted by" ← VIRTSTRAT
            jira.create_issue_link(
                type="Account",
                inwardIssue=vs_key,
                outwardIssue=cipoe_key
            )
            logger.log(f"  ✓ Created: {vs_key} → {cipoe_key} ({customer})")
            created += 1
            virtstrat_success[vs_key].append(cipoe_key)
        except Exception as e:
            error_msg = str(e)
            if 'LIMIT_EXCEEDED' in error_msg or '2000' in error_msg:
                logger.log(f"  ✗ LINK LIMIT: {vs_key} → {cipoe_key} (2000 link limit on CIPOE)")
                virtstrat_needs_review.add(vs_key)
            else:
                logger.log(f"  ✗ Error: {vs_key} → {cipoe_key}: {error_msg[:50]}")
            errors += 1
        
        # Track if this VIRTSTRAT needs the review comment
        if link['link_limited']:
            virtstrat_needs_review.add(vs_key)
    
    # Add comments to VIRTSTRAT issues
    logger.log("\n" + "-" * 70)
    logger.log("Adding comments to VIRTSTRAT issues...")
    logger.log("-" * 70)
    
    commented = 0
    skipped_comments = 0
    all_virtstrats = set(virtstrat_success.keys()) | virtstrat_needs_review
    
    for vs_key in sorted(all_virtstrats):
        success_count = len(virtstrat_success.get(vs_key, []))
        needs_review = vs_key in virtstrat_needs_review
        
        # Check if review comment already exists (skip if so for review-type comments)
        if needs_review and has_existing_review_comment(jira, vs_key):
            logger.log(f"  ⏭ Skipped {vs_key} (review comment already exists)")
            skipped_comments += 1
            continue
        
        # Skip if no links were actually added and no review needed
        if success_count == 0 and not needs_review:
            continue
        
        if needs_review:
            comment = (f"{COMMENT_MARKER}. {success_count} link(s) added. "
                       f"Please review the linked RFE as not all CIPOE links were able to be "
                       f"included at this time due to link limits.{CLAUDE_ATTRIBUTION}")
        else:
            comment = f"{COMMENT_MARKER}. {success_count} link(s) added.{CLAUDE_ATTRIBUTION}"
        
        try:
            jira.add_comment(
                vs_key,
                comment,
                visibility={'type': 'group', 'value': 'Red Hat Employee'}
            )
            comment_type = "(with review notice)" if needs_review else ""
            logger.log(f"  ✓ Commented on {vs_key} {comment_type}")
            commented += 1
        except Exception as e:
            logger.log(f"  ✗ Error commenting on {vs_key}: {e}")
    
    logger.log("\n" + "=" * 70)
    logger.log("EXECUTION COMPLETE")
    logger.log("=" * 70)
    logger.log(f"Links created: {created}")
    logger.log(f"Links failed (limit): {errors}")
    logger.log(f"Comments added: {commented}")
    logger.log(f"Comments skipped (already exist): {skipped_comments}")
    logger.log(f"VIRTSTRATs with review notice: {len(virtstrat_needs_review)}")
    
    logger.log("\n" + "-" * 70)
    logger.log("Updated VIRTSTRAT items:")
    logger.log("-" * 70)
    for vs_key in sorted(all_virtstrats):
        url = f"https://redhat.atlassian.net/browse/{vs_key}"
        logger.log(f"  {vs_key}: {url}")

    remove_executor_watchers(jira, all_virtstrats, logger)


def main():
    parser = argparse.ArgumentParser(
        description='Copy CIPOE links from CNV to linked VIRTSTRAT issues'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without making them (default behavior)'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually create the links in Jira'
    )
    parser.add_argument(
        '--bot',
        action='store_true',
        help='Run as VME Automation Bot instead of personal account'
    )
    parser.add_argument(
        '--exclude',
        nargs='*',
        default=[],
        help='CIPOE keys to exclude (e.g., --exclude CIPOE-30227)'
    )
    
    args = parser.parse_args()
    
    # Default to dry run unless --execute is specified
    dry_run = not args.execute
    exclude_cipoe = set(args.exclude) if args.exclude else set()
    
    # Initialize logger
    logger = Logger(LOG_FILE)
    logger.start()
    
    try:
        logger.log("=" * 70)
        logger.log("CIPOE Link Copy Tool: CNV → VIRTSTRAT")
        logger.log("=" * 70)
        logger.log(f"\nExecution Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.log(f"Mode: {'DRY RUN (preview only)' if dry_run else 'EXECUTE (will create links)'}")
        logger.log(f"Running as: {'VME Automation Bot' if args.bot else 'Personal account'}")
        if exclude_cipoe:
            logger.log(f"Excluding: {exclude_cipoe}")
        logger.log(f"Link-limited CIPOE (review comment): {LINK_LIMITED_CIPOE}")
        logger.log(f"Log file: {LOG_FILE}")
        
        logger.log("\nConnecting to Jira...")
        jira, email = get_jira_connection(use_bot=args.bot)
        logger.log(f"Connected as: {email}")
        
        links_to_create = find_links_to_copy(jira, logger, exclude_cipoe)
        copy_links(jira, links_to_create, logger, dry_run=dry_run)
        
    finally:
        logger.close()
    
    print(f"\nLog saved to: {LOG_FILE}")


if __name__ == "__main__":
    main()
