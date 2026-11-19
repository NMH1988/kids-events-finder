# Legal compliance rules (mandatory)

**Read this file before starting any ticket.** Every change must respect these rules. If a ticket
would break a rule, or it is unclear whether it does, **stop and ask the owner** before writing code.
Never ship a change "to check later".

> These rules are the project's own compliance baseline for Germany and the EU, based on research
> done in November 2026. They are not legal advice. Before the app is opened to the public or earns
> money, the owner has it reviewed by a lawyer or data protection consultant (Datenschutzberater),
> and this file is updated with the result.

## How to use this file
1. Before a ticket: read the whole file and note which sections the change touches.
2. While working: follow the rules; when a rule needs a decision that is not written here, ask.
3. In the pull request: fill in the **Legal check** section of the PR template (which rules apply,
   how the change follows them). A PR without it is not merged.
4. When a new data source, service, data flow or feature with legal impact is added, update this
   file and the registers at the end in the same PR.

---

## 1. Children's data (GDPR, Recital 38)
The users are parents, but the app handles data about children, who are specially protected.

- **1.1 Adults only.** The app is for parents and carers aged 18+. It is designed and promoted for
  adults, never directly for children (keeps the app outside Art. 8 GDPR). The terms state 18+.
- **1.2 No names.** Never ask for, store or send a child's name, school, photo or address.
  Children are only "Child 1", "Child 2" (by position) with an age group (`src/family.py`).
- **1.3 Age groups, never exact ages.** The app only knows age groups (0-2, 3-5, 6-9, 10-14, 15-17).
  They nest inside the rail fare groups, so fares stay exact, and they are enough to match places.
  The age groups are never sent to outside services (maps, events, weather, transit); they reach
  the AI model only as part of the request that needs them.
- **1.4 No health data, ever (Art. 9 GDPR).** The app never asks for, stores, infers or comments on
  health, illness, disability, diagnoses, therapy or development. Concretely:
  - no input field about health;
  - a keyword check blocks chat messages that mention health topics (e.g. ADHD, Autismus,
    Diagnose, Krankheit, therapy) and asks the parent to remove that part before anything is sent;
  - the system prompt forbids asking about, repeating or inferring health information;
  - medical and therapy places (paediatricians, Ergotherapie, Logopädie, Frühförderung) are not in
    the knowledge base or the OpenStreetMap categories.
- **1.5 No development assessment (GDPR Art. 9, EU MDR).** The "balanced activities" feature only
  suggests variety based on the themes of outings the parent logged. It never assesses, scores or
  describes a child's development, abilities or behaviour; software that does could count as a
  medical device. Nudges use fixed templates, e.g. "The last 4 weeks had a lot of 🎵 Music and
  🎨 Crafts. Would you like to try a 🧗 Active outing this week?" Words such as "lacks", "behind",
  "delayed", "needs", "should", "good for development" are forbidden in nudges; a test enforces this.
- **1.6 Activity history stays on the phone.** The "visited" log is off by default, switched on by
  the parent, stored only on the device, deletable with one button, and never uploaded. Only the
  chosen theme (e.g. "active") may leave the device when the parent asks for suggestions.
- **1.7 DPIA first.** The activity history feature ships only with a written data protection impact
  assessment (`docs/DPIA.md`): children are vulnerable data subjects and the feature is a form of
  profiling.
- **1.8 No profiling for advertising** and no sale or sharing of any user data with advertisers.

## 2. General GDPR duties
- **2.1 Data minimisation and privacy by default (Art. 5, Art. 25).** Collect only what a feature
  needs; the most private option is the default.
- **2.2 Legal basis per purpose (Art. 6).** Every data flow has a documented basis in the processing
  register below (contract for the core service, consent for optional features such as push
  notifications and the activity history).
- **2.3 Privacy policy (Art. 13).** `Datenschutzerklärung` lists every purpose, legal basis,
  processor, third-country transfer and retention period. Any new data flow updates it in the same PR.
- **2.4 Processors (Art. 28).** Only processors with a data processing agreement (DPA/AVV). Hosting
  in the EU. Listed in the register below.
