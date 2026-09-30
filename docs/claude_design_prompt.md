# Design brief: "21 Vision: AI Card Counter" live card-counting desktop app

## What you are designing

A Windows desktop tool that watches an online live-dealer blackjack game on screen, recognises the cards with a vision model, keeps the Hi-Lo card count, and advises the player what to do and how much to bet.

Please design **5 screens** (4 tabs of the main window plus a separate logs window), the **key states** listed below, and a small **style sheet** (colours, type scale, components). The result will be built in **Python with PySide6 (Qt Widgets)**, so keep everything implementable with standard widgets: flat surfaces, solid colours, simple borders, no blur, no translucency effects and no animations that matter to the layout.

## Attached references

- `Sample Expected User Screen.png`: how the user's screen is arranged (game in a large window; the app's main window on the right; a small logs window below it).
- `BJA_Basic_Strategy.jpg` and `BJA_S17.pdf`: the strategy charts the Basic Strategy and Deviations tabs must reproduce (layout, row/column order, colour key).
- `Betting Spread Reference/` (4 images): the bet spread calculator and "Variance Visualizer" the Bet Spread tab should follow.

## Who uses it and how

One player, sitting at the game for long sessions. The game window takes most of the screen; the app sits **always on top on the right side**, so the player glances at it between hands and keeps clicking in the game. It must be readable **at a glance**: the running count, true count, recommended bet and the current advice should be recognisable in under a second. **Theme: dark plus neon** (see Style direction).

## Window and layout constraints (fixed)

- Screen: 1920 × 1080. The main window is placed on the **right**; it may be partly off-screen but must never cover the game area.
- The main window contains an embedded **live feed of exactly 640 × 640 px**, shown 1:1 with **no title bar of its own**. In the Main tab the feed sits on the **right side** of the window; the controls panel is on the **left**. Extra items may also go **below** the feed.
- Suggested main window size: about **1100 × 760** (you may go larger, but keep the 640 × 640 feed at 1:1).
- Tabs across the top: **Main · Basic Strategy · Deviations · Bet Spread**. The live feed only appears in the Main tab.
- A thin status bar at the bottom of the main window: capture method, model, FPS (e.g. "dxcam · TensorRT fp32 · 32 FPS").
- **Program Logs window**: a separate, smaller always-on-top window (about 520 × 260) placed below the main window.

## Screen 1: Main tab

**Right:** the 640 × 640 live feed. The feed already draws its own overlays (card boxes coloured green = counted, orange = settling, grey = outside zone; a yellow counting-zone rectangle), so the frame around it should stay quiet.

**Left panel** (about 420 px wide), in order of importance:

1. **Counts** (the biggest numbers on screen)
   - Running count, e.g. **+7**
   - True count, e.g. **+2.3** (shown with one decimal; a small label under it shows the whole number used for decisions: "using +2")
2. **Recommended bet**, e.g. **$40 (4 units)**, with a small caption "Ramp 1–12 · base $10".
3. **Shoe**
   - Cards dealt / remaining, e.g. "154 dealt · 262 left" (of 416)
   - Decks remaining, e.g. "5.0 decks"
   - Penetration bar: progress toward the cut card, e.g. "49% of 75%", with the bar turning amber when close to the cut card.
   - Two small inputs: **Decks in shoe** (default 8) and **Decks behind cut card** (default 2; accepts decimals like 2.5).
4. **Hand input** (entered manually by the player)
   - **Dealer upcard**: a row of buttons **2 3 4 5 6 7 8 9 10 J Q K A**.
   - **Hand type**: a segmented control **Hard · Soft · Pair**.
   - **Player value**: a button grid that changes with the type:
     - Hard: 5 to 21
     - Soft: A,2 … A,9 (13 to 20)
     - Pair: 2,2 … 10,10 and A,A
   - A small "Clear" button.
5. **Advice card** (the result of the hand input)
   - Large action text, e.g. **STAND**, **HIT**, **DOUBLE**, **SPLIT**, **SURRENDER**.
   - For two-card-only actions, a fallback line: "Double (if not allowed: Hit)", "Surrender (if not allowed: Hit)".
   - A source badge: **BASIC STRATEGY** or **DEVIATION** (deviations must stand out clearly from basic strategy, e.g. an accent colour and the index shown: "Deviation · 12 vs 3 · TC ≥ +2").
   - When the dealer shows an Ace: an insurance line, "Insurance: TAKE (TC ≥ +3)" or "Insurance: don't take".
6. **Controls**: Start / Stop capture, **New shoe** (resets the count), **Undo last card**, and **−1 / +1** buttons to correct the running count after a misread card. Also a small "Cards counted: 154" and last-card readout, e.g. "Last: Q (−1) · YOLO + verifier agree".

## Screen 2: Basic Strategy tab

- Reproduce the attached **BJA_Basic_Strategy.jpg** as four tables **stacked vertically** in a scrollable view: **Pair Splitting**, **Soft Totals**, **Hard Totals**, **Late Surrender**, each with its colour key underneath.
- Columns: dealer upcard 2 3 4 5 6 7 8 9 10 A. Rows exactly as in the chart.
- Cell colours follow the chart's key: Split Y (green), Y/N split if DAS (teal), N (white); H (white), S (yellow), D (green), Ds (teal); SUR (green).
- Two cells differ from the JPG because this table is S17: **A,8 vs 6 = S** and **11 vs A = H**.
- The cell matching the hand currently entered on the Main tab is **highlighted** (e.g. a thick outline).
- A footer line: "Insurance or even money: don't take". Rules caption at the top: "8 decks · S17 · DAS · Late surrender".

