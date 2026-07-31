#!/usr/bin/env python3
"""
Copy CIPOE Links to VIRTSTRAT from Linked CNV and/or MTV Items

This script:
1. Finds VIRTSTRAT → CNV/MTV → CIPOE chains
2. For each CIPOE link on a CNV or MTV issue linked to a VIRTSTRAT
3. Copies that CIPOE link to the VIRTSTRAT (if not already linked)
4. Adds a Red Hat Employee comment with Claude attribution
5. Removes the executor as watcher after updates
6. For link-limited CIPOE items (e.g., IBM), adds a review notice

Usage:
    python copy_cipoe_links_to_virtstrat.py --dry-run
    python copy_cipoe_links_to_virtstrat.py --execute --bot
    python copy_cipoe_links_to_virtstrat.py --source cnv
    python copy_cipoe_links_to_virtstrat.py --source mtv
    python copy_cipoe_links_to_virtstrat.py --source both   # default
    python copy_cipoe_links_to_virtstrat.py --exclude CIPOE-30227

Link Direction (IMPORTANT):
    jira.create_issue_link(
        type="Account",
        inwardIssue=virtstrat_key,  # VIRTSTRAT shows "impacts account"
        outwardIssue=cipoe_key,     # CIPOE shows "account is impacted by"
    )
"""

from jira import JIRA
import argparse
import os
from datetime import datetime
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..', '..'))
JIRA_BASE_URL = "https://redhat.atlassian.net/browse"
LOG_FILE = os.path.join(REPO_ROOT, "cipoe_link_copy.log")

LINK_LIMITED_CIPOE = {'CIPOE-30227'}

SOURCES = {
    'cnv': {
        'prefix': 'CNV-',
        'label': 'CNV',
        'comment': 'Missing CIPOE links were added from linked CNV items',
    },
    'mtv': {
        'prefix': 'MTV-',
        'label': 'MTV',
        'comment': 'Missing CIPOE links were added from linked MTV items',
    },
}

CLAUDE_ATTRIBUTION = '\n\n---\n*This comment was added via Claude AI assistant.*'
LEGACY_COMMENT_MARKERS = (
    'CIPOE links copied from linked CNV items by Claude automation',
    'CIPOE links copied from linked MTV items by Claude automation',
    'CIPOE links copied from linked VIRTSTRAT features by Claude automation',
    'Missing CIPOE links were added from linked CNV items',
    'Missing CIPOE links were added from linked MTV items',
    'Missing CIPOE links were added from linked CNV/MTV items',
)


def _read_env_file(path):
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


def get_jira_connection(use_bot=False):
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
        )
        token = env.get('JIRA_API_TOKEN') or os.environ.get('JIRA_API_TOKEN', '')
        jira_url = env.get('JIRA_URL') or os.environ.get('JIRA_URL') or jira_url
        if not email or not token:
            raise ValueError(
                "Jira credentials not found. Create .env_jira in the repo root "
                "with JIRA_USERNAME and JIRA_API_TOKEN (see env.jira.example)"
            )

    return JIRA(server=jira_url, basic_auth=(email, token)), email


def search_virtstrat_features(jira):
    """Paginated fetch of VIRTSTRAT Features when enhanced search is available."""
    jql = 'project = VIRTSTRAT AND issuetype = Feature'
    fields = 'key,summary,issuelinks'
    if hasattr(jira, 'enhanced_search_issues'):
        return jira.enhanced_search_issues(jql, maxResults=0, fields=fields)
    return jira.search_issues(jql, maxResults=500, fields=fields)


def remove_executor_watchers(jira, issue_keys, logger):
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
    try:
        comments = jira.comments(issue_key)
        for comment in comments:
            body = comment.body if hasattr(comment, 'body') else ''
            if any(m in body for m in LEGACY_COMMENT_MARKERS) and 'link limits' in body:
                return True
    except Exception:
        pass
    return False


def comment_marker_for_sources(source_keys):
    labels = sorted({SOURCES[s]['label'] for s in source_keys})
    if labels == ['CNV']:
        return SOURCES['cnv']['comment']
    if labels == ['MTV']:
        return SOURCES['mtv']['comment']
    return 'Missing CIPOE links were added from linked CNV/MTV items'


