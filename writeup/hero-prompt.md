# Hero image prompt — `harness-bench` v1.0

Drop the generated image at `writeup/hero.png` (or update the article reference if you save under a different name). Article currently expects PNG; JPG works fine if you want a smaller file — change the markdown reference accordingly.

---

## Concept

The article's thesis is **"sixteen harness strategies, one frozen model — most of the complexity is overhead."** Visual translation: a single model element at center; sixteen distinct "wiring" patterns radiating around it; one wire reaches the answer cleanly while the others coil into elaborate Rube-Goldberg loops that take much longer paths to the same destination.

This is a 16-harness update of the earlier `Rube-Goldberg-vs-ASK-ONCE-button` concept, scaled to reflect the post-Phase-8 library size.

## Prompt — DALL-E 3 / ChatGPT image tool

```
Editorial tech illustration for a software engineering article hero image.
1:1 square aspect ratio, 2048x2048 px, designed for both Medium hero (1500x1000
crop) and LinkedIn article preview (square thumbnail). Wired/The Verge magazine
aesthetic — flat vector style with subtle film grain, muted color palette, no
photorealism.

CENTER: a single matte-black hexagonal node, glossy and minimal, slightly
elevated above an off-white workbench surface. Inside the hexagon, a small
glowing pale-blue circle pulses softly. Label-free. This represents the frozen
language model.

CONNECTED TO THE NODE: exactly sixteen distinct routes radiating outward in
360 degrees, each one a clean copper-toned trace ending at a single small
brass solder pad on the far side of the frame. The same destination pad
appears for all sixteen routes — the destination, like the source, is one
shared point.

OF THE SIXTEEN ROUTES:

- ONE route (the hero, top-right at roughly 1 o'clock position) is a
  perfectly straight 1.5mm-wide copper line, slightly brighter than the
  others, with a clean direct path from the hexagon to the destination pad.
  No bends, no inline components, no detours. This is single_shot.
- THE OTHER FIFTEEN routes are progressively more elaborate as they radiate
  around the clock face. Each is 0.4mm wide, slightly oxidized copper.
  Distribute them roughly evenly so the composition reads as a clock face
  with the simple hero trace at 1 o'clock and the most elaborate routes at
  6, 7, 8, 9 o'clock positions. Examples of elaboration to vary across the
  fifteen:
  - Several have small visible 0402-package surface-mount components inline
    (resistors, capacitors).
  - A few coil into full loops that double back on themselves before
    continuing toward the pad — these represent retry/reflexion patterns.
  - Two or three split into branches that re-merge — these represent
    plan-execute and tree-of-thoughts.
  - One contains a small visible micro-IC chip with eight pins inline —
    represents multi-agent.
  - One ends in a faint X mark before the pad and never connects (it is
    drawn dimmer and slightly faded, in dusty grey rather than copper) —
    represents streaming_react excluded from the matrix.
  - At least three of the long elaborate routes have a small puff of
    light-grey smoke rising from one of their inline components, suggesting
    the route is straining.

BACKGROUND: a faint epoxy-green PCB-style grid at very low opacity, just
enough to ground the composition without distracting. Off-white border with
a 5% inset margin so the composition doesn't go edge-to-edge.

MATERIALS:
- Hexagonal node: matte-black plastic, soft anisotropic specular highlights
- Glowing inner circle: pale blue (#7CC4FF), low-radius bloom
- Hero copper trace: bright polished copper (#D89A3E)
- Other copper traces: oxidized copper (#B8802E)
- Excluded route: dusty grey (#9A9A9A) at 60% opacity
- Solder pad destination: tinned brass (#E8D8B0) with a single small
  specular highlight
- Background grid: epoxy-green (#006E40) at 8% opacity

LIGHTING: studio softbox from upper-left at 70deg elevation, no ambient fill,
slight rim highlight on the hexagonal node.

NEGATIVE SPACE: significant breathing room around all elements; the
composition should read at thumbnail size (300px square) without becoming
visually cluttered.

STRICT NO-TEXT DIRECTIVE: zero text, zero numbers larger than 1pt-equivalent,
zero labels, zero captions, zero arrows with words, zero title cards, zero
corner marks, zero watermarks, zero signatures. No part numbers on the
inline components — they are visual texture only.

Slight imperfection allowed (faint dust, sub-millimeter fingerprint near a
corner) to avoid sterile CGI look.
```

## Prompt — Midjourney v6 (fallback)

If DALL-E renders the routes too cleanly or adds unwanted text, swap to Midjourney with this condensed version:

```
editorial tech illustration, 1:1 square, Wired magazine style, flat vector
with subtle grain, off-white background --
center: matte black hexagonal node with a soft pale blue glow inside --
sixteen copper traces radiating outward to one brass solder pad on the far
side -- one trace at 1 o'clock is a clean straight bright bold line, the
other fifteen are progressively more elaborate: looping switchbacks, inline
0402 SMD components, branches that re-merge, a small 8-pin IC chip on one,
faint smoke rising from three of them -- one trace ends in a dusty grey X
short of the pad (excluded) -- epoxy-green PCB grid at 8% opacity background
-- copper #D89A3E hero, #B8802E others, glow #7CC4FF, pad #E8D8B0 --
no text no labels no numbers no watermark --
--ar 1:1 --s 250 --style raw
```

## What to do with the rendered image

1. Save as `writeup/hero.png` (or `.jpg` at higher quality if you want smaller file size — change the markdown reference accordingly).
2. The article currently does NOT reference a hero image in `article.md`. To add it, drop `![16-harness library hero](hero.png)` immediately under the H1 byline at line 23. The `scripts/build_medium_html.py` script will pick it up on the next regeneration.
3. For LinkedIn: the square 1:1 aspect ratio crops cleanly to LinkedIn's article header (1200x627 with center-crop) and to the round profile thumbnail.
4. For Medium: their hero auto-crops to ~3:2 — review the crop preview in their editor before publishing.