## Screen 3: Deviations tab

- Same four-table layout, reproducing **BJA_S17.pdf**: basic strategy cells, with the **deviation indices shown in red** inside the affected cells (e.g. "4+", "0+", "−1−", "0−").
- Legend at the top, as in the PDF: "+ = at that true count and above", "− = at that true count and below", "0+ / 0− = any positive / negative running count".
- Footer: "Insurance or even money: take at +3".
- Highlight the current hand's cell, and additionally mark **active deviations** (index met at the current true count) differently from inactive ones, e.g. filled red badge vs outlined.

## Screen 4: Bet Spread tab

Follow the attached Blackjack Apprenticeship calculator closely (two columns of collapsible panels plus a results bar):

- **Player Settings**: Career / Trip toggle, Available bankroll, Rounds per hour, Unit amount, # of units, **Spread preset** dropdown (1–5, 1–8, 1–8 (2 spots), 1–10, 1–10 (2 spots), 1–12, 1–12 (2 spots), 1–20, 1–20 (2 spots)), Deviations (Standard / None).
- **Table Rules**: Number of decks, Penetration (e.g. "6 decks (312 cards · 75%)"), Dealer hits soft 17, Double after splitting, Resplitting aces, Splitting (max hands), Surrender.
- **Additional Settings**: ENHC, Double rule, Blackjack payout.
- **Bet Spread (ramp) table**: rows for true count **−3 … +7**, each with an editable bet value and a **1X / 2X** hands toggle; Reset button; "Freeze bets" switch. Negative indices in red, positive in green. The row matching the current live true count is highlighted.
- **Results bar** pinned at the bottom: **Expected value** ($/hr), **1 standard deviation** (± $/hr), **Risk of ruin** (%), **Hours 'til N-0**. Mark these as estimates (small "est." label).
- A **Variance Visualizer** button opening a chart view (as in the reference): inputs EV, Std. deviation, Hours, Bankroll, Players simulated, SD-lines toggle; line chart of bankroll over hours with the EV line, ±1 SD and ±2 SD bands and one or more simulated player paths; **Run sim** and **Return** buttons.

## Screen 5: Program Logs window

A compact, monospaced, scrolling log with coloured level tags, newest at the bottom, a Clear button and an auto-scroll toggle. Example lines:

```
[SYSTEM]  Screen capture: dxcam · Model: blackjack_model_v0.4.fp32.engine
[DECISION] ID 12 -> Q (HIGH -1) · YOLO: 8 (0.62) · Verifier: Q (0.94) · decided by VERIFIER
[SYSTEM]  ID 3 now shows a different card (8 -> Q); counting it as new
[WARNING] Main window overlaps the capture area
```

## Key states to show

1. Main tab, idle: capture stopped, no hand entered (advice card shows a friendly empty state).
2. Main tab, basic strategy advice: TC +0.4, hand Hard 15 vs 10 → **SURRENDER (if not allowed: Hit)**, badge BASIC STRATEGY.
3. Main tab, deviation advice: TC +2.3, hand Hard 12 vs 3 → **STAND**, badge DEVIATION "12 vs 3 · TC ≥ +2".
4. Main tab, dealer Ace with TC +3.4: insurance line **TAKE**.
5. Main tab, near the cut card: penetration bar amber, "New shoe soon".
6. Warning banner: "Main window overlaps the capture area; move it so the game is not covered."
7. Bet Spread tab with results, and the Variance Visualizer view.

## Sample data for the mockups

- Running count +7, true count +2.3 (using +2), 154 cards dealt of 416, 5.0 decks remaining, cut card 2 decks from the end (75%).
- Base bet $10, spread 1–12; ramp: TC ≤ +1 → $10, +2 → $40, +3 → $80, +4 and up → $120.
- Bankroll $10,000, 100 rounds per hour.

## Style direction

- **Theme colour: dark plus neon.** Near-black / deep charcoal backgrounds with bright neon accents (e.g. neon green, cyan, magenta, amber) for the key numbers, active states, borders and highlights. Neon glow should be suggested with solid bright colours and crisp outlines rather than blur effects (the app is built in Qt).
- Give each meaning its own neon colour and use it consistently: e.g. positive count / good for the player, negative count / bad, deviations, warnings, live/active capture.
- Keep text readable: neon for emphasis and numbers, not for long body text.
- Strategy table cells keep the BJA chart meanings (green = split/double, yellow = stand, teal = Ds or split if DAS, white/neutral = hit or no split), expressed as neon-tinted versions of those colours so the tables fit the theme and still read like the familiar charts.
- Clear hierarchy: counts and advice first, settings and controls second.
- Comfortable click targets for the upcard and value buttons (the player clicks them quickly between hands).
- Deliver a style sheet: colour tokens, type scale (including the large count numerals), button/segmented-control/toggle/input/table-cell styles.
