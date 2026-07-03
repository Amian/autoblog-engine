# Hero images — free-image (ChatGPT) with a mandatory review-and-regenerate loop

Blog hero cards are generated for FREE via the `anthropic-skills:free-image` skill
(ChatGPT web automation — zero API cost), then reviewed for quality and only accepted
if they are genuinely excellent. The deterministic `hero.py` template is the fallback
floor so the pipeline never blocks. All image config is under `images.ai` in
`autoblog.config.json`; honor `editorial.hardRules` in every prompt.

**Non-negotiable: every image is reviewed; anything short of excellent is regenerated.**

## 1. Build one prompt per new post

For each new post, write an image prompt that:
- depicts the post's actual subject/object (a real, specific photographic scene — the
  thing a reader is holding or looking at), NOT an abstract or text graphic;
- applies `images.ai.style` (the site's visual direction — medium, lighting, mood);
- ends with the aspect clause `wide 16:9 landscape composition, no text, no words,
  no lettering, no watermark`;
- appends every `images.ai.negative` term and every relevant `editorial.hardRules`
  visual rule as explicit exclusions (e.g. "no magnifying glass, no loupe").

Write the prompts as a JSON array to `tmp/image_prompts.json` **in publish-date order**
(so if generation is cut short, the near-term posts are covered), and keep a parallel
`tmp/image_slug_order.txt` (one slug per line, line N ↔ the Nth generated file).
Only include posts whose card file does not already exist (incremental / resumable).

## 2. Smoke-test the login, then generate

Invoke the `anthropic-skills:free-image` skill. Its `generate.js` reads the prompts
JSON and downloads PNGs to an output dir:
`node <free-image>/scripts/generate.js --prompts tmp/image_prompts.json --output tmp/img`

- **Smoke-test with ONE prompt first** into `tmp/img_smoke/` (~90s). If the log stalls
  before the first send, the ChatGPT login expired — the automation browser is visible;
  the run cannot proceed unattended. In that case skip to step 5 (template fallback for
  the whole batch) and note in the report that images need a logged-in ChatGPT session.
- ChatGPT rate-limits ~40 images per rolling window. A batch under ~35 posts is fine;
  if the tail fails with click-timeouts, that's the limit — cover it via fallback and
  note it (far-future posts can be upgraded next week).

## 3. Convert to cards

For each downloaded PNG, map it to its slug via `tmp/image_slug_order.txt` and convert:
`python3 $AUTOBLOG_ENGINE_DIR/scripts/to_card.py --config $AUTOBLOG_CONFIG --slug <slug> --src tmp/img/<n>.png`
This center-crops to the site's `images.size` and writes the post's frontmatter image path.

## 4. REVIEW every card — regenerate anything not excellent (mandatory)

For each card, **Read the JPEG** and judge it against this rubric. It PASSES only if
every line is true:
- **On-subject**: unmistakably depicts this post's specific object/topic — a reader
  would recognize it as the thing the article is about.
- **Photographic quality**: looks like a real, well-lit editorial photo — sharp,
  natural, good composition for a 1200×630 card (subject not awkwardly cropped or
  tiny); not cartoonish, plasticky, or obviously AI-melted.
- **No artifacts**: no garbled text/letters, no watermark, no distorted hands/faces,
  no duplicated or nonsensical objects.
- **No banned elements**: none of `images.ai.negative`; no `editorial.hardRules`
  violation (e.g. NO magnifying glass or loupe).
- **On-brand**: matches the `images.ai.style` mood.

If a card FAILS, regenerate it: rewrite its prompt to fix the specific defect
(e.g. "no magnifying glass" if one appeared, "single object, centered" if cluttered,
"sharp focus, realistic materials" if it looked fake), regenerate just that slug via
free-image, reconvert, and review again. Allow up to `images.ai.reviewMaxAttempts`
attempts per post. Curate — generate a spare and pick the best when a topic is
finicky. Never accept a merely-okay image; excellent or regenerate.

## 5. Fallback so the pipeline never blocks

For any post that, after `reviewMaxAttempts`, still has no excellent image — or if
free-image is unavailable/rate-limited — generate the deterministic template card so
the file exists and gates pass:
`python3 $AUTOBLOG_ENGINE_DIR/scripts/hero.py generate --config $AUTOBLOG_CONFIG --slug <slug>`
List every post that fell back in the run report, so the next run can retry a real image.

## 6. Verify + clean up

`python3 $AUTOBLOG_ENGINE_DIR/scripts/hero.py verify --config $AUTOBLOG_CONFIG` must pass
(every near-term post has an image). Remove `tmp/` image artifacts before committing;
commit only the final cards under the site's image dir.