def find_links_to_copy(jira, logger, source_keys, exclude_cipoe=None):
    """Find CIPOE links to copy from the given product sources onto VIRTSTRAT."""
    exclude_cipoe = exclude_cipoe or set()
    source_keys = list(source_keys)

    labels = ', '.join(SOURCES[s]['label'] for s in source_keys)
    logger.log("=" * 70)
    logger.log(f"Finding CIPOE links to copy from {labels} to VIRTSTRAT")
    logger.log("=" * 70)

    if exclude_cipoe:
        logger.log(f"\nExcluding CIPOE items: {exclude_cipoe}")

    logger.log("\nStep 1: Fetching VIRTSTRAT Features...")
    virtstrat_issues = search_virtstrat_features(jira)
    logger.log(f"Found {len(virtstrat_issues)} VIRTSTRAT Features")

    prefixes = {s: SOURCES[s]['prefix'] for s in source_keys}
    virtstrat_product_map = {}  # vs_key -> {summary, product_links: [{key, source}]}
    virtstrat_existing_cipoe = {}
    all_product_keys = defaultdict(set)  # source -> keys

    logger.log("\nStep 2: Analyzing VIRTSTRAT links...")
    for vs_issue in virtstrat_issues:
        product_links = []
        existing_cipoe = set()

        if hasattr(vs_issue.fields, 'issuelinks') and vs_issue.fields.issuelinks:
            for link in vs_issue.fields.issuelinks:
                linked_issue = getattr(link, 'inwardIssue', None) or getattr(link, 'outwardIssue', None)
                if not linked_issue:
                    continue
                key = linked_issue.key
                if key.startswith('CIPOE-'):
                    existing_cipoe.add(key)
                    continue
                for source, prefix in prefixes.items():
                    if key.startswith(prefix):
                        product_links.append({'key': key, 'source': source})
                        all_product_keys[source].add(key)
                        break

        if product_links:
            virtstrat_product_map[vs_issue.key] = {
                'summary': vs_issue.fields.summary,
                'product_links': product_links,
            }
            virtstrat_existing_cipoe[vs_issue.key] = existing_cipoe

    for source in source_keys:
        label = SOURCES[source]['label']
        vs_with = sum(
            1 for d in virtstrat_product_map.values()
            if any(p['source'] == source for p in d['product_links'])
        )
        logger.log(f"Found {vs_with} VIRTSTRAT items with {label} links")
        logger.log(f"Total unique {label} issues to check: {len(all_product_keys[source])}")

    logger.log("\nStep 3: Checking product issues for CIPOE links...")
    product_cipoe_map = {}  # product_key -> [cipoe info]
    total = sum(len(v) for v in all_product_keys.values())
    checked = 0

    for source in source_keys:
        label = SOURCES[source]['label']
        for product_key in sorted(all_product_keys[source]):
            checked += 1
            if checked % 10 == 0:
                logger.log(f"  Checked {checked}/{total} product issues...")
            try:
                issue = jira.issue(product_key, fields='issuelinks,summary')
                cipoe_links = []
                if hasattr(issue.fields, 'issuelinks') and issue.fields.issuelinks:
                    for link in issue.fields.issuelinks:
                        linked_issue = getattr(link, 'inwardIssue', None) or getattr(link, 'outwardIssue', None)
                        if linked_issue and linked_issue.key.startswith('CIPOE-'):
                            cipoe_key = linked_issue.key
                            if cipoe_key not in exclude_cipoe:
                                cipoe_links.append({
                                    'key': cipoe_key,
                                    'summary': (
                                        linked_issue.fields.summary
                                        if hasattr(linked_issue.fields, 'summary') else ''
                                    ),
                                    'link_limited': cipoe_key in LINK_LIMITED_CIPOE,
                                    'source': source,
                                    'source_label': label,
                                })
                if cipoe_links:
                    product_cipoe_map[product_key] = cipoe_links
            except Exception as e:
                logger.log(f"  ✗ Error checking {product_key}: {e}")

    logger.log(f"\nFound {len(product_cipoe_map)} product issues with CIPOE links")

    logger.log("\nStep 4: Determining links to create...")
    links_to_create = []
    virtstrat_has_review_comment = {}
    skipped_due_to_existing_comment = 0

    for vs_key, vs_data in virtstrat_product_map.items():
        existing_cipoe = virtstrat_existing_cipoe.get(vs_key, set())

        for product in vs_data['product_links']:
            product_key = product['key']
            if product_key not in product_cipoe_map:
                continue
            for cipoe_info in product_cipoe_map[product_key]:
                cipoe_key = cipoe_info['key']
                if cipoe_key in existing_cipoe:
                    continue

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
                    'source_key': product_key,
                    'source': cipoe_info['source'],
                    'source_label': cipoe_info['source_label'],
                    'cipoe_key': cipoe_key,
                    'cipoe_summary': cipoe_info['summary'],
                    'link_limited': cipoe_info['link_limited'],
                })
                existing_cipoe.add(cipoe_key)

    if skipped_due_to_existing_comment > 0:
        logger.log(
            f"\nSkipped {skipped_due_to_existing_comment} link-limited CIPOE entries "
            "(review comment already exists)"
        )

    waiting_for_limit = []
    for vs_key, vs_data in virtstrat_product_map.items():
        if vs_key not in virtstrat_has_review_comment or not virtstrat_has_review_comment[vs_key]:
            continue
        for product in vs_data['product_links']:
            product_key = product['key']
            if product_key not in product_cipoe_map:
                continue
            for cipoe_info in product_cipoe_map[product_key]:
                if cipoe_info['link_limited']:
                    waiting_for_limit.append({
                        'virtstrat_key': vs_key,
                        'cipoe_key': cipoe_info['key'],
                        'source_key': product_key,
                        'source_label': cipoe_info['source_label'],
                    })

    if waiting_for_limit:
        logger.log("\n" + "-" * 70)
        logger.log("WAITING FOR LINK LIMIT TO CLEAR")
        logger.log("-" * 70)
        logger.log(
            f"{len(waiting_for_limit)} link(s) pending - will be created when "
            "CIPOE link limit is cleared:\n"
        )
        logger.log("| VIRTSTRAT | CIPOE (at limit) | Source |")
        logger.log("|-----------|------------------|--------|")
        for item in waiting_for_limit:
            logger.log(
                f"| {item['virtstrat_key']} | {item['cipoe_key']} | "
                f"{item['source_key']} ({item['source_label']}) |"
            )
        logger.log("\nNote: These VIRTSTRAT items already have a review comment. Once the")
        logger.log(f"link limit is cleared on {LINK_LIMITED_CIPOE}, re-run this script.")
        logger.log("-" * 70)

    return links_to_create


