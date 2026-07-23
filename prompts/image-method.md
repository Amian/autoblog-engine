# Hero images — free-image (ChatGPT) with a mandatory review-and-regenerate loop

Blog hero cards are generated for FREE via the `anthropic-skills:free-image` skill
(ChatGPT web automation — zero API cost), then reviewed for quality and only accepted
if they are genuinely excellent. The deterministic `hero.py` template is the fallback
floor so the pipeline never blocks. All image config is under `images.ai` in
`autoblog.config.json`; honor `editorial.hardRules` in every prompt.

**Non-negotiable: every image is reviewed; anything short of excellent is regenerated.**

**Before generating: consider a real photo instead.** Some scenes — a shopper at a shelf,
hands operating a phone, a desk of real collectibles — are ones AI reliably renders wrong
or blank regardless of prompt craft. For those, `tools/source-photo.mjs` in the site's
monorepo pulls real, licensed stock photos (Pexels/Unsplash) to review and place instead
of generating. See `docs/BLOG-IMAGES.md` → "When to reach for a real photo instead of AI"
for the full method and the credit-rendering mechanics. Use AI for everything else.

## 1. Build one prompt per new post

For each new post, write an image prompt that:
- depicts the post's actual subject/object (a real, specific photographic scene — the
  thing a reader is holding or looking at), NOT an abstract or text graphic;
