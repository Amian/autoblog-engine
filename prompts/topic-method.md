# Topic research → publishing calendar (the method)

The calendar is where traffic is won or lost; everything downstream is mechanical.
The subject-matter territory comes from `editorial.archetypes` in the site config —
this file is only the method, and it applies to any site.

## What makes a topic worth a slot

Judge every candidate on both axes; want both, not either:
1. **Real search demand** — people type this into Google in meaningful volume.
2. **Funnel fit** — the reader's moment matches `editorial.funnel`. A reader in that
   moment is the conversion; volume without funnel fit is vanity traffic.

## Procedure

1. **Generate candidates per archetype**, honoring each archetype's `share` of the
   calendar. Use the archetype's `examples` as seeds for the *kind* of topic, not a
   literal list — expand along the same axis (the long tail within each archetype is
   the point).
2. **Cannibalization check (hard rule)**: for each candidate, scan every existing
   slug AND title for *intent* overlap, not string match. Two topics with different
   searcher intents both stay (and must cross-link); same intent in different words →
   drop the candidate. When related-but-distinct, the new post must take a clearly
   distinct angle and link to the sibling.
3. **Volume sanity**: if an SEO data tool is available in this environment, pull
   volumes and drop dead topics (<50/mo primary market) unless a strategic
   cluster-filler. If no tooling: prefer topics with obvious "people ask this
   constantly" energy (forum/Reddit perennials in the niche) — the archetypes were
   calibrated against real demand.
4. **SERP-gap recon (information gain)**: for the ~10 highest-stakes topics, web-search
   the priority keyword and skim what ranks. The must-cover bullets must guarantee the
   post covers what the top results cover PLUS at least one specific thing they handle
   badly or skip. A post that re-says the current #1 has no reason to outrank it.
   Record the gap being exploited in the calendar row so the writer targets it.
5. **Seasonality**: schedule seasonal topics `editorial.seasonalLeadWeeks` weeks
   before their search peak (indexing needs lead time). Never schedule a seasonal
   topic after its peak.
6. **Mix discipline**: ~`editorial.commercialPostsPerWeek` commercial/funnel posts per
   week, informational posts the rest; vary clusters day to day (no three consecutive
   posts from one cluster).
7. **Link assignment**: give each post 3–4 related-guide links chosen from posts that
   will already be live on its publish date (existing posts, or batch posts dated
   earlier). Spread links so new posts also receive some.
8. **Reserves**: pick 3 extra topics (same rules) as fact-check replacement backups.

## Output

One calendar row per post: `date | title | slug | priority_keyword | cluster |
search_intent | related links (3–4) | must-cover bullets (2–4)`. Titles are specific
and promise-true; slugs are lowercase-hyphenated, stable, and free of stop-word bloat.
