-- ============================================================
-- Customer GAPS on VIRTSTRAT Features
-- Customers linked to CNV issues NOT yet on the linked VIRTSTRAT Feature
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
--   - CNV default: Feature Request only (issuetype 10111). Drop the
--     AND cnv.issuetype = 10111 filter for all CNV issue types.
--   - Link types: ALL link types between CNV and VIRTSTRAT (both directions)
--   - Gap detection: per customer_mdm_pk anti-join (not per issue)
--   - DISTINCT on core keys to collapse bidirectional link duplicates
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

related_cnv_issues AS (
    SELECT DISTINCT
        vs.virtstrat_issue_key, vs.virtstrat_summary, vs.virtstrat_status,
        cnv.issue_key AS cnv_issue_key, cnv.summary AS cnv_summary
    FROM virtstrat_features vs
    JOIN jira_db.cloudrhai_marts.jira_issuelink_rhai il ON il.destination = vs.id
    JOIN jira_db.cloudrhai_marts.jira_issue_non_pii cnv ON cnv.id = il.source
    WHERE cnv.project = 'CNV'
      AND cnv.issuetype = 10111  -- Feature Request

    UNION

    SELECT DISTINCT
        vs.virtstrat_issue_key, vs.virtstrat_summary, vs.virtstrat_status,
        cnv.issue_key AS cnv_issue_key, cnv.summary AS cnv_summary
    FROM virtstrat_features vs
    JOIN jira_db.cloudrhai_marts.jira_issuelink_rhai il ON il.source = vs.id
    JOIN jira_db.cloudrhai_marts.jira_issue_non_pii cnv ON cnv.id = il.destination
    WHERE cnv.project = 'CNV'
      AND cnv.issuetype = 10111  -- Feature Request
),

cnv_customers AS (
    SELECT DISTINCT
        rci.virtstrat_issue_key, rci.virtstrat_summary, rci.virtstrat_status,
        rci.cnv_issue_key, rci.cnv_summary,
        cl.customer_mdm_pk, cl.customer_name,
        cl.link_context    AS customer_link_context,
        cl.linked_by_email AS customer_linked_by
    FROM related_cnv_issues rci
    JOIN interestedparties_db.marts.fct_current_customer_links cl
      ON cl.issue_key    = rci.cnv_issue_key
     AND cl.jira_project = 'CNV'
),

virtstrat_customers AS (
    SELECT DISTINCT issue_key, customer_mdm_pk
    FROM interestedparties_db.marts.fct_current_customer_links
    WHERE jira_project = 'VIRTSTRAT'
)

SELECT
    cc.virtstrat_issue_key,
    cc.virtstrat_summary,
    cc.virtstrat_status,
    cc.cnv_issue_key,
    cc.cnv_summary,
    cc.customer_name,
    cc.customer_mdm_pk,
    cc.customer_link_context,
    cc.customer_linked_by
FROM cnv_customers cc
LEFT JOIN virtstrat_customers vc
  ON  vc.issue_key       = cc.virtstrat_issue_key
  AND vc.customer_mdm_pk = cc.customer_mdm_pk
WHERE vc.customer_mdm_pk IS NULL
ORDER BY cc.virtstrat_issue_key, cc.customer_name;