- applies `images.ai.style` (the site's visual direction — medium, lighting, mood);
- obeys the **printed-surface rule** below — this is the single most important part;
- ends with the aspect clause `wide 16:9 landscape composition, no watermark,
  no text overlay, no caption bar`;
- appends the **baseline negatives** below, then every `images.ai.negative` term, then
  every relevant `editorial.hardRules` visual rule, as explicit exclusions
  (e.g. "no magnifying glass, no loupe").

### Baseline negatives — append these to every prompt on every site

`images.ai.negative` in each site's config holds only that site's **content** bans
(subject matter it must never show). The craft negatives are shared and live here, so a
fix reaches all sites at once:

```
no blank or unprinted labels, no empty card faces, no plain unlabeled packaging,
no blank switched-off or grey screens, no blank signs or documents,
no flat colour placeholder panel, no title card, no collage or split panels,
no cloned repeated identical objects, no garbled or melted lettering,
no text overlay, no caption bar, no watermark, no cartoon, no illustration, no 3D render
```

Note what is deliberately **absent**: there is no `no text` / `no lettering` /
`no words` term. Those are what caused blank packaging and empty cards. We forbid
*garbled* lettering and *overlaid* graphic text; we do not forbid print existing on
printed things. Never add a blanket text ban to a site config — if a site needs one,
the composition is wrong instead (see the printed-surface rule).

**These are a checklist, not a literal suffix.** Our generator is ChatGPT's image tool
driven through the chat UI, not a diffusion API with negative conditioning. A long
tail of `no X, no Y, no Z…` hurts there in three ways: the model has no negative-prompt
channel so it reads them as prose, naming a thing makes it *more* likely to appear, and
a prompt that is mostly prohibitions can get answered with text instead of an image —
which the automation records as a generation failure.

So: **convert each relevant baseline negative into a positive clause about what IS in
frame, and carry at most three or four true exclusions at the end.** Aim for roughly
400–700 characters of confident descriptive prose.

- Instead of `no blank card faces` → "every card densely printed edge to edge with
  full-colour action photography and halftone ink texture"
- Instead of `no blank screen` → "the phone screen switched on and glowing warm"
- Instead of `no cloned identical objects` → "visibly varied, different colours,
  borders and wear"
- Instead of `no 3D render, no cartoon, no illustration` → "shot on 50mm, natural
  light, real materials"

Keep as explicit exclusions only the ones with no positive phrasing and real
consequence — typically real brand/certifier logos and the site's content bans
(e.g. ScanHalal's pork and alcohol list).

### The printed-surface rule (non-negotiable)

Most of our subjects — trading cards, food packaging, stamps, labels, certificates,
phone screens, documents — are **things that have printing on them**. If the prompt
tells the generator to avoid text, it renders the object with a *blank* face: a
trading card with no player on it, a milk carton with no label, a dead black phone
screen. This looks fake and cheap, and it silently contradicts the product ("we read
what's printed on your thing"). **A blank printed surface is worse than imperfect
print.** Never ask for a text-free version of an object that has text in real life.

Instead, compose so the surface reads as genuinely printed without needing legible
words. Pick whichever of these fits the shot:

- **Throw it out of focus.** Put the printed object off the focal plane — `shot at
  f/1.8, label soft and out of focus, only the texture of print visible`. Blurred
  print reads as completely real; sharp blank does not.
- **Angle it away.** `viewed at a steep oblique angle`, `edge-on`, `raking light
  across the surface` — foreshortening makes print unresolvable but present.
- **Occlude it.** A hand, a thumb, another card, packaging overlap, shadow falling
  across the label.
- **Crop it out.** Frame so the printed face is cut by the frame edge and the shot is
  carried by the material — foil sheen, card stock edges, perforations, gloss, the
  binder page, the shelf.
- **Show the back / the stack.** Card backs, spines, stacked edges, a fanned deck seen
  from the side, a sealed pack.
- **Let incidental print exist.** Small, unresolved, out-of-focus lettering elsewhere in
  the frame (a shelf tag, a distant aisle sign) is *desirable* — it is what makes a
  photograph look like a photograph. Only the focal subject needs to avoid legible words.

Say what you DO want, positively: `a densely printed vintage trading card, ink and
halftone texture clearly visible, held at an angle so the print is soft and
unresolvable`. Do NOT say `a blank card`, `an unlabeled package`, `no text`,
`no lettering`, or `plain white packaging`.

**Screens specifically:** a phone or laptop in frame must never be off or blank. Show
it `glowing warm, screen at a glancing angle so only colour and light are visible`,
or angled away from camera, or with the screen out of frame entirely.

**Honesty is preserved by identity, not by blankness.** The rule we care about is that
an AI image must never purport to be a *specific named real entity* — no AI "Penny
Black", no AI "1986 Fleer Jordan", no AI certification logo of a real certifier. A
generic, plausibly-printed, unbranded card or package breaks no honesty rule; a blank
one just looks broken. When the post is about a specific real entity, show the real
thing via `entityRefs` and keep the AI hero on mood.

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
every line is true.

**Gate 0 — the blank-surface check. Fail this and the image is rejected outright,
no matter how good it otherwise looks.** Reject if the frame contains any of:
- a **card, stamp, or ticket** whose face is empty, or carries only a plain frame,
  a bare silhouette, or an untouched cream/white panel where the subject would be;
- **packaging** (carton, box, pouch, bottle, jar, wrapper, can) with no label, or a
  label that is a solid unprinted block of colour;
- a **phone, tablet, or laptop screen** that is black, grey, white, or otherwise
  carries no interface — including a "scanning" shot where the screen is dead;
- a **blank sign, plaque, certificate, document, book cover, or page**;
- a plain colour field, gradient, or flat title-card standing in for a photograph.

This is the defect that has shipped most often and it is the one readers notice. An
unprinted object on a site about reading printed objects reads as broken. **If the
shot needs the surface to be blank in order to avoid text, the composition is wrong —
reshoot it per the printed-surface rule, don't accept it.**

Then the quality bar — every line must be true:
- **On-subject**: unmistakably depicts this post's specific object/topic — a reader
  would recognize it as the thing the article is about.
- **Right entity**: if the post names a real, specific place or object, the image must
  not depict a visibly *different* one. A generic mood shot is fine; a photorealistic
  shot of the wrong mountain under a named-mountain headline is not.
- **Photographic quality**: looks like a real, well-lit editorial photo — sharp,
  natural, good composition for a 1200×630 card (subject not awkwardly cropped or
  tiny); not cartoonish, plasticky, or obviously AI-melted.
- **Physically coherent**: real materials and geometry. No melted or smeared texture,
  no impossible reflections, no device bezels that don't close, no pasted-on window
  frames or split-panel collages, no light with no source.
- **No cloned objects**: rows of near-identical repeated items (five near-copies of the
  same peak, five identical cards) fail — real photographs have variation.
- **No artifacts**: no garbled or melted lettering, no watermark, no distorted hands or
  faces, no nonsensical objects.
- **No banned elements**: none of `images.ai.negative`; no `editorial.hardRules`
  violation (e.g. NO magnifying glass or loupe).
- **On-brand**: matches the `images.ai.style` mood.

If a card FAILS, regenerate it: rewrite its prompt to fix the specific defect, then
regenerate just that slug via free-image, reconvert, and review again. Fix by changing
the *composition*, not by adding more prohibitions — piling on negatives is what
produced the blank surfaces in the first place. Map the defect to the fix:

| defect seen | rewrite the prompt to… |
|---|---|
| blank card / label / packaging | re-frame per the printed-surface rule: oblique angle, shallow focus on the print texture, occluded by a hand, or cropped to the edge/stack |
| dead phone screen | `screen glowing warm, seen at a glancing angle`, or turn the device away / out of frame |
| flat title card, plain colour field | ask for a photograph explicitly: `editorial photograph, natural light, real materials` |
| melted / plasticky texture | name the material and the optics: `visible grain, worn edges, shot on 50mm, natural light` |
| cloned repeated objects | `a single subject`, or `varied, each one different, casually arranged` |
| impossible geometry / pasted frames | `a single continuous photograph, one camera, no collage` |
| wrong entity under a named headline | drop the name from the prompt and go generic-but-honest, or source the real thing via `entityRefs` |
| cluttered | `single object, centered, clean background` |

Allow up to `images.ai.reviewMaxAttempts` attempts per post. Curate — generate a spare
and pick the best when a topic is finicky. Never accept a merely-okay image; excellent
or regenerate.

## 5. Fallback so the pipeline never blocks

For any post that, after `reviewMaxAttempts`, still has no excellent image — or if
free-image is unavailable/rate-limited — generate the deterministic template card so
the file exists and gates pass:
`python3 $AUTOBLOG_ENGINE_DIR/scripts/hero.py generate --config $AUTOBLOG_CONFIG --slug <slug>`

**The template card is a build unblocker, not a shippable hero.** It is a flat colour
panel with the title typeset on it — as an `og:image` it is exactly the "blank card"
readers complain about, and it wastes the social-share and Discover value the hero
exists for. Therefore:

- A template card is only acceptable on a post whose publish date is **more than 7 days
  out**. A post going live inside the next week must have a real photographic hero, even
  if that means holding the post back a day and retrying generation.
- Every fallback goes in the run report under a **`NEEDS REAL HERO`** heading, listed by
  slug and publish date, so the next run retries it. Do not bury it in prose.
- If more than a third of the batch fell back, the batch has a systemic problem (expired
  ChatGPT login, rate limit, a style prompt that keeps producing rejects) — say so at the
  top of the report rather than shipping a wall of title cards.
- Never let a template card sit in production once free-image is working again. Retrying
  outstanding `NEEDS REAL HERO` slugs is the **first** step of the next run, before any
  new post's images.

## 6. Verify + clean up

`python3 $AUTOBLOG_ENGINE_DIR/scripts/hero.py verify --config $AUTOBLOG_CONFIG` must pass
(every near-term post has an image). Remove `tmp/` image artifacts before committing;
commit only the final cards under the site's image dir.