- **2.5 Third-country transfers (Art. 44 ff.).** The AI requests go through OpenRouter to model
  providers that may be in the US. Before public launch: confirm the transfer basis (DPA, SCCs or
  Data Privacy Framework), enable zero data retention routing if the plan allows, and name the
  providers in the privacy policy.
- **2.6 Personal details in free text.** Before a chat message leaves the app, obvious personal data
  (emails, phone numbers, "my son X") is detected and the parent is asked to remove it.
- **2.7 Retention.** Conversations are deleted from the server when the parent starts a new one and
  automatically after 2 hours without use (`CONVERSATION_RETENTION_SECONDS`, enforced by a
  background cleaner every `CLEANUP_INTERVAL_SECONDS`, also when nobody uses the app); feedback is deleted after 90 days and stores the question text
  only with the parent's consent; push subscriptions are deleted after the trip date; logs never
  contain message content, ages, budgets or keys.
- **2.8 Data subject rights.** Parents can delete their data (and export it where stored on the
  server) without contacting support.
- **2.9 Security.** Keys only through `config.get_secret()`, never logged or shown; HTTPS only;
  invite codes and rate limits protect the deployed app.

## 3. Device storage and tracking (TDDDG § 25)
- **3.1 No trackers.** No analytics, advertising pixels, fingerprinting or third-party tracking
  scripts (no Google Analytics, no Meta pixel). This is why the app needs no cookie banner.
- **3.2** Storage on the device (local storage, IndexedDB, service worker cache) is used only for
  features the parent explicitly uses or switches on.
- **3.3** Adding any tracker or non-essential storage is an owner decision and requires a consent
  tool and an update of this file first.

## 4. AI rules (EU AI Act)
- **4.1 Disclosure (Art. 50, in force since 2 August 2026).** The chat clearly says the parent is
  talking to an AI, and answers are labelled as AI-generated.
- **4.2 No manipulation (Art. 5).** No techniques that exploit the vulnerability of children or
  pressure parents (no fake urgency, no dark patterns).
- **4.3 Grounding.** The AI recommends only places, events, times and links returned by tools; the
  grounding check removes any other link. Money is calculated in code, never by the model.

## 5. Advertising, affiliate links and ranking (UWG)
Affiliate links are **off** in the Capstone version. Before they are switched on:
- **5.1 Label every commercial link (§ 5a Abs. 4 UWG)** as "Anzeige" / "Affiliate-Link", with the
  note "If you buy through this link we receive a commission; your price does not change."
- **5.2 Ranking independent of money (§ 5b Abs. 2 UWG, Annex No. 11a).** The retriever, the AI and
  the ranking never see whether a place earns a commission; affiliate links are added in code only
  when the final answer is displayed. Free places stay in the results. No paid placement unless it
  is clearly marked as an ad.
- **5.3 Publish the main ranking parameters** (country, city, age, indoor/outdoor, relevance to the
  question, weather) on the About page.
- **5.4 No advertising aimed at children (UWG Annex No. 28).** Commercial content addresses parents
  only.
- **5.5 No unproven claims.** No promises that the app improves a child's development or health.
- **5.6** Every affiliate programme's terms are read and recorded in the register before use.
- **5.7** The app does not sell tickets itself (no payments, no reseller role) without a separate
  legal review.

## 6. Copyright and data licences
- **6.1 Own words.** Descriptions are written by the project. Never copy text, photos or logos from
  websites, Google or event pages. Images only if self-made or openly licensed with attribution.
- **6.2 Facts are fine** (names, addresses, ticket prices as facts) but keep the source and the date
  checked (`data/fares.json`).
- **6.3 Licences and attribution** for every data source are recorded in the data source register
  below and shown on the About page. A new source is not used until its licence is checked and
  recorded, including whether commercial use is allowed.
- **6.4 Dependencies.** Only permissive licences (MIT, BSD, Apache-2.0, ISC) in shipped code; any
  GPL/AGPL dependency needs the owner's decision.
