# Style Transfer — Complete History

All styles ever tried across all generation methods, with acceptance rates.

## Current Pipeline: `smart_style` (genimages, Imagen 3)

| Style | Accept | Reject | Total | Rate | Status |
|-------|--------|--------|-------|------|--------|
| Sumi-e Ink Wash | 4 | 1 | 5 | **80%** | Active |
| Bold Black Ink | 5 | 2 | 7 | **71%** | Retired (was test) |
| Gonzo / Steadman | 43 | 48 | 91 | **47%** | Active |
| Batman TAS / Dark DC | 24 | 30 | 54 | **44%** | Active |
| French Impressionist | 5 | 11 | 16 | 31% | Retired (was test) |
| Transform (generic) | 17 | 47 | 86 | 27% | Retired |
| Archer TV | 4 | 14 | 18 | 22% | Active |
| Ukiyo-e Woodblock | 8 | 34 | 42 | 19% | Active |
| Editorial Illustration | 4 | 19 | 23 | 17% | Retired (was test) |
| Pixar 3D | 2 | 18 | 20 | 10% | Active |
| Watercolor | 1 | 26 | 27 | 4% | Retired |
| Studio Ghibli | 0 | 7 | 7 | 0% | Active |
| Moebius / Ligne Claire | 0 | 6 | 6 | 0% | Active |
| Marvel Comic | 1 | 0 | 1 | 100% | Active (too few samples) |

Active config has 10 styles: archer, batman, marvel, gonzo, sumie, ukiyoe, moebius, pixar, ghibli, shinkai (untested).

## Legacy: `style_transfer` (older Imagen prompts)

| Style | Accept | Reject | Total | Rate |
|-------|--------|--------|-------|------|
| Hugo Pratt Ink | 8 | 4 | 12 | **67%** |
| Bold Ink | 16 | 13 | 29 | **55%** |
| Oil Painting | 2 | 2 | 4 | 50% |
| Sumi-e / Ink Wash | 2 | 0 | 2 | 100% |
| Visible Brushstrokes | 12 | 29 | 41 | 29% |
| Linocut / Woodblock | 9 | 24 | 33 | 27% |
| Watercolor | 7 | 19 | 26 | 27% |
| Charcoal / Sketch | 5 | 15 | 20 | 25% |
| Crosshatching | 23 | 79 | 102 | 23% |
| Realistic Anatomy | 17 | 60 | 77 | 22% |
| Rubber Hose Animation | 12 | 57 | 69 | 17% |

## Legacy: `cartoon` / `gemma_cartoon` (Imagen)

| Style | Accept | Reject | Total | Rate |
|-------|--------|--------|-------|------|
| gemma_cartoon: Pixar | 12 | 2 | 14 | 86% |
| gemma_cartoon: Watercolor | 43 | 22 | 65 | 66% |
| gemma_cartoon: Studio Ghibli | 20 | 15 | 35 | 57% |
| cartoon: (generic) | 30 | 44 | 74 | 41% |

## Taste Profile (learned from 1,085 reviews)

**Strong accept:** Bold ink, sumi-e, gonzo splatter, noir/batman, Hugo Pratt
**Moderate accept:** French impressionist, archer, crosshatching
**Reject:** Watercolor (smart_style), ghibli (smart_style), moebius, pixar, rubber hose

Pattern: Prefers **bold, high-contrast, graphic** styles with strong linework.
Dislikes: Soft, pastel, dreamy styles and 3D renders.

## Gemma Recommendations (for reference)

Gemma overwhelmingly suggests watercolor (60%) and ghibli (32%), which are the *worst* performers in smart_style. The cartoon_style field is not useful for style selection.
