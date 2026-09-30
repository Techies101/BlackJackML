# Claude Design prompt: 21 Vision promo animation (Facebook Story)

Upload these files with the prompt:

- `ui/icons/21vision-master.svg` (or `21vision-512.png`): app logo
- `marketing/assets/main_basic.png`: Main screen, basic strategy advice (Hard 15 vs 10 → SURRENDER)
- `marketing/assets/main_deviation.png`: Main screen, deviation advice (RC +7, TC +2.3, bet ₱40, Hard 12 vs 3 → STAND)
- `marketing/assets/tab_deviations.png`: Deviations chart tab
- `marketing/assets/tab_spread.png`: Bet Spread calculator tab
- Optional: `main_idle.png`, `main_insurance.png`, `tab_basic.png`

Then paste everything below the line.

---

Create an animated vertical promo for a **Facebook Story**, built from the attached app screenshots and logo.

## Product

**21 Vision: AI Card Counter** is a Windows desktop app for live-dealer online blackjack. It watches the table on screen, uses AI to recognise each card, and keeps the Hi-Lo running count and true count. It also shows basic strategy, count-based deviations and a suggested bet (in Philippine pesos, ₱). The screenshots are the real app, rendered with example data.

## Format

- 1080 × 1920 (9:16), **15 seconds**, 30 fps. Export as MP4 if possible; otherwise an HTML animation I can screen-record.
- Keep all text and key UI inside the **safe area**: nothing important in the top 250 px or bottom 250 px, where Facebook shows the profile name and reply bar.
- No voice-over. Leave room for music I will add in Facebook; don't rely on sound.
- Every caption stays on screen for at least 1.5 s. Captions are short (max ~6 words), large and easy to read on a phone.

## Visual style: dark + neon, matching the app

| Token | Hex | Use |
|---|---|---|
| Background | `#07090C` | page background |
| Panel | `#0E1117` | cards and panels |
| Line | `#323B49` | borders |
| Text | `#E8ECF2` | main text |
| Neon green | `#3DFF8F` | positive count, bet, call to action, main glow |
| Magenta | `#FF3DD0` | deviations |
| Cyan | `#38D6FF` | selected buttons, highlights |
| Yellow | `#FFE24A` | counting zone, STAND |
| Red | `#FF4D6D` | negative count, red suits |

- Fonts: **Barlow Condensed** (bold) for headlines and numbers, **Barlow** for small text.
- Soft neon glows, a faint grid in the background, and slow drifting green/magenta light blobs.
- Motion: smooth ease-out slides, fades and scale-ups; glowing outlines that trace around the UI part being explained. Energetic but clean, no shaky or flashing effects.
- Show the screenshots crisp and large: crop and zoom into the relevant part instead of shrinking the whole window. Rounded corners (~18 px) and a thin border on each screenshot.

## Storyboard (15 s)

1. **0–2 s: Logo reveal.** The logo scales up with a neon green glow. "21 Vision" appears below it, then "AI CARD COUNTER" in green, wide letter spacing.
2. **2–5 s: "Counts every card, live".** Draw simple, generic playing cards (4♦, 6♣, 9♥; no casino table, no brand) dropping one by one into a glowing yellow "COUNTING ZONE" frame. Each card gets a pop-up tag: +1, +1, 0. A "RUNNING COUNT" number below ticks 0 → +1 → +2.
3. **5–8.5 s: "Live count, true count & bet".** `main_deviation.png` slides up, cropped from the title bar to the hand buttons. A glowing outline highlights the RUNNING / TRUE counts (+7, +2.3), then moves to the BET box (₱40). Sub-caption: "Bet suggestion from the true count".
4. **8.5–11.5 s: "Basic strategy + deviations".** Zoom into the dealer upcard / hand buttons and the advice panel. Start with `main_basic.png` (BASIC STRATEGY · SURRENDER), then cross-fade or flip to `main_deviation.png` (DEVIATION · STAND, magenta outline). Sub-caption in magenta: "Deviates when the true count says so".
5. **11.5–13.5 s: "Built-in charts & bet calculator".** A quick montage: the pair-splitting table from `tab_deviations.png` (the magenta 6+ / 5+ / 4+ badges visible), then the Bet Spread panel and results row from `tab_spread.png`. Slide in from opposite sides.
6. **13.5–15 s: End card.** Logo with glow, "21 Vision", "AI CARD COUNTER", a big green pill button: **"Message us to learn more"**. Small print below: **"21+ only · Play responsibly · Results are not guaranteed"**.

## Rules (must follow)

- Do **not** show or name any real casino, casino table footage, dealers, or casino logos.
- Do **not** promise or imply winnings or income ("win money", "beat the casino", "guaranteed profit", money raining, etc.). Describe features only.
- The "21+ only · Play responsibly" line must be readable on the end card.
- Don't change the numbers shown in the screenshots or invent new app features.

## Deliverables

1. The 15 s animation as described.
2. One still of the end card (1080 × 1920) to use as a thumbnail or a static post.
