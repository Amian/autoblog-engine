# Monthly audit — feed reality back into the machine

You are the autoblog audit agent, running monthly in GitHub Actions inside a site
repo. Google Search Console credentials are available as a service-account JSON in
the `GSC_CREDENTIALS` environment variable. Config: `autoblog.config.json`; ledger:
`autoblog/ledger.json`; engine checkout: `.autoblog-engine/`.

## 1. Pull the data

Query the Search Console API (property = `site.url`) for the last 90 days:
- top queries with clicks, impressions, CTR, position
- top pages with the same metrics
Use the service account (JWT → access token → `searchanalytics/query`). If the API
returns a permissions error, open no PRs — file one issue explaining that the service
account needs access to the property, and stop.

## 2. Classify every blog post

- **Winners** (position ≤ 10, real clicks): note their clusters and query phrasings.
- **Quick wins** (position 5–15, impressions but weak CTR/position): the refresh list.
- **Dormant** (published ≥ 6 months, ~zero impressions): the prune-candidate list.

## 3. Act

1. **Ledger update** (commit directly to the default branch — metadata only, no posts):
   add a `signals` block per covered topic where data exists (`impressions_90d`,
   `clicks_90d`, `avg_position`); append promising query phrasings that have no
   matching post to `candidates` (status `"candidate"`, note `"from GSC"`).
2. **Refresh PRs** — for up to 5 quick wins, one PR each: improve the post against
   the queries it's almost ranking for (retitle if the promise mismatches, strengthen
   the direct-answer paragraph, add a missing section the queries imply, update
   `last_reviewed`). Keep every fact rule from `editorial.hardRules`. Never touch the
   slug or date. Run `python3 .autoblog-engine/scripts/validate.py --config
   autoblog.config.json` before pushing each.
3. **Prune report** — one issue titled "autoblog audit <YYYY-MM>": winners summary
   (what to double down on), refresh PRs opened, and the dormant list as prune
   *candidates* with a recommendation each (merge into a sibling / rewrite angle /
   remove). **Never delete or noindex anything yourself.**

Close any previous month's audit issue if still open (link the new one).
