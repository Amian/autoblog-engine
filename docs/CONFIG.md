# `autoblog.config.json` reference

Lives at the site repo root. Validated against `schema/autoblog.config.schema.json`
in the gates workflow. Every field the engine knows about is listed here; unknown
fields are rejected (typos should fail loudly).

```jsonc
{
  "version": 1,

  "site": {
    "name": "Antique Identifier",          // brand name used in prompts + hero images
    "url": "https://identifyantiques.app", // canonical origin, no trailing slash
    "language": "en"
  },

  // Which stack adapter shapes paths/builds. jekyll | astro-content | plain-md
  "adapter": "jekyll",

  "content": {
    "dir": "_posts",                        // where posts live, repo-relative
    "filenamePattern": "{date}-{slug}.md",  // {date} = YYYY-MM-DD; or "{slug}.md" (date in frontmatter)
    "urlPattern": "/blog/{slug}/",          // public URL shape for a post
    "frontmatter": {
      "required": ["layout", "title", "date", "slug", "image", "description",
                   "categories", "tags", "priority_keyword", "search_intent",
                   "cluster", "cta_type", "draft_source", "review_state"],
      "constant": { "layout": "blog_post" },// fields that must equal these values
      "dateField": "date",                  // frontmatter field holding the publish date
      "clusterField": "cluster",
      "descriptionMaxChars": 160
    },
    "ctaSnippet": "{% include cta-antique-identifier.html %}", // must be present; marks a complete file
    "clustersFile": "_data/content_clusters.yml" // JSON(-style) file with {"clusters": {...}}; optional
  },

  "editorial": {
    "audience": "who reads this blog and what moment they're in",
    "funnel": "why a reader converts to the app — the moment the app sells itself",
    "voice": "tone + style rules for writers",
    "archetypes": [                         // topic families; ranked examples live here, not in the engine
      { "name": "brand-marks", "description": "…", "examples": ["…"], "share": 0.4 }
    ],
    "commercialPostsPerWeek": 1,            // funnel/commercial posts per week; rest informational
    "seasonalLeadWeeks": [6, 10],           // schedule seasonal topics this many weeks before peak
    "wordCount": { "min": 1200, "target": 1800 },
    "bannedPhrases": ["in today's fast-paced world", "delve into"], // case-insensitive, body text
    "hardRules": ["never depict a magnifying glass or loupe in imagery"] // injected verbatim into prompts
  },

  "cadence": {
    "postsPerDayMax": 1,                    // hard cap; gates enforce
    "batchTargetDays": 21,                  // days of queue a refill aims to add
    "refillThresholdDays": 21               // refill runs only when runway drops below this
  },

  "quality": {
    "minRunwayDays": 7,                     // watchdog alarm threshold
    "dupContainmentThreshold": 0.5,         // shingle containment above this = duplicate (gates fail)
    "factCheck": true                       // run P4 fact-check phase
  },

  "images": {
    "mode": "template",                     // template (deterministic hero) | off
    "brandColors": ["#1f2937", "#b45309"],  // [background, accent]
    "textColor": "#f8f5ee",
    "size": [1200, 630],
    "fontPath": "",                         // optional TTF path; auto-discovers system fonts if empty
    "verifyWithinDays": 14                  // gates: posts publishing within N days must have an image
  },

  "autonomy": { "merge": "review" },        // review | auto — the training-wheels flag

  "models": { "writer": "best", "checker": "best" }, // "best" = most capable available; never downgrade

  "build": {
    "command": "bundle exec jekyll build --future --destination tmp/_site_future",
    "distDir": "tmp/_site_future",
    "setup": "ruby-bundler",                // ruby-bundler | node-pnpm | none — CI toolchain to install
    "rubyVersion": "3.3",                   // used by setup: ruby-bundler (default 3.3)
    "nodeVersion": "22"                     // used by setup: node-pnpm (default 22)
  },

  "audit": { "gsc": "auto" }                // auto = use GSC if GSC_CREDENTIALS secret exists, else skip
}
```

## Field notes

- **`editorial.archetypes`** is where the subject-matter expertise lives. The engine's
  `prompts/topic-method.md` supplies the *method* (ranking, cannibalization checks,
  SERP-gap recon, seasonal lead); the archetypes supply the *territory*. Write them
  richly — they're the difference between year-two topics that compound and topics
  that wander. `share` values should roughly sum to 1 and steer calendar balance.
- **`content.ctaSnippet`** doubles as the completeness marker: writers end every post
  with it, and validation treats a file without it as incomplete/truncated.
- **`quality.dupContainmentThreshold`** uses shingle *containment*
  (|A∩B| / min(|A|,|B|)) rather than Jaccard, so a short post copied into a long one
  still scores high. Calibrated so an existing healthy corpus passes.
- **`models`**: "best" is a policy, not a model id — the refill prompt instructs the
  agent to use the most capable model its Agent tool offers and to stop (not
  downgrade) if usage limits hit mid-batch.
- **Secrets are never in this file.** They live in the site repo's Actions secrets:
  `CLAUDE_CODE_OAUTH_TOKEN` (required), `CLOUDFLARE_DEPLOY_HOOK` (if using
  `publish.yml`), `GSC_CREDENTIALS` (optional, enables the audit).
