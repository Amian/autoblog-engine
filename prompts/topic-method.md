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
   the point). Generate **~1.5–2× more candidates than slots** — step 3's keyword
   data is what prunes the pool, and it can only pick winners if there is a pool.
2. **Cannibalization check (hard rule)**: for each candidate, scan every existing
   slug AND title for *intent* overlap, not string match. Two topics with different
   searcher intents both stay (and must cross-link); same intent in different words →
   drop the candidate. When related-but-distinct, the new post must take a clearly
   distinct angle and link to the sibling.
3. **Volume + difficulty reality check (DataForSEO)**: write every surviving
   candidate's priority keyword to `tmp/candidates.txt` (one per line) and run
   ```sh
   python3 $AUTOBLOG_ENGINE_DIR/scripts/keywords.py vet \
     --keywords-file tmp/candidates.txt --config $AUTOBLOG_CONFIG --out tmp/keywords.json
   ```
   One batched run costs pennies; results are cached in `autoblog/keywords-cache.json`
   (committed), so repeat keywords across refills are free. Use the data to pick the
   calendar, not to pad it:
   - Drop `dead` (<10/mo) and demote `thin` (<`--min-volume`, default 50/mo) — keep a
     thin topic only as a deliberate cluster-filler and say so in its calendar row.
   - When two candidates compete for a slot, prefer **volume high × difficulty (kd)
     low**; a kd ≥ 70 topic needs a strong information-gain angle (step 4) to earn
     its slot.
   - `intent` sanity: a `commercial`/`transactional` keyword on an informational
     archetype (or vice versa) usually means the *keyword phrasing* is wrong, not
     the topic — rephrase toward what searchers type.
   - `no-data` keywords aren't dead: very-long-tail can still be right when funnel
     fit is strong. Judge those on the heuristic below.
   - **If the script prints `SKIPPED`** (no credentials, unverified account, empty
     balance): fall back to the heuristic — prefer topics with obvious "people ask
     this constantly" energy (forum/Reddit perennials in the niche) — and write
     `keyword data: heuristic (<reason>)` in the calendar header so reviewers know
     the volumes are guesses. Never block a refill on missing keyword data.
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
6b. **Date spacing**: honor `cadence.postsPerWeek`. Below 7/week, spread each week's
   posts evenly (3/week → Mon/Wed/Fri; 2/week → Tue/Fri) — a steady drip, never a
   burst. Fewer, better-differentiated posts beat a daily flood: every slot must
   still pass the two-axis test, and a slot with no strong topic is dropped, not
   filled.
7. **Link assignment**: give each post 3–4 related-guide links chosen from posts that
   will already be live on its publish date (existing posts, or batch posts dated
   earlier). Spread links so new posts also receive some.
8. **Reserves**: pick 3 extra topics (same rules) as fact-check replacement backups.

## Output

One calendar row per post: `date | title | slug | priority_keyword | volume | kd |
cluster | search_intent | related links (3–4) | must-cover bullets (2–4)`. `volume`
and `kd` come from step 3 (`-` when the run was heuristic or the keyword had
no data). Titles are specific and promise-true; slugs are lowercase-hyphenated,
stable, and free of stop-word bloat.
