# UI design spec (from the mockups of 2026-11-26)

What the interface should look like, as the owner approved it on 2026-11-26 from mockups of the
`ui-designer` proposals ([ui-proposals-2026-11-25.md](ui-proposals-2026-11-25.md), T1.10). The
mockups are a private design canvas of the owner's; this file is the record that travels with the
repo. T5.12 put it into the tickets: T5.2 (handed to its own PR), T5.3, T5.5, T5.13, T5.14, T5.15.

## Rules the design keeps

- Only Streamlit's own tools: `st.badge`, `:color[...]` and `:color-background[...]` Markdown,
  coloured Material Symbols in labels and widget icons, `st.info` / `st.success` / `st.warning`,
  `st.metric`, `st.progress`, `st.container(border=True)` and the theme options below, all checked
  in the installed 1.66.1. No CSS, no `unsafe_allow_html`, no `st.html` apart from the constant AI
  marker (`docs/LEGAL_COMPLIANCE.md` 3.4, `.claude/agents/ui-designer.md`).
- Generic patterns only (icon tiles, badges, status boxes, a journey timeline, large key figures, a
  progress bar, filter chips). No other app's look, colours, icons or layout, and no app named as a
  model (owner's rule of 2026-11-25; UrhG, DesignG and the EU design regulation, § 4 Nr. 3 UWG).
  These patterns are common and unoriginal, and the look comes from Streamlit's own components, so
  no copying-based right is touched. A registered design can be infringed without copying: if the
  app ever gets a distinctive look or logo of its own, the owner (or a lawyer) decides on a design
  and trademark search before a public launch (6.5).
- Calm and adult (1.1, 5.4): no mascot, no game-like rewards, no alarm colours. Colour is never the
  only signal: every badge and box has words.
- Yes and no weigh the same (4.2): Approve, "Run with my changes" and Reject are the same button type
  with a neutral border; no green Approve, no red Reject. Share and delete sit together.
- Only the fonts and Material Symbols inside Streamlit (6.4); nothing loaded from another host (3.4).

## Colour meanings

| Colour | Means | Examples |
|---|---|---|
| Blue | data leaves the app; journeys; neutral information | "Sends data to an outside service", way there and back, the bahn.de note, the link note |
| Green | stays inside the app; money that fits (every cost known); done | "Stays inside the app", "Within budget", "Shared with your rating." |
| Violet | the AI; the children | "AI-generated", "Child 1: 3-5 years", "Sent to the AI model with later questions" |
| Orange | the day trip | the trip box and the trip settings |
| Yellow | waiting or still unknown | "2 steps are waiting for you", "Within budget so far" |
| Gray | secondary facts | "Sources", the service name, testing settings |
| Accent | the app's own mark | the tab underline, the progress bar, "Kids" in the title |

## Palette (own picks, contrast computed with the WCAG 2.2 formula)

Theme options in `.streamlit/config.toml` (T5.15), set in `[theme.light]` and `[theme.dark]`.
Text needs 4.5:1, borders and other interface parts 3:1. The last column is the lowest contrast of
that colour on the backgrounds it is used on: for the first five rows the page and the secondary
background, for the palette its own background colour (it is higher on the page).

| Option | Light | Dark | Lowest contrast (light / dark) |
|---|---|---|---|
| `primaryColor` (accent) | `#B3470D` | `#F97316` | 5.14 / 6.02 (on the secondary background) |
| `backgroundColor` | `#FFFFFF` | `#0E1117` | |
| `secondaryBackgroundColor` | `#FFF6EE` | `#1A1D24` | |
| `textColor` | `#111418` | `#FAFAFA` | 17.30 / 16.16 |
| `linkColor` | `#1F5A99` | `#8AB8F0` | 6.60 / 8.19 |
| `borderColor` | `#7A7F8A` | `#8B909A` | 3.76 / 5.26 (3:1 needed) |
| `blueColor`, `blueTextColor` / `blueBackgroundColor` | `#1F5A99` / `#E3EEFB` | `#8AB8F0` / `#1B2A40` | 6.00 / 7.02 |
| `greenColor`, `greenTextColor` / `greenBackgroundColor` | `#1E6B3A` / `#E2F3E7` | `#7FD19A` / `#15301F` | 5.66 / 7.79 |
| `violetColor`, `violetTextColor` / `violetBackgroundColor` | `#6B3FA0` / `#EFE7F8` | `#C3A6F0` / `#2B2040` | 6.14 / 7.25 |
| `orangeColor`, `orangeTextColor` / `orangeBackgroundColor` | `#A64B00` / `#FDEBDD` | `#F5A15C` / `#3A2414` | 4.99 / 7.03 |
| `yellowColor`, `yellowTextColor` / `yellowBackgroundColor` | `#735500` / `#FFF3CC` | `#F0CF6A` / `#33290B` | 6.26 / 9.46 |
| `grayColor`, `grayTextColor` / `grayBackgroundColor` | `#4A4F59` / `#ECEEF1` | `#B8BDC7` / `#2A2D35` | 7.07 / 7.31 |

Six palette colours are set; red keeps Streamlit's default because the design uses no red. Each
`<colour>TextColor` is set to the same value as `<colour>Color`: otherwise Streamlit derives the
text colour of badges, `:color[...]` and the status boxes from it (15% darker in light, 15% lighter
in dark), a value nobody measured. White text on the dark accent is only 2.80:1, so the app uses no
`type="primary"` button (T5.2 makes all approval buttons secondary; T5.15 tests that none is left).
Also `linkUnderline = true` and `showWidgetBorder = true`; the old top-level `[theme] primaryColor`
is removed; `font` stays the bundled sans-serif; no `base` URL; `gatherUsageStats = false`.
How Streamlit picks the light or dark section (the device setting or its settings menu) and the
exact caption colour are measured in the running app (T5.15).

## Screens

- **Approval panel (T5.2, handed to PR #31):** a yellow box "N steps are waiting for you"; one bordered
  card per step with an icon tile, "Step n of m", a blue "Sends data to an outside service" or green
  "Stays inside the app" badge plus the service's name, a plain title from `PROGRESS_TOOL_LABELS`, the
  explanation, every argument as an editable field, the tool name as small plain text; an unknown
  cost shows a yellow badge holding only the fixed word "unknown", while its label (written by the
  model) stays plain text; the reject reason field, then the three equal buttons; the disabled chat
  box says "Answer the steps above first: approve, change or reject". A memory save
  (`remember_preference`, T5.11) never gets the green badge: what it saves goes to the AI model with
  later questions (2.11, 4.2), so it gets a violet "Sent to the AI model with later questions" badge
  next to the app's own "🧠 Save to memory: …" text.
- **Trip plan box (T5.3):** shown whenever a train, weather, ticket or budget tool ran (a turn with
  only the ticket comparison or the budget shows just those parts). A header saying the figures are
  calculated by the app, with an orange trip tile, the date, route and party, and the budget state from
  `src/budget.py`: green "Within budget" (every cost known), yellow "Within budget so far" (some costs
  still unknown; owner decision 2026-11-26) or gray "Over budget by €x" (never red); two journey cards
  (way there, way back) with large departure and arrival times; a weather card with the temperature
  range as a large figure and the Open-Meteo credit as a link right under it; a ticket card "Prices as
  of <checked_on>" with today's fare warnings; a budget section with three `st.metric` figures (known
  costs, budget, left) and an `st.progress` of known costs over the budget, capped at 100 % and left
  out when the budget is 0; the unknown costs as plain text (the labels are written by the model, so
  never a badge or Markdown; the mockup's yellow chips are an approximation); a blue `st.info` with the
  bahn.de and DB Navigator sentence.
- **Settings line and sidebar (T5.13, after T5.11):** under the AI notice, "Your next question uses"
  with badges built from fixed values only (country and city, each child's age group, day trip on or
  off, long-term memory on or off, approval mode) and "New conversation"; tab labels "Ask for ideas",
  "Browse places", "About and privacy"; the sidebar on the secondary background in the order Where,
  Children, Day trip by train, Long-term memory, Outside services, Settings for testing, each with a
  coloured icon in its heading.
- **Answer footer and feedback (T5.5, T5.14):** the violet "AI-generated" badge with the warning as
  body text; the answer; the app's box (with the weather credit next to the weather card); a gray
  "Sources" badge followed by the credits, the Open-Meteo credit as a link to open-meteo.com and to
  CC BY 4.0, the OpenStreetMap credit as a link to its copyright page; the link note in a blue
  `st.info` with a link icon, no ✅; "How this answer was made" with count badges; the feedback row as
  in T5.14.

## What Streamlit can only approximate

- Rounded icon tiles: a coloured Material Symbol on a `:color-background[...]` highlight.
- The vertical line of the journey timeline: needs CSS; the app shows the two times in large text
  with icons instead.
- A background colour per card: only `st.info` / `st.success` / `st.warning` boxes and the sidebar
  carry colour; other containers stay on the page background with a border.
