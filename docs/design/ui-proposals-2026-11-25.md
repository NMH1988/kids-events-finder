# UI proposals of the `ui-designer` agent, 2026-11-25

The full report of the T1.10 trial run (PR #37), kept as the agent wrote it, except that local paths
are now repo-relative. The owner chose proposals 1+2, 3, 5+7 and 6 for mockups; the design that
came out of them is in [ui-design-spec.md](ui-design-spec.md), and T5.12 turned it into tickets.
This report is the agent's first check, not legal advice; each ticket's own reviews decide.

---

## UI design proposal: whole app · Streamlit 1.66.1

**Summary:**
1. **Approval panel:** make Approve, "Run with my changes" and Reject look the same, and give each step a plain title that says what leaves the app. Today Approve is a filled primary button, which breaks rule 4.2.
2. **Settings line above the chat:** show country, city, children's age groups, trip mode and approval mode above the chat. On a phone the sidebar is hidden, so a parent can get answers for "Child 1, 3-5" without ever choosing it.
3. **Share tick under each answer:** lock it once the rating is saved, show whether the answer was shared, and put a delete button right there. Today, unticking after rating does not withdraw consent.

API source: this worktree has no `.venv`. I read the installed package in the main checkout's venv (`.venv/.../streamlit-1.66.1.dist-info/METADATA` says `Version: 1.66.1`, the same as the pin in `pyproject.toml:26`). "Confirmed" below means confirmed in that copy.

### Current interface

| Screen / panel | What the parent does | Main problems (`path:line`) |
|---|---|---|
| Header and tabs | Reads the 18+ / AI note, picks a tab | The tab label "Chat agent" is technical jargon (`app.py:20`). The sidebar starts hidden on a phone because `initial_sidebar_state` is unset, so it is "auto" (`app.py:10`). |
| Sidebar: where and who | Picks country, city, number of children, an age group per child | One child aged "3-5" is pre-selected (`views/sidebar.py:32`, `:38`). The parent may never see this choice, and it is sent with every question. Family settings and technical settings (model, RAG toggles) sit in one column (`:104-121`). |
| Sidebar: trip | Opens the expander, turns the trip on, enters budget, adults, Deutschlandticket holders | The toggle hides inside a collapsed expander (`:55-56`), so the parent has to find it twice. The chat does not say whether the trip is on. |
| Sidebar: agent settings | Model, auto-approve, RAG toggles, New conversation | "New conversation" also deletes data (2.7), but it sits last, under the testing switches (`:122`). The auto-approve label is technical (`:107`). |
| Chat start | Reads the AI notice, taps an example | The AI notice is correct (`views/chat.py:566-569`). Four examples sit in columns, one of them in Vietnamese, for parents in DE, GB and US (`:82-91`, `:575-580`). |
| Progress | Waits | Fine: the step labels are fixed (`views/chat.py:522-530`). |
| Approval panel | Approves, edits or rejects each step | Shows the raw tool name (`:411`). The 🌍 / 📚 emoji have no explanation, which is a screen-reader gap (`:411`). Arguments are raw JSON (`:423-429`; that is T5.2's scope). **Approve is `type="primary"`, Reject is secondary (`:447-462`): this breaks rule 4.2.** The chat box is disabled with no reason given (`:606`). |
| Answer | Reads it, the calculation box, the credits, the details | The AI label is a faded caption (`:585`), so its contrast is probably under 4.5:1 in the light theme (see Theme). The fare column is called "Checked" (`:227`), which reads as "the app checked this price". A ✅ next to "links come from tool results" (`:278-281`) reads as "verified". The credits caption has no "Sources" heading (`:268`). |
| Feedback | Ticks "share", rates 👍/👎 | The share label is about 60 words and repeats under every answer (`:304-311`). After a rating is saved, changing the tick does nothing (`:313-328`): unticking does not withdraw consent, and ticking later shares nothing. The delete button only appears at the end of the chat (`:600`). |
| Errors | Reads a warning | Every failure shows the same "Something went wrong…" (`:549-551`), which is T5.4's scope. The chat box has no `max_chars`, so the 1000-character limit only shows up after sending (`:606`, `src/agent/runner.py:62`). |
| Browse | Filters and reads cards | **The knowledge base description goes through `st.write`, which renders Markdown (`views/browse.py:34`), and the name sits in a Markdown heading (`:28`).** The rule says plain text. Raw values like "mixed", "paid" and "outdoor" (`:30-33`). The page does not say that the sidebar's city and age groups filter it (`:52`). |
| About | Reads | Technical pipeline terms (LangGraph, RRF) come before privacy (`views/about.py:18-33`). The content is complete, and "How results are ranked" is present (`:35`). |
| Theme | — | `primaryColor = "#f97316"` (`.streamlit/config.toml:8`) gives **2.80:1** against white, both for a white label on the button and for the focus ring and toggle on a white page (needed: 4.5 and 3). |

### Users and main tasks

Users are adult parents and carers in DE, GB and US, often on a phone, often in a hurry, sometimes with a child nearby.

1. **Ask for an outing** nearby (rainy day, free, this weekend) for the chosen age groups.
2. **Plan a day trip by regional train within a budget** (Germany only): turn the trip on, set the budget and the party, fill in the unknown costs.
3. **Decide on each outside step:** understand what will be sent and to whom, then approve, change or reject it.
4. **Read and trust the answer:** see what the AI wrote versus what the app calculated, follow official links, see sources, rate it, and share or delete.

### Design principles

1. Say what leaves the app, in plain words, at the moment it leaves.
2. Yes and no have equal weight: approve and reject, share and delete look and feel the same.
3. Facts and money come from the app's own boxes and are labelled that way. The AI's text is always labelled as AI.
4. The state stays visible: the parent always sees which family settings and which approval mode the next question uses.
5. Phone first: one column, full-width buttons, short labels. Details may fold away; consent text and AI notices never do.
6. Anything from outside the app (tool data, knowledge base) is shown as plain text.

### Theme

Contrast uses WCAG 2.2 relative luminance. Background values are Streamlit's defaults (white #FFFFFF, #F0F2F6, #0E1117, #262730). They live in the frontend bundle, which I could not confirm, so the proposal sets them explicitly and the ratios then hold for sure. Caption ratios assume Streamlit draws captions in 60% of the text colour. That is an assumption, not confirmed, and should be measured in the running app.

| Setting (`.streamlit/config.toml`) | Now | Proposed | Contrast (on which background) | Confirmed in 1.66.1 |
|---|---|---|---|---|
| `[theme] primaryColor` | `#f97316` | remove; set per theme below | now: white label 2.80 ✗; as a UI part on #FFFFFF 2.80 ✗, on #F0F2F6 2.50 ✗; on #0E1117 6.74 ✓, on #262730 5.29 ✓ | yes (`config.py:1495`) |
| `[theme.light] primaryColor` | — | `#B3470D` | white label 5.49 ✓; UI part / focus on #FFFFFF 5.49 ✓, on #F0F2F6 4.90 ✓ | section and option yes (`config.py:1450`, `:1495`) |
| `[theme.dark] primaryColor` | — | `#F97316` (kept) | on #0E1117 6.74 ✓, on #262730 5.29 ✓; a white label would be 2.80 ✗, so the app uses no `type="primary"` button (proposal 1 removes the only one) | yes (`:1455`) |
| `[theme.light] backgroundColor` / `secondaryBackgroundColor` | default | `#FFFFFF` / `#F0F2F6` (made explicit) | base for the ratios | yes (`:1510`, `:1525`) |
| `[theme.dark] backgroundColor` / `secondaryBackgroundColor` | default | `#0E1117` / `#262730` (made explicit) | base for the ratios | yes |
| `[theme.light] textColor` | default (#31333F) | `#111418` | body: 18.47 on #FFFFFF, 16.48 on #F0F2F6 ✓. Captions (assumed 60%): now 3.69 / 3.56 ✗, with this value 4.83 / 4.64 ✓ | yes (`:1540`); caption blend not confirmed |
| `[theme.dark] textColor` | default (#FAFAFA) | `#FAFAFA` (made explicit) | body 18.11 on #0E1117; caption (assumed) 6.96 ✓ | yes |
| `[theme.light] linkColor` | default `blueTextColor` | `#1F5A99` | 7.05 on #FFFFFF, 6.29 on #F0F2F6 ✓ | yes (`:2002`) |
| `[theme.dark] linkColor` | default | `#8AB8F0` | 9.17 on #0E1117, 7.20 on #262730 ✓ | yes |
| `[theme] linkUnderline` | default | `true` (links are not marked by colour alone, WCAG 1.4.1) | — | yes (`:2019`) |
| `[theme] showWidgetBorder` | default | `true` (a filled #F0F2F6 input on white is only 1.13:1) | see `borderColor` | yes (`:2568`) |
| `[theme.light] borderColor` | default | `#7A7F8A` | 4.02 on #FFFFFF, 3.58 on #F0F2F6 ✓ (≥3) | yes (`:2492`) |
| `[theme.dark] borderColor` | default | `#8B909A` | 5.90 on #0E1117, 4.63 on #262730 ✓ | yes |
| `font` | default sans-serif | unchanged (bundled Source Sans, OFL, 6.4) | — | yes (`:2067`) |
| `base` | unset | stays unset (it also accepts a remote URL, which 3.4 forbids) | — | yes (`:1475`) |
| `[browser] gatherUsageStats` | `false` | unchanged | — | yes (`config.py:1333`) |

The hex values are my own picks. They are not taken from any brand palette.

How Streamlit chooses between `[theme.light]` and `[theme.dark]` (device setting or the settings menu) is not confirmed in the Python package. Check it in the running app.

### Proposals

**1. Equal weight for Approve, Change and Reject** · ticket: T5.2 · effort S

**Problem:** Approve is `type="primary"` (filled, accent colour) while Reject is secondary (`views/chat.py:447-462`). That makes Approve brighter than Reject, which breaks 4.2. The coloured ✅ / ❌ emoji add a second colour signal on top.

**Proposal:** All three buttons are the same type, width and icon style, in the order Approve, change, Reject. Labels: "Approve", "Run with my changes", "Reject". The reject reason field stays visible directly above them.

**Wireframe:**
```
Reason if you reject (optional) [________________________]
[ ✓ Approve ]   [ ✎ Run with my changes ]   [ ✕ Reject ]   <- same look, same width
(on a phone: three full-width buttons stacked in this order)
```

**Streamlit:** `st.button(label, key=..., type="secondary", icon=":material/check:" | ":material/edit:" | ":material/close:", width="stretch")`, all confirmed (`button.py:139-153`, `:232`). `width="stretch"` replaces the old `use_container_width` parameter.

**Files:** `views/chat.py`, plus a test in `tests/test_app.py` that all three buttons have the same type.

**Legal check:** 4.2 (no dark pattern; saying no is as easy as saying yes). This conflicts with T5.2's note "Keep the three buttons' look as today" (see Questions).

**Copyright check:** own labels. Material Symbols used in a widget's `icon=` (bundled, Apache-2.0), never as the tab icon. Nothing loaded from another host.

**Security check:** button keys stay tied to the pause (`approval_panel_key`). The meaning of each decision is unchanged. No "approve all".

**2. Readable step cards in the approval panel** · ticket: T5.2 · effort S (on top of T5.2's form)

**Problem:** The card heading is the raw tool name, `find_nearby_places`, with an unexplained 🌍 / 📚 (`views/chat.py:411`). Neither tells the parent in words whether data leaves the app.

**Proposal:** Each card starts with a plain title from the fixed labels the app already has (`config.PROGRESS_TOOL_LABELS`). The second line says in words whether the step sends data outside the app. Then comes today's explanation (`TOOL_EXPLANATIONS`), then T5.2's fields with every argument. The raw tool name stays on the card as small plain text.

**Wireframe:**
```
🛑 The agent is waiting for you. Do you approve these steps?
┌───────────────────────────────────────────────────────────┐
│ Looking for places on OpenStreetMap                        │
│ 🌍 Sends data to an outside service                        │
│ Sends the city and a place category to OpenStreetMap ...   │
│ Town [Leipzig      ]  Country [Germany ▾]  Category [Park ▾]│
│ tool: find_nearby_places                                   │
└───────────────────────────────────────────────────────────┘
┌───────────────────────────────────────────────────────────┐
│ Adding up the budget                                       │
│ 📚 Stays inside the app                                    │
│ Budget (EUR) [60]   [ budget table, as today ]             │
└───────────────────────────────────────────────────────────┘
```

**Streamlit:** `st.text` (`text.py:32`) for the title, the data line and the tool name; `st.caption` for the explanation; `st.container(border=True)` (`layouts.py:118`). All confirmed.

**Files:** `views/chat.py`; the labels are reused from `src/config.py`.

**Legal check:** 2.6 (the same fields and the same `PlaceName` check through T5.2). 4.2 (neutral wording). Nothing new leaves the app.

**Copyright check:** own words. Emoji only.

**Security check:** every argument stays shown and editable before approval. Model-written names stay in plain text (`st.text`), never Markdown. `TOOLS_REQUIRING_APPROVAL` and `TOOLS_ALWAYS_REVIEWED` are untouched.

**3. Trip plan box: one place for the day** · ticket: T5.3 · effort M

**Problem:** Times and totals are spread between the model's text and a calculation box. The fare column is called "Checked" (`views/chat.py:227`). The budget summary is one dense `st.text` line (`:251-254`).

**Proposal:** One bordered box under the answer, titled "Your day trip, from the app's data", with sections in this order: way there, way back, weather, tickets, budget. The budget shows three plain figures. Costs that are still unknown are listed by name and never filled in. The fare date column becomes "Price as of".

**Wireframe:**
```
┌ Your day trip, from the app's data ─────────────────────────┐
│ Way there  Sat 14 Mar · Leipzig Hbf 08:12 → Halle 08:47     │
│            35 min · 0 changes · RE ... (plain text)          │
│ Way back   Sat 14 Mar · Halle 17:10 → Leipzig Hbf 17:46     │
│ Weather    Sat: cloudy, 4-9 °C, rain chance 30 %             │
│ Tickets    Option | Total (EUR) | Price as of                │
│ Budget     Known costs €34.00 | Budget €60.00 | Left €26.00  │
│            Still unknown: Entry fee, Food                    │
│ If a figure in the AI's text differs from this box, this box│
│ is right. Train times and fares can change: check bahn.de or│
│ the DB Navigator app before you travel.                      │
└─────────────────────────────────────────────────────────────┘
```
When the total is over budget, the third figure reads "Over budget €12.00". It uses no red delta or alarm colour.

**Streamlit:** `st.container(border=True)`, `st.text` for all service text, `st.dataframe` with `hide_index=True` (as today), and `st.metric(label, value, border=False)` with no `delta` (`metric.py:104-120`, confirmed).

**Files:** `src/agent/runner.py`, `views/chat.py`, `src/config.py`, as named in T5.3.

**Legal check:** 4.3 and 7.3 (figures only from tool results and code; unknown costs stay empty; points to bahn.de). 6.3 (the credits stay). 4.2 (no urgency colours).

**Copyright check:** own layout and words. The "DB Navigator" sentence is T5.3's approved wording and is a factual reference.

**Security check:** station, line and town names come from a service, so they are shown as plain text only (T5.3's test). The grounding check is untouched.

**4. Clear stop messages and a clear chat box** · ticket: T5.4 · effort S

**Problem:** There is one generic error (`views/chat.py:549-551`). Overlong questions only fail after sending (`src/agent/runner.py:62`). While the panel waits, the chat box is disabled with no reason (`views/chat.py:606`).

**Proposal:** Messages in my own words:
- Step limit: "This question needed more steps than the app allows. Try a narrower one, for example one town and one day."
- Timeout or connection error: "The AI service did not answer in time. Please try again in a moment."
- Anything else: today's text.

The chat box shows the limit (`max_chars=config.MAX_USER_MESSAGE_CHARS`). While a panel waits, its placeholder reads "Answer the steps above first: approve, change or reject".

**Wireframe:**
```
⚠️ The AI service did not answer in time. Please try again in a moment.
[ Answer the steps above first: approve, change or reject   (disabled) ]
```

**Streamlit:** `st.chat_input(placeholder, max_chars=..., disabled=...)` (`widgets/chat.py:564-579`) and `st.warning`, both confirmed.

**Files:** `src/agent/runner.py`, `views/chat.py`.

**Legal check:** 2.9 (the server-side limit in `check_input` stays; the box only shows it). 2.10 (no error text shown or logged).

**Copyright check:** own words.

**Security check:** no error text reaches the page. The approval gate and grounding are unchanged.

**5. Answer footer in a fixed order, with a "Sources" line** · ticket: T5.5 · effort S

**Problem:** The credits caption has no heading (`views/chat.py:268`). The ✅ in front of the link note reads as "verified" (`:278`). The AI label is a faded caption (`:585`).

**Proposal:** Every answer follows the same order:
1. The AI label, as normal body text (the constant `AI_LABEL`) with the hidden marker
2. The answer
3. The app's box (proposals 3 / 4)
4. "Sources: …", the app-set credits for the whole conversation (T5.5)
5. The link note with a neutral 🔗: "All 4 links come from tool results (official websites, maps, OpenStreetMap, Ticketmaster); check them before you go."
6. "How this answer was made"
7. Feedback

**Wireframe:**
```
🤖 AI-generated answer: it can be wrong; check the official websites.
<answer>
[ app box ]
Sources: Data © OpenStreetMap contributors, ODbL ... · Weather data by Open-Meteo.com ...
🔗 All 4 links come from tool results ... check them before you go.
▸ How this answer was made
[ feedback, proposal 7 ]
```

**Streamlit:** `st.markdown(AI_LABEL)` (a constant, plain Markdown), `st.html(AI_MARKER_HTML)` unchanged, `st.caption`, `st.expander`. All confirmed.

**Files:** `views/chat.py`; `tests/test_app.py` (tests at `:109`, `:136` look for the label in `at.caption`).

**Legal check:** 4.1 (the label gets stronger, the marker stays). 6.3 (credits are set by the app). The "only 'from <source>'" wording rule for links is kept.

**Copyright check:** own words; the attribution strings are the licensors' required credits, kept as they are.

**Security check:** `AI_MARKER_HTML` stays a constant and nothing dynamic goes into `st.html`. The grounding output is untouched.

**6. Settings line above the chat, and family settings grouped first** · ticket: new · effort S/M

**Problem:** On a phone the sidebar is hidden (`app.py:10`), so the parent cannot see the city, the pre-set "Child 1: 3-5", the trip mode or auto-approve. "New conversation", which deletes data, sits under the testing switches (`views/sidebar.py:122`).

**Proposal:**
- **Chat tab:** under the AI notice, a bordered line shows the settings that the next question will use, with a "New conversation" button beside it.
- **Sidebar order:** Where → Children → Day trip by train → Outside services, with the auto-approve toggle always visible and relabelled "Run outside searches without asking me" (still off by default) → a collapsed "Settings for testing" expander (model, multi-query, rerank).
- **Trip expander:** opens on its own when the trip is on.
- **Tab label:** "💬 Chat agent" becomes "💬 Ask for ideas".

**Wireframe:**
```
🤖 You are chatting with an AI assistant ... (st.info, unchanged, first)
┌──────────────────────────────────────────────────────────────┐
│ Germany · Berlin · Child 1: 3-5 years · Day trip: off         │
│ Outside searches: you approve each one   [ New conversation ] │
│ Change these in the sidebar (› at the top left on a phone).   │
└──────────────────────────────────────────────────────────────┘
SIDEBAR
 Where        Country [🇩🇪 Germany ▾]  City [All cities ▾]
 Children     How many? [- 1 +]  Child 1 [🧒 3-5 years ▾]
 ▾ 💶 Day trip by train (Germany)   [toggle] Plan within a budget ...
 Outside services
   [ off ] Run outside searches without asking me
 ▸ Settings for testing (model, search options)
```

**Streamlit:** `st.container(border=True, horizontal=True)` (`layouts.py:118-131`), `st.text`, `st.button(width="content")`, `st.expander(label, expanded=st.session_state.get("trip_on", False))` (`layouts.py:1203`), `st.toggle` (`checkbox.py:285`), `st.tabs`. All confirmed. Never use `bind="query-params"` on these widgets (`checkbox.py:82`): it would write age groups and the budget into the URL.

**Files:** `views/sidebar.py`, `views/chat.py`, `app.py` (tab label), `tests/test_app.py`.

**Legal check:**
- 1.2 / 1.3: only "Child N" and the fixed age-group labels.
- 2.1: nothing new is stored or sent; the summary shows what is already chosen.
- 2.7 / 2.8: deleting becomes easier.
- 4.1: the AI notice stays first.
- Security rule: the default of the auto-approve switch stays off.

**Copyright check:** own words and a generic layout. Emoji only.

**Security check:** auto-approve stays visible and off by default, so its state becomes more visible, not less. The summary shows only values from fixed choices, as plain text.

**7. Feedback row with an honest share state** · ticket: new · effort S

**Problem:** The long consent label is repeated under every answer (`views/chat.py:304-311`). The tick is read only when the rating is saved (`:313-328`), so changing it afterwards silently does nothing, and unticking looks like withdrawing consent when it is not. The delete button only appears at the end of the chat (`:600`).

**Proposal:** The share tick sits before the rating, is never pre-ticked, and has a shorter label that keeps the key facts visible. Once the rating is saved, the tick and the thumbs are locked. A plain line then says "Shared with your rating" plus an inline delete button, or "Not shared". The end-of-chat delete button stays.

**Wireframe:**
```
[ ] Share this question and answer with my rating. Kept on this app's
    server for 90 days to improve answers; you can delete it while this
    page is open. Leave this off if it mentions your family.
Was this answer helpful?  [👍] [👎]
-- after rating --
Shared with your rating.  [ 🗑️ Delete everything I shared ]
   (or)  Not shared. Only the rating and technical facts were saved.
```

**Streamlit:** `st.checkbox(label, value=False, disabled=...)` (`checkbox.py:68-78`), `st.feedback("thumbs", disabled=...)` (`feedback.py:109-119`), `st.button`, `st.text`. All confirmed.

**Files:** `views/chat.py`, `tests/test_app.py`.

**Legal check:**
- 2.2 / 2.8 / 4.2: withdrawing is as easy as giving and sits in the same place; no pre-tick; neutral wording.
- 2.7: 90 days, still stated.
- 1.2: the "leave it off" hint stays.

**Copyright check:** own words.

**Security check:** `save_feedback` and `delete_shared_feedback` are unchanged. The code-reviewer should confirm the lock logic.

**8. Browse cards as plain text, with readable labels** · ticket: new · effort S

**Problem:**
- The description is rendered as Markdown by `st.write` (`views/browse.py:34`), and the name sits in a Markdown heading (`:28`). Both break the plain-text rule for knowledge base text.
- Raw values like "mixed" and "paid" (`:30-33`).
- The page does not say that the sidebar's city and age groups filter it (`:52`).

**Proposal:** Each card shows a fixed category label, then the name, a details line and the description, all as plain text. Words are readable: "Free entry", "Entry fee", "Free and paid parts", "Indoor and outdoor". A line above the filters names the active sidebar filters.

**Wireframe:**
```
Places for families in Germany
Showing: Berlin and day trips from it · for Child 1: 3-5 years (change in the sidebar)
[Type of place ▾ All]   [Indoor or outdoor ▾ Both]
12 places · Opening times and prices change: check the website before you go.
┌──────────────────────────────┐
│ 🏛️ Museum                     │  fixed app label
│ <place name>                 │  st.text
│ Berlin · ages 3-14 · Indoor · Free entry
│ <description>                │  st.text
│ [🌐 Website]  [🗺️ Directions] │  links, nothing loads
└──────────────────────────────┘
```

**Streamlit:** `st.text` (`text.py:32`), `st.container(border=True)`, `st.link_button(width="stretch")` (`button.py:842-857`). All confirmed.

**Files:** `views/browse.py`, `tests/test_app.py` (`:16` checks the count caption).

**Legal check:** 3.4 (knowledge base text as plain text, links stay links). 5.3 (no ranking or sponsored look). 6.1 (own descriptions). 7.3 (price type only, no amounts).

**Copyright check:** own labels. Emoji only. No images.

**Security check:** this removes a Markdown path for knowledge base text. No raw HTML.

**9. Contrast-safe theme and readable required text** · ticket: new · effort S

**Problem:**
- The accent is 2.80:1 on white (`.streamlit/config.toml:8`).
- Inputs on the light theme have no border that meets 3:1.
- Captions, which carry the AI label, the credits and the price warnings, are probably under 4.5:1 in light mode.

**Proposal:**
- Apply the Theme table above.
- Keep required notices in body text (proposal 5).
- Optionally set `layout="centered"` so lines in the chat are shorter on a desktop. The trade-off is one card column in Browse.

**Wireframe:** no layout change. The same screens with a darker accent, underlined links and bordered inputs.

**Streamlit:**
- Confirmed in `config.py`: the `[theme.light]` and `[theme.dark]` sections and the options `primaryColor`, `backgroundColor`, `secondaryBackgroundColor`, `textColor`, `linkColor`, `linkUnderline`, `borderColor`, `showWidgetBorder`.
- Confirmed: `st.set_page_config(layout=...)` (`page_config.py:119-124`).
- Not confirmed: the caption colour blend and how Streamlit picks the light or dark section.

**Files:** `.streamlit/config.toml`, optionally `app.py`.

**Legal check:** 3.1 / 3.4 (no font URL, no remote `base`, `gatherUsageStats = false` kept). 6.4 (bundled fonts only). 1.1 (calm, adult look).

**Copyright check:** own colour values. No font, logo or image.

**Security check:** config only.

**10. About page in a parent-first order** · ticket: new · effort S

**Problem:** Pipeline terms (LangGraph, Reciprocal Rank Fusion) come first (`views/about.py:18-33`). A parent looking for privacy or limits has to scroll past them.

**Proposal:** Same text, new order:
1. Who this app is for
2. What the app does, in four plain lines (it searches its own list, asks you before outside searches, removes links no tool returned, does the money in code)
3. Privacy
4. How results are ranked
5. Limits
6. Data sources and licences
7. How it works (technical), kept in full for reviewers

All are visible headings, not folded away. The tab label becomes "ℹ️ About and privacy".

**Wireframe:**
```
### Who this app is for
### What the app does
### Privacy
### How results are ranked
### Limits
### Data sources and licences
### How it works (technical)
```

**Streamlit:** `st.markdown` with app-written text, as today; `st.tabs`. Both confirmed.

**Files:** `views/about.py`, `app.py`.

**Legal check:** 4.1, 5.3 (ranking stays reachable and visible), 6.3 (licences stay), 1.4 (the accessibility pointer to the venue's website stays), 2.3 (privacy is easier to find).

**Copyright check:** own words.

**Security check:** text only.

### Not possible within the rules
- **A map of places or of the train route:** `st.map` and `st.pydeck_chart` load map tiles from another host (3.4; the owner decision of 2026-11-25 says no embedded map).
- **Photos on Browse cards:** remote images (3.4), and the photos are not self-made (6.1). It would need an owner decision on assets.
- **A brand look** (custom font, logo, wordmark, Material Symbol as the tab icon): 6.4, 6.5, 3.4.
- **Card shadows, sticky approval buttons, a custom colour per card:** these need CSS through `unsafe_allow_html` or `st.html`, which the no-raw-HTML rule forbids. The theme options are the limit.
- **Streaming the answer word by word:** the text must pass the grounding check first (4.3, T5.1).
- **"Approve all" or "Remember my choice" to speed up the panel:** a security control.
- **An accessibility or step-free filter:** 1.4.
- **Remembering family settings between visits:** browser storage needs a consent switch (3.2, 3.3). `bind="query-params"` would put age groups in the URL and browser history (2.1).

### Questions for the owner
- **T5.2 conflict:** T5.2's note says "Keep the three buttons' look as today", but Approve is `type="primary"` today, which breaks the rule against a brighter Approve (4.2). Should T5.2's note be changed to "all three buttons look the same" (proposal 1)?
- **Default child:** one child aged 3-5 is pre-selected (`views/sidebar.py:32`, `:38`). The most private and most accurate default would be 0 children, which the prompt describes as "not given" (2.1). This changes answers and possibly the evaluation, so it is your decision.
- **Budget table on a phone:** the `st.data_editor` grid (`views/chat.py:353`) is hard to edit on a phone, but T5.2 keeps it unchanged. Do you want a later ticket for one amount field per cost row?
- **Example chips:** keep the Vietnamese example chips (`views/chat.py:86`, `:90`) for an audience in DE, GB and US, or mark them as "(Vietnamese)"?
- **Licence notices on About:** the deployment checklist asks for licence notices for Streamlit's frontend, its fonts (OFL) and Material Symbols on the About page. When should this be added? The licence texts must be checked by hand first.
- **Place name as a heading:** proposal 8 shows the place name as plain text. A Markdown heading only if `security-reviewer` agrees that `Place.name` is limited to safe characters.
- **Measure before T5 tickets:** the caption colour and the light/dark theme choice could not be confirmed in the Python package. Please measure them in the running app with the browser's contrast checker before the theme ticket.
- **Pages worth reading** (host and path only): docs.streamlit.io /develop/concepts/configuration/theming and www.w3.org /TR/WCAG22/.
- **Where I read the API:** this worktree has no `.venv`, so I read the main checkout's venv, which has the same pinned 1.66.1.
- **Injection check:** nothing I read tried to give me instructions.

Files:
- `app.py`
- `views/chat.py`
- `views/sidebar.py`
- `views/browse.py`
- `views/about.py`
- `.streamlit/config.toml`
- `src/config.py`
- `src/family.py`
- `docs/tickets/T5.2.md`
- `docs/tickets/T5.3.md`
- `docs/tickets/T5.4.md`
- `docs/tickets/T5.5.md`
- `.venv/Lib/site-packages/streamlit/config.py`