- **6.5 Brand.** Before choosing a public app name, check DPMA and EUIPO for existing trademarks.

## 7. Consumer and business duties (owner, before public launch or income)
- **7.1 Impressum (§ 5 DDG)** and Datenschutzerklärung reachable from every page.
- **7.2 Terms of use** (18+, no guarantee of correctness, check official websites).
- **7.3 Never invent prices, opening hours or availability**; always tell parents to check the
  official website or bahn.de.
- **7.4** Business registration (Gewerbeanmeldung), tax advice (Steuerberater) and a check that the
  owner's residence status allows self-employment, before any income.

---

## Register: data sources

| Source | Used for | Licence / terms | Commercial use | Notes |
|---|---|---|---|---|
| Own knowledge base | Places | Project's own text | Yes | No copied text or images |
| `data/fares.json` | Ticket rules and prices | Facts copied by hand from bahn.de, notes in the project's own words | Yes (facts) | Keep `source_url` and `checked_on`; owner re-checks prices before each release |
| OpenStreetMap (Overpass) | Nearby places | ODbL, attribution | Yes | Queried live, not stored |
| Open-Meteo | Weather, geocoding | CC BY 4.0, attribution | **No on the free API** | Paid plan, or DWD / Bright Sky, before income |
| Ticketmaster Discovery API | Family events | Ticketmaster terms | Check terms | Optional key |
| Google Maps URLs, Place IDs | Directions, transit | Public URL scheme, no key | Yes | Place IDs may be stored |
| Transitous | Train journeys (current code) | Free for open-source, non-commercial projects only | No | Owner decision 2026-11-19: the repository stays public while Transitous is used. **Must be switched off before the repository goes private or the app earns money.** Visible link to https://transitous.org/sources/ (About page); its sources' conditions apply (OSM attribution); coordinate with Transitous above 720 `/plan` requests per day; the service may stop at any time, so DELFI + MOTIS is the fallback |
| DELFI GTFS (planned) | Timetables | CC BY 4.0 | Yes | Self-hosted MOTIS |
| gtfs.de realtime (planned) | Live delays | CC BY-SA 4.0 | Yes, share-alike on derived data | No warranty of completeness |

## Register: processing

| Data | Purpose | Legal basis | Where | Retention |
|---|---|---|---|---|
| Chat message, country and city, children's age groups | Answer the question | Contract (Art. 6(1)(b)) | Server memory, OpenRouter → model provider | Deleted on new conversation or after 2 h idle |
| Trip settings: budget, number of adults, Deutschlandticket holders; ticket comparison results; budget items (labels, amounts, notes typed by the parent) | Plan a budget day trip | Contract (Art. 6(1)(b)) | Server memory, OpenRouter → model provider | As above |
| Start and destination town names → coordinates, date, time | Train journeys | Contract (Art. 6(1)(b)) | Open-Meteo geocoder, Transitous | Not stored by the app |
| Feedback rating and technical facts (model, country, tools, grounding); question, answer and comment plus a random browser-session id only when the parent ticks "share" | Evaluation | Rating: legitimate interest (Art. 6(1)(f)); shared text: consent (Art. 6(1)(a)), withdrawable with the "Delete the questions and answers I shared" button while the page is open | Local file on the server | 90 days, then deleted automatically by the background cleaner; records saved before 2026-11-19 (no consent tick) are deleted by the owner after this change is merged |
| Activity history (themes, dates) | Variety nudges | Consent; stays on the device | Phone only | Until the parent deletes it |
| Push subscription (planned) | Trip notifications | Consent | Server | Until the trip date |
| Invite code, request counts (planned) | Access control, cost limits | Legitimate interest (Art. 6(1)(f)) | Server | While the code is active |

## Register: processors and affiliate programmes

| Name | Role | Location | DPA / terms checked |
|---|---|---|---|
| OpenRouter (+ model providers) | AI model access | US / EU routing on some plans | To do before launch |
| Hosting provider (to be chosen, EU) | Server | EU | To do before launch |
| Affiliate programmes | — | — | None active |