def copy_links(jira, links_to_create, logger, dry_run=True):
    logger.log("\n" + "=" * 70)
    if dry_run:
        logger.log("DRY RUN - Previewing links to create (no changes will be made)")
    else:
        logger.log("EXECUTING - Creating links in Jira")
    logger.log("=" * 70)

    if not links_to_create:
        logger.log("\nNo new links to create - all CIPOE links are already on VIRTSTRAT items.")
        return

    by_virtstrat = defaultdict(list)
    for link in links_to_create:
        by_virtstrat[link['virtstrat_key']].append(link)

    logger.log(
        f"\n{len(links_to_create)} new links to create across "
        f"{len(by_virtstrat)} VIRTSTRAT items:\n"
    )
    logger.log("| VIRTSTRAT | CIPOE to Add | Source | Customer | Action |")
    logger.log("|-----------|--------------|--------|----------|--------|")
    for link in links_to_create:
        customer = link['cipoe_summary'][:25] + "..." if len(link['cipoe_summary']) > 25 else link['cipoe_summary']
        action = "Link + Review Comment" if link['link_limited'] else "Link + Comment"
        src = f"{link['source_key']} ({link['source_label']})"
        logger.log(
            f"| {link['virtstrat_key']} | {link['cipoe_key']} | {src} | {customer} | {action} |"
        )

    marker = comment_marker_for_sources(l['source'] for l in links_to_create)

    if dry_run:
        review_vs = set(l['virtstrat_key'] for l in links_to_create if l['link_limited'])
        if review_vs:
            logger.log("\n" + "-" * 70)
            logger.log(f"{len(review_vs)} VIRTSTRAT items will get a special review comment:")
            logger.log("-" * 70)
            for vs in sorted(review_vs):
                logger.log(f"  {vs}")
            logger.log("\nReview comment text (Red Hat Employee visibility):")
            logger.log(f'  "{marker}. N link(s) added.')
            logger.log('   Please review the linked RFE as not all CIPOE links were able')
            logger.log('   to be included at this time due to link limits."')
            logger.log('   + Claude AI assistant attribution')

        logger.log("\n" + "-" * 70)
        logger.log("This is a DRY RUN. To execute these changes, run with --execute")
        logger.log("-" * 70)
        return

    logger.log("\n" + "-" * 70)
    logger.log("Creating links...")
    logger.log("-" * 70)

    created = 0
    errors = 0
    virtstrat_success = defaultdict(list)
    virtstrat_sources = defaultdict(set)
    virtstrat_needs_review = set()

    for link in links_to_create:
        vs_key = link['virtstrat_key']
        cipoe_key = link['cipoe_key']
        customer = link['cipoe_summary'][:30] + "..." if len(link['cipoe_summary']) > 30 else link['cipoe_summary']

        try:
            jira.create_issue_link(
                type="Account",
                inwardIssue=vs_key,
                outwardIssue=cipoe_key,
            )
            logger.log(
                f"  ✓ Created: {vs_key} → {cipoe_key} ({customer}) "
                f"via {link['source_key']}"
            )
            created += 1
            virtstrat_success[vs_key].append(cipoe_key)
            virtstrat_sources[vs_key].add(link['source'])
        except Exception as e:
            error_msg = str(e)
            if 'LIMIT_EXCEEDED' in error_msg or '2000' in error_msg:
                logger.log(f"  ✗ LINK LIMIT: {vs_key} → {cipoe_key} (2000 link limit on CIPOE)")
                virtstrat_needs_review.add(vs_key)
            else:
                logger.log(f"  ✗ Error: {vs_key} → {cipoe_key}: {error_msg[:50]}")
            errors += 1

        if link['link_limited']:
            virtstrat_needs_review.add(vs_key)

    logger.log("\n" + "-" * 70)
    logger.log("Adding comments to VIRTSTRAT issues...")
    logger.log("-" * 70)

    commented = 0
    skipped_comments = 0
    all_virtstrats = set(virtstrat_success.keys()) | virtstrat_needs_review

    for vs_key in sorted(all_virtstrats):
        success_count = len(virtstrat_success.get(vs_key, []))
        needs_review = vs_key in virtstrat_needs_review

        if needs_review and has_existing_review_comment(jira, vs_key):
            logger.log(f"  ⏭ Skipped {vs_key} (review comment already exists)")
            skipped_comments += 1
            continue

        if success_count == 0 and not needs_review:
            continue

        vs_marker = comment_marker_for_sources(virtstrat_sources.get(vs_key) or {
            l['source'] for l in links_to_create if l['virtstrat_key'] == vs_key
        })

        if needs_review:
            comment = (
                f"{vs_marker}. {success_count} link(s) added. "
                f"Please review the linked RFE as not all CIPOE links were able to be "
                f"included at this time due to link limits.{CLAUDE_ATTRIBUTION}"
            )
        else:
            comment = f"{vs_marker}. {success_count} link(s) added.{CLAUDE_ATTRIBUTION}"

        try:
            jira.add_comment(
                vs_key,
                comment,
                visibility={'type': 'group', 'value': 'Red Hat Employee'},
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
        logger.log(f"  {vs_key}: https://redhat.atlassian.net/browse/{vs_key}")

    remove_executor_watchers(jira, all_virtstrats, logger)


def main():
    parser = argparse.ArgumentParser(
        description='Copy CIPOE links from CNV and/or MTV onto linked VIRTSTRAT Features'
    )
    parser.add_argument('--dry-run', action='store_true', help='Preview only (default)')
    parser.add_argument('--execute', action='store_true', help='Create links in Jira')
    parser.add_argument('--bot', action='store_true', help='Run as VME Automation Bot')
    parser.add_argument(
        '--source',
        choices=['cnv', 'mtv', 'both'],
        default='both',
        help='Product source(s) to scan (default: both)',
    )
    parser.add_argument(
        '--exclude',
        nargs='*',
        default=[],
        help='CIPOE keys to exclude (e.g., --exclude CIPOE-30227)',
    )

    args = parser.parse_args()
    dry_run = not args.execute
    exclude_cipoe = set(args.exclude) if args.exclude else set()
    source_keys = ['cnv', 'mtv'] if args.source == 'both' else [args.source]

    logger = Logger(LOG_FILE)
    logger.start()

    try:
        source_label = ' + '.join(SOURCES[s]['label'] for s in source_keys)
        logger.log("=" * 70)
        logger.log(f"CIPOE Link Copy Tool: {source_label} → VIRTSTRAT")
        logger.log("=" * 70)
        logger.log(f"\nExecution Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.log(f"Mode: {'DRY RUN (preview only)' if dry_run else 'EXECUTE (will create links)'}")
        logger.log(f"Running as: {'VME Automation Bot' if args.bot else 'Personal account'}")
        logger.log(f"Source: {args.source}")
        if exclude_cipoe:
            logger.log(f"Excluding: {exclude_cipoe}")
        logger.log(f"Link-limited CIPOE (review comment): {LINK_LIMITED_CIPOE}")
        logger.log(f"Log file: {LOG_FILE}")

        logger.log("\nConnecting to Jira...")
        jira, email = get_jira_connection(use_bot=args.bot)
        logger.log(f"Connected as: {email}")

        links_to_create = find_links_to_copy(jira, logger, source_keys, exclude_cipoe)
        copy_links(jira, links_to_create, logger, dry_run=dry_run)

    finally:
        logger.close()

    print(f"\nLog saved to: {LOG_FILE}")


if __name__ == "__main__":
    main()
