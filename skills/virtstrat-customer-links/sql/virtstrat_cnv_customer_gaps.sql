-- ============================================================
-- Customer GAPS on VIRTSTRAT Features
-- Customers linked to CNV/MTV Feature Requests NOT yet on the
-- linked VIRTSTRAT Feature
--
-- Run in Dataverse (Interested Parties + Jira marts). Do not page the
-- Customer Intelligence REST/MCP for whole-project dumps.
--
-- Warehouse can lag live links. After this query, live-verify with bulk
-- MCP search_links q=VIRTSTRAT- (paged), not per-issue get_issue_links.
-- Then create_link only for pairs still missing.
--
-- Key design:
--   - VIRTSTRAT: Feature issue type (10142), ANY status
--   - Sources (default): CNV + MTV Feature Request only (issuetype 10111)
--   - To include all issue types for a project, drop the issuetype filter
--     for that project (or both).
--   - Link types: ALL link types between source and VIRTSTRAT (both directions)
--   - Gap detection: per customer_mdm_pk anti-join (not per issue)
--   - DISTINCT on core keys to collapse bidirectional link duplicates
--
-- Column note: cnv_issue_key / cnv_summary are historical names for the
-- source Feature Request key/summary (CNV or MTV). Prefer source_* aliases.
-- ============================================================

WITH virtstrat_features AS (
    SELECT
        i.id,
        i.issue_key    AS virtstrat_issue_key,
        i.summary      AS virtstrat_summary,
        s.pname        AS virtstrat_status
    FROM jira_db.cloudrhai_marts.jira_issue_non_pii i
    JOIN jira_db.cloudrhai_marts.jira_issuestatus_rhai s
      ON i.issuestatus_id = s.id
    WHERE i.project   = 'VIRTSTRAT'
      AND i.issuetype = 10142
),

related_source_frs AS (
    SELECT DISTINCT
        vs.virtstrat_issue_key, vs.virtstrat_summary, vs.virtstrat_status,
        src.project   AS source_project,
        src.issue_key AS source_issue_key,
        src.summary   AS source_summary
    FROM virtstrat_features vs
    JOIN jira_db.cloudrhai_marts.jira_issuelink_rhai il ON il.destination = vs.id
    JOIN jira_db.cloudrhai_marts.jira_issue_non_pii src ON src.id = il.source
    WHERE src.project IN ('CNV', 'MTV')
      AND src.issuetype = 10111  -- Feature Request

    UNION

    SELECT DISTINCT
        vs.virtstrat_issue_key, vs.virtstrat_summary, vs.virtstrat_status,
        src.project   AS source_project,
        src.issue_key AS source_issue_key,
        src.summary   AS source_summary
    FROM virtstrat_features vs
    JOIN jira_db.cloudrhai_marts.jira_issuelink_rhai il ON il.source = vs.id
    JOIN jira_db.cloudrhai_marts.jira_issue_non_pii src ON src.id = il.destination
    WHERE src.project IN ('CNV', 'MTV')
      AND src.issuetype = 10111  -- Feature Request
),

source_customers AS (
    SELECT DISTINCT
        rsf.virtstrat_issue_key, rsf.virtstrat_summary, rsf.virtstrat_status,
        rsf.source_project, rsf.source_issue_key, rsf.source_summary,
        cl.customer_mdm_pk, cl.customer_name,
        cl.link_context    AS customer_link_context,
        cl.linked_by_email AS customer_linked_by
    FROM related_source_frs rsf
    JOIN interestedparties_db.marts.fct_current_customer_links cl
      ON cl.issue_key    = rsf.source_issue_key
     AND cl.jira_project = rsf.source_project
),

virtstrat_customers AS (
    SELECT DISTINCT issue_key, customer_mdm_pk
    FROM interestedparties_db.marts.fct_current_customer_links
    WHERE jira_project = 'VIRTSTRAT'
)

SELECT
    sc.virtstrat_issue_key,
    sc.virtstrat_summary,
    sc.virtstrat_status,
    sc.source_project,
    sc.source_issue_key,
    sc.source_summary,
    -- backward-compatible aliases for existing CSV → draft tooling
    sc.source_issue_key AS cnv_issue_key,
    sc.source_summary   AS cnv_summary,
    sc.customer_name,
    sc.customer_mdm_pk,
    sc.customer_link_context,
    sc.customer_linked_by
FROM source_customers sc
LEFT JOIN virtstrat_customers vc
  ON  vc.issue_key       = sc.virtstrat_issue_key
  AND vc.customer_mdm_pk = sc.customer_mdm_pk
WHERE vc.customer_mdm_pk IS NULL
ORDER BY sc.virtstrat_issue_key, sc.source_project, sc.customer_name;
