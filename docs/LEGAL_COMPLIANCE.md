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
  - a keyword check (`src/privacy_check.py`, English, German, Vietnamese, on a normalised copy
    of the text: Unicode variants, look-alike letters, spaced letters, text without accents)
    blocks chat messages and the parent's own text in the approval panel that mention health
    topics (e.g. ADHD, Autismus, Diagnose, Krankheit, therapy) and asks the parent to remove that
    part before anything is sent. Blocked text is not stored; the warning names only the kind of
    data, never the words. It is a basic safeguard, not proof: a keyword list cannot catch every
    wording, so the About page asks parents to leave such details out, and the lists are re-checked
    with the Datenschutzberater before launch;
  - **owner decision 2026-11-20:** statements about a child's development ("development",
    "behind his peers", "late talker", "Entwicklung", "Lernschwäche", "phát triển") and questions
    about accessibility needs ("wheelchair", "barrierefrei", "rollstuhlgerecht", "disabled
    access", "step-free", "xe lăn") are blocked by the keyword check like health data; the system
    prompt also forbids judging development, and red-team case r08 checks the block. The About
    page tells parents to check accessibility on the venue's official website. Step-free or
    barrier-free questions in a message that names a pram, a buggy, a bike, a scooter or luggage
    ("mit Kinderwagen barrierefrei?") pass when they name no wheelchair, disability or mobility
    aid (Rollator, Reha-Buggy, walker, crutches); the check does not test that the question is
    about the equipment, so such a word anywhere in the message turns off the accessibility
    check for that message (a residual, 2.6). "Is it accessible by train / on foot / in winter?"
    (getting there) and, by owner decision of 2026-11-20, "Is the playground accessible for
    toddlers?" (suitability by age, only when the message ends after the age word) pass;
    "accessible for kids with a walker" is blocked. Generic
    accessibility questions ("Is the museum accessible?", "What accessibility does the zoo
    offer?") are blocked too. Giftedness ("gifted", "hochbegabt", "advanced for his age") counts
    as a development statement and is blocked; only the verb with an object ("we were gifted
    tickets") passes.
    "Development" and "Entwicklung" are blocked only about a child ("my son's development",
    "seine Entwicklung", "sprachliche Entwicklung"), so "game development workshop" or
    "Stadtentwicklung" pass;
  - **stopping rule (owner decision 2026-11-20):** after nine review rounds the keyword lists
    cover the wordings the reviewers found. Other wordings of the same data are an accepted
    residual of this basic safeguard (2.6). New terms are added only when the evaluation, the
    red-team cases or a real report shows a miss, together with a test for it, and the
    Datenschutzberater re-checks the lists before launch;
  - **block-only rule (owner decision 2026-11-20, after 13 review rounds):** changes to the
    keyword check only add blocks. A newly found false alarm (a harmless question that is
    blocked) is recorded in 2.6 as an accepted false alarm instead of loosening a pattern, because
    every loosening so far let real data through; the parent rephrases once. Mapping a look-alike
    character to its plain form (such as "´" to "'") is not a loosening (owner decision
    2026-11-20, review round 17): the variant then gets
    exactly the result of the plain wording, even where it was blocked by accident before;
  - **baseline for regressions (owner decision 2026-11-20, review round 19):** a regression is
    a sentence that a commit from the block-only rule on (c560f86 and later) blocked and that now
    passes. A sentence that only the earlier commits blocked (they blocked bare keywords such as
    "injury" or "booster" and were narrowed to stop false alarms) is an accepted residual in 2.6,
    unless it is added as a new block. Before each review round the whole reviewer corpus is run
    at every commit of the branch and any regression is fixed first;
  - the system prompt forbids asking about, repeating or inferring health information;
  - medical and therapy places (paediatricians, Ergotherapie, Logopädie, Frühförderung) are not in
    the knowledge base or the OpenStreetMap categories.
- **1.5 No development assessment (GDPR Art. 9, EU MDR).** The "activity variety suggestions"
  feature works like this and nothing more: when the outings the parent marked as visited were
  mostly of one kind (e.g. brain games, music, crafts), it suggests an outing of another kind
  (e.g. active, outdoors), and the other way round. It is about variety of outings, not about the
  child. It never assesses, scores or describes a child's development, abilities or behaviour;
  software that does could count as a medical device. Nudges use fixed templates, e.g. "The last
  4 weeks had a lot of 🎵 Music and
  🎨 Crafts. Would you like to try a 🧗 Active outing this week?" Words such as "lacks", "behind",
  "delayed", "needs", "should", "good for development" are forbidden in nudges; a test enforces this.
- **1.6 Activity history stays on the phone.** The "visited" log is off by default, switched on by
  the parent, stored only on the device, deletable with one button, and never uploaded. Only the
  chosen theme (e.g. "active") may leave the device when the parent asks for suggestions.
- **1.7 Risk assessment first.** The activity variety feature ships only with a written, voluntary
  risk assessment (`docs/RISK_ASSESSMENT_ACTIVITY_VARIETY.md`): it records which kinds of outings a
  child went to. Whether a formal DPIA (Art. 35 GDPR) is legally required is a question for a
  lawyer: a required DPIA would also oblige the owner to appoint a data protection officer
  (§ 38(1) BDSG). Until that is answered, the feature stays off in any public deployment.
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
- **2.6 Personal details in free text.** Before a chat message, a budget note or a reason for
  rejecting a step leaves the app, obvious personal data (e-mails, phone numbers, street addresses,
  names such as "my son X", exact ages such as "7 years old") is detected by `src/privacy_check.py`
  and the parent is asked to remove it. Town and city fields of tools accept only place names
  (`check_place_name`: up to 5 capitalised words of Latin letters, counted across spaces and
  hyphens, small connecting words such as "am" or "upon" allowed, no family or instruction
  words), so no sentence, number or contact detail reaches the geocoder; Ticketmaster receives
  only the geocoder's town name. A capitalised person's name cannot be told from a town by its
  letters; the parent sees every such value in the approval panel first.
  Accepted residuals of the keyword check (re-checked with the Datenschutzberater before launch):
  first names in place-name fields; German names inside a clause after "wenn", "weil", "ob" and
  similar words or after a preposition without a relative clause ("mit meinem Sohn Max ins
  Museum"), because there the verb comes last and a name cannot be told from a noun; after a
  preposition, a daughter's name ending in -e, -en, -er, -es, -n or -s before ", die" ("mit meiner
  Tochter Marie, die …"), because plural nouns look the same; a possessive directly before a name
  without "Sohn"/"Tochter" ("Unser Max mag Dinos") and the parent's own name ("Ich bin Anna");
  names written in lower case; ages written only in words inside other phrases, an age followed
  by "&", "with", "mit", "or" or "oder" ("Lena is 7 or 8", "Lena ist 7 mit viel Energie"); after a
  preposition, "mein Kind X, das …" (neuter nouns look the same); a domain spelled in link text in
  the middle of the label ("Visit evil . top today"); and two ages as a shortened compound ("4- und
  6-jährige Kinder"), because "für 4- und 5-Jährige" is an age-group question; health words with
  an extra accent on a letter that has none ("Thérapie"); a daughter's name ending in -ion or -s
  after a preposition ("Marion, die …"); link text whose spelled domain is in title case (".Com")
  or written with "dot", "(.)" or spaced letters and an uncommon ending; and, under the stopping
  rule in 1.4, any other wording of health data, names or ages that the lists do not contain;
  a pram, bike, scooter or luggage word anywhere in a message turns off the step-free and
  generic accessibility check for that message ("Is the museum accessible? We come with a
  stroller."); German children's names before a clause-final verb when the last name ends in
  -e, -n or -s ("Meine Kinder Max und Jonas tanzen."); "has cold" without the article ("my son
  has cold", owner decision 2026-11-20, so that "have cold drinks" passes); "was/were/been/got/get
  gifted" followed by "a", "an", "two", "three", "some", "my", "our", a digit, "tickets" or
  "vouchers" ("She was gifted a teacher said"), so that "We were gifted a zoo membership" passes;
  a name with "s" and no apostrophe ("Bens knee injury"), with a space or a double quote ("Ben s",
  'Ben"s') or with a rare apostrophe-like mark that is not mapped (U+02ED, U+055B, U+0313,
  U+0315); more than six words between the verb and "injury", or more than five between
  "is/was/seems/looks/appears/became" and "gifted"; "loading poorly" about a child. The link target itself is always a verified tool URL.
  Accepted false alarms (the parent rephrases once): slang ("That's sick!"), rare uses of health
  words ("rash decision", "Der Stau ist übel", "Corona beer garden", "his shots at goal",
  "Stitches and craft workshop", "MMR museum", "Zelt aufgeschlagen"), and a German noun before
  "ist N" without an article ("Film ist etwa 4"). Under the block-only rule (1.4, review round
  14): "gifted" as a verb with a person ("Grandma gifted the kids tickets", "gifted him a
  voucher") or "the" ("We were gifted the tickets"); injuries in a general question with a verb
  or "is" ("Has anyone had injuries on the trampoline?", "My worry is injuries at trampoline
  parks"); "need a booster" and "her booster at home" (could be the car seat); "accessible for
  toddlers?" followed by another sentence; "doing poorly" about a place ("The museum is doing
  poorly financially"); "walker" as a hiker or a name next to an accessibility question ("keen
  walkers", "Walker Art museum"). Review round 15: injury statistics or policies ("Which park
  has the fewest injuries?", "Which parks have more injuries?", "the park's injury record",
  "Today's injury report", "Do they have injury cover?", "What happens with a serious injury?",
  "Let's avoid any injury"); "his booster for the plane"; "cannot walk" about the way, not the
  child ("You cannot walk there from the station, is it accessible by train?"). Review round 16:
  "Which trampoline parks have the fewest injuries?", "Do they have injury insurance?", "the
  park's injury risk", "the kids' injuries at trampoline parks", "the parks' injury statistics",
  "He has an injury prevention class", "Is his booster in the car?", "We are gifted tickets by
  grandma". Review round 17: "Is there a children's injury clinic?", "Does the park have injury
  insurance?", "What are the kids' injury risks?", "the zoo's injury prevention tips", "the
  boys' injury rate", "Grandma's gifted us tickets", "Which toys are best gifted to toddlers?",
  "We were very kindly gifted two tickets". Review round 18: "Does the zoo have a minor injury
  unit?", "We were happy, grandma gifted us tickets", "The zoo is nice. Grandma gifted us
  tickets", "He got injuryfree last season".
  Review round 19 (162aff7 and the round-19 additions for names, ages, injury, booster, poorly,
  sick, hospitalisation and development statements): "There's no injury risk at this park,
  right?", "What's your injury policy?", "Where's your nearest injury unit?", "What's this
  injury about", "Is the zoo open? Grandma gifted us tickets", "My mum seemed happy and gifted
  us a voucher", "What to do after a minor injury?", "Is there help with a minor injury on
  site?", "Exhibition on healing from injury in the war", "It's the injury capital of Europe",
  "That's the injury time in football", "Here's the knee injury update", "Injuries, how common
  are they at trampoline parks?", "Sports injury, what does the clinic do?", "Is the trampoline
  park injury prone?", "The app does poorly on mobile", "The website reads poorly", "They're
  gifted with a great view", "You're gifted a free drink at the cafe", "Does the ride have a
  booster section?", "booster" alone, "Museum for kids aged 3 and 4", "Activities for kids aged
  6 and 9", "Kinder 6 und 9 Jahre gemischt?", "Die Entwicklung von Berlin ist spannend".
  Review round 20: price questions with one child's age ("Eintritt Kind 6 Jahre?", "Eintritt
  Kinder 6 Jahre frei", "Preis für ein Kind 6 Jahre im Zoo?"), "Injury-free …" at the start of a
  sentence, "The park's staff are trained for any injury", "Nobody was badly hurt …", "Brauchen
  Sie Ihren Impfpass?", "We're gifted a voucher …", "Is there a booster club?". Residual: a
  bare "booster" statement in a message that also names a vehicle or seat ("The booster made
  him tired, can we take the train?"), because that message is read as a booster-seat question.
  Regressions are measured from c560f86 (baseline rule in 1.4): every sentence the reviewers
  used in rounds 1-19 was run at every commit of the branch, and none that a commit from c560f86
  on blocked passes now, apart from look-alike cases under 1.4. Sentences only the earlier
  commits blocked are accepted residuals unless re-added as blocks.
- **2.7 Retention.** Conversations are deleted from the server when the parent starts a new one and
  automatically after 2 hours without use (`CONVERSATION_RETENTION_SECONDS`, enforced by a
  background cleaner every `CLEANUP_INTERVAL_SECONDS`, also when nobody uses the app); feedback
  is deleted after 90 days and stores the question text only with the parent's consent;
  long-term memory (T5.11) keeps each preference `LONG_TERM_MEMORY_RETENTION_DAYS` (30) days
  after it was last saved, deleted by the same cleaner and when the memory is loaded, and
  "Forget everything" deletes all of it at once, together with any file the app could not load
  and any temporary copy; push subscriptions are deleted after the trip date; logs never contain
  message content, ages, budgets or keys.
- **2.8 Data subject rights.** Parents can delete their data (and export it where stored on the
  server) without contacting support. Long-term memory (T5.11) is listed in the sidebar and deleted
  with "Forget everything", which is offered whenever something is remembered, also while the
  switch is off; switching it off stops its use from the next step, also for a turn that waits
  for approval (the switch is read again at every step). What the parent said earlier stays in
  the current conversation until a new one starts (2.7).
- **2.9 Security.** Keys only through `config.get_secret()`, never logged or shown; HTTPS only;
  invite codes and rate limits protect the deployed app. Every length limit on the parent's text
  (question, reject reason, edited values, folded length) is enforced on the server, not only by
  the text box, so the privacy check stays fast.
- **2.10 No tracing, quiet logs.** No LangSmith or other third-party tracing, observability or
  error-reporting service (they would receive messages, age groups and trip settings): the tracing
  switches in `config.TRACING_ENV_OFF` are forced off in `src/llm.py`. Libraries that log request
  bodies at DEBUG (`config.QUIET_LOGGERS`) are capped at `config.LOG_LEVEL` (INFO). The app's own
  logs hold only event names and error types. Adding any such service is an owner decision that
  updates the processor register first.
- **2.11 Long-term memory (T5.11).** Off by default; the parent switches it on in the sidebar
  ("Remember our preferences on this computer", consent; the switch's help text says what is
  kept, that it goes to the AI model with each question, that everyone using the app on that
  computer shares it, and how to stop and delete it). It keeps only fixed choices: a place
  category or indoor/outdoor, and "likes" or "avoids" (`config.MEMORY_TOPICS`,
  `config.MEMORY_FEELINGS`), with the date it was saved. Never free text, place names, age
  groups, the budget, the family size, or visited or liked places (those would be the activity
  history of 1.5-1.7). The model can only save through the `remember_preference` tool, whose
  arguments are these fixed choices; the switch (from the run's config) and the store are
  injected by the graph, and a preference is saved only when the parent's own latest message
  names its topic as a whole word (`config.MEMORY_TOPIC_WORDS`; "parking", "parken" or "theme
  park" do not count as "park"), so text in a tool result cannot add a topic the parent never
  mentioned; only before any other tool result of the same turn, so a tool result of that turn
  cannot decide what is saved; and only once per topic in one step. **Every save waits for the
  parent's approval** (`config.TOOLS_ALWAYS_REVIEWED`, also with auto-approve on; owner decision
  2026-11-25): the approval panel shows the kind of place and "likes" or "avoids", and nothing is
  stored if the parent rejects. With the switch off the call is refused without a pause. A save that pauses next to another step while the switch is off is decided by the switch at approval time (2.8): if the parent switches memory on first, the panel shows the save without the "Memory is off" note and approving stores it (owner decision 2026-11-26, T5.2; `test_switching_memory_on_during_a_pause_saves_the_approved_save`). Without
  the server setting below the model is not offered the tool at all. Each saved preference is
  shown under the answer. Remembered preferences change which places the AI suggests first
  (5.3). Without a login the memory belongs to the computer that runs the app (one local profile
  shared by every browser session there). The server setting `config.LONG_TERM_MEMORY_ENABLED` switches the
  whole feature off; while it is on, the switch is offered only when the page is opened on that
  computer (`views/memory.py: is_local_visit`, which checks the connection's address, its Host
  header and its Origin header, required and of the same origin, which a web page cannot set)
  and `.streamlit/config.toml` accepts only local host names (`server.allowedHosts`). If the file
  cannot be opened at start-up (another program holds it), it is kept as it is, never used or
  sent, and the next start-up (which applies the 30-day limit) or the next save rewrites it; until
  then the sidebar cannot list it. A visit through a proxy or tunnel that adds forwarding headers
  (`Forwarded`, `Via`, `X-Forwarded-*`, `X-Real-*`, `X-Client-*`, `X-Original-*`,
  `True-Client-*`, `Cf-*`, even empty) is never local; one that adds none of them and rewrites
  Host and Origin to localhost cannot be told apart, which is why exposing the app in any way
  counts as a deployment. The feature is for the local demo only (see "Before a public deployment").
  Remaining risk: the model proposes the topic and the feeling (from a message that only mentions
  a topic, or from an earlier turn's tool result), but nothing is stored unless the parent
  approves exactly that save; an approved save is shown under the answer and can be deleted.

## 3. Device storage and tracking (TDDDG § 25)
- **3.1 No trackers.** No analytics, advertising pixels, fingerprinting or third-party tracking
  scripts (no Google Analytics, no Meta pixel). This is why the app needs no cookie banner.
- **3.2** Storage on the device (local storage, IndexedDB, service worker cache) is used only for
  features the parent explicitly uses or switches on.
- **3.3** Adding any tracker or non-essential storage is an owner decision and requires a consent
  tool and an update of this file first.
- **3.4 Nothing from third-party hosts.** (owner decision 2026-11-25, T1.10) Fonts, icons, images,
  map tiles, stylesheets and scripts that the page loads by itself come from the app itself: the
  fonts and Material Symbols shipped inside Streamlit (6.4), emoji, or files the owner approved.
  None is loaded from another host, because each such load sends the parent's IP address to that
  host (LG München I, judgment of 20 January 2022, 3 O 17493/20). In Streamlit this means: no Google
  Fonts or CDN; no theme font option (`font`, `headingFont`, `codeFont`) with a `<name>:<url>`
  value and no `[[theme.fontFaces]]` with an outside `url`; no Material Symbol as `page_icon` or
  `st.Page(icon=...)` (Streamlit fetches such a tab icon from `fonts.gstatic.com`; the app uses an
  emoji, which Streamlit renders locally); no `st.image`, `st.logo`, `st.video` or `st.audio` with a remote URL; no
  `st.map` or `st.pydeck_chart` (base map tiles from Carto or Mapbox; owner decision 2026-11-25:
  no embedded map unless the owner decides otherwise and updates this file first); no remote image
  in Markdown; a URL from a tool result or the knowledge base is never rendered as an element that
  loads it (the grounding check drops images from the answer's Markdown, not from such elements).
  A link the parent clicks is not a load. Today nothing in `app.py`, `views/` or
  `.streamlit/config.toml` loads from another host. Streamlit itself can add such loads, so the PR
  that upgrades Streamlit re-checks this rule in its Legal check, next to the licence check of
  6.4; a Dependabot PR has no Legal check, so the owner adds that re-check as a PR comment before
  merging it. Adding an outside asset is an owner decision and updates this file
  first. Legal basis: the load is a transfer of personal data (the IP address) under GDPR
  Art. 6(1) and, for hosts outside the EU, Art. 44 ff. (see 2.2, 2.5); if the outside host also
  sets or reads cookies, § 25 TDDDG and 3.1 apply too. It sits here next to 3.1 because it is the
  same kind of rule.

## 4. AI rules (EU AI Act)
- **4.1 Disclosure (Art. 50, in force since 2 August 2026).** The chat clearly says the parent is
  talking to an AI (notice above the chat), every answer is labelled "AI-generated" and carries a
  machine-readable marker (a hidden element with `data-ai-generated="true"`), and the About page
  says so.
- **4.2 No manipulation (Art. 5).** No techniques that exploit the vulnerability of children or
  pressure parents (no fake urgency, no dark patterns). The system prompt forbids urgency and
  scarcity claims and claims about a child's development (5.5); red-team cases in
  `data/eval_questions.json` check both: r09 (urgency) and r13 ("make my child smarter") must not
  reach the parent as a claim, r08 (a development statement) is blocked before the model.
  No live red-team run (owner decision 2026-11-24; OpenRouter's terms on red-teaming,
  `docs/THIRD_PARTY_TERMS.md`): the cases are tested offline only, with fake models that obey the
  request, and a code check on the final answer will replace the urgency, scarcity and development
  claims it recognises; as a pattern check it misses some wordings, and its miss rate is recorded
  (T5.6, to do).
- **4.3 Grounding.** The AI recommends only places, events, times and links returned by tools; the
  grounding check removes any other link. Money is calculated in code, never by the model: the
  family for the ticket comparison is taken from the app's settings (the model cannot pass it), and
  the ticket and budget figures are shown under the answer from the tool results, not from the
  model's text.

## 5. Advertising, affiliate links and ranking (UWG)
Affiliate links are **off** in the Capstone version. Before they are switched on:
- **5.1 Label every commercial link (§ 5a Abs. 4 UWG)** as "Anzeige" / "Affiliate-Link", with the
  note "If you buy through this link we receive a commission; your price does not change."
- **5.2 Ranking independent of money (§ 5b Abs. 2 UWG, Annex No. 11a).** The retriever, the AI and
  the ranking never see whether a place earns a commission; affiliate links are added in code only
  when the final answer is displayed. Free places stay in the results. No paid placement unless it
  is clearly marked as an ad.
- **5.3 Publish the main ranking parameters** (country, city, age, indoor/outdoor, relevance to the
  question, weather, and the remembered preferences when the parent switched long-term memory on,
  2.11) on the About page (done: "How results are ranked").
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
  below and shown on the About page; under an answer, the app itself (not the model) credits the
  live sources it used. A new source is not used until its licence is checked and recorded,
  including whether commercial use is allowed.
- **6.4 Licences of everything we use.** Only permissive licences (MIT, BSD, Apache-2.0, ISC,
  PSF, MPL-2.0 unmodified) for Python packages (runtime and dev), JavaScript libraries, fonts,
  icons and images; AI models and embedding models are used only under terms that allow the use
  (each model is named in the processor register with the date its terms were checked; a new or
  changed model updates that row in the same PR); data sets follow 6.3. Any GPL/AGPL/SSPL, "non-commercial"
  or unclear licence needs the owner's decision first. Check the licence when adding or upgrading a
  dependency in `pyproject.toml`.
  **Fonts inside Streamlit (owner decision 2026-11-25, T1.10):** the fonts shipped inside the
  Streamlit package, used as Streamlit ships them (Source Sans, Source Serif and Source Code, and
  the KaTeX fonts for formulas, under the SIL OFL 1.1; the Material Symbols icons under
  Apache-2.0), are accepted as part of that dependency. Any other font, including another OFL font, is still an owner
  decision first. (Licences from the model's knowledge; the owner checks the font projects'
  licence files by hand, since the Streamlit wheel ships no notice for them.)
- **6.5 Brand.** Before choosing a public app name, check DPMA and EUIPO for existing trademarks.

## 7. Consumer and business duties (owner, before public launch or income)
- **7.1 Impressum (§ 5 DDG)** and Datenschutzerklärung reachable from every page.
- **7.2 Terms of use** (18+, no guarantee of correctness, check official websites).
- **7.3 Never invent prices, opening hours or availability**; always tell parents to check the
  official website or bahn.de.
- **7.4** Business registration (Gewerbeanmeldung), tax advice (Steuerberater) and a check that the
  owner's residence status allows self-employment, before any income.

## 8. Current limitation: synthetic data only (owner decision 2026-11-19)
- The app uses the **school's OpenRouter account**. Its privacy settings (zero data retention,
  no providers that train on prompts) cannot be changed by the owner, and no DPA can be signed.
- Therefore, until the owner has an AI provider account of their own with a DPA: **only synthetic
  (made-up) data** in development, demos, evaluations and tests; **no real users and no public
  deployment**. User tests with real parents use made-up questions and no real family details.
- **Testers:** only adults (18+) who agreed beforehand (a short written note is enough) that they
  test an AI demo, use only made-up questions, and that their feedback may be kept for 90 days;
  no children take part, no screen or voice recordings, and testers' names are not stored with
  their feedback. Long-term memory (2.11) is shared by everyone on the test computer: press
  "Forget everything" before and after each tester, so no tester's preferences reach the next.

## Before a public deployment (checklist)
Remind the owner of this whole list whenever deployment comes up. Nothing here blocks the local
Capstone demo with synthetic data.

**AI provider (the biggest open point)**
- [ ] Own AI account instead of the school's OpenRouter account: OpenAI directly (online DPA; EU data
      residency project if eligible), OpenRouter Business/Enterprise, Azure OpenAI in the EU or
      Mistral. Sign the DPA, enable zero data retention, exclude providers that train on prompts.
- [ ] Replace the Qwen embedding model (providers possibly outside the EU, e.g. China/Singapore)
      and rebuild the Chroma index.
- [x] Provider, base URL, model names and embedding model switchable from `src/config.py` only
      (`AI_PROVIDER_NAME`, `AI_BASE_URL`, `EMBEDDING_BASE_URL`, `API_KEY_NAME`, model names).

**Legal texts and contracts**
- [ ] Impressum (name, address where legal papers can be served, email; § 5 DDG / § 18 MStV) and
      Datenschutzerklärung, linked from every screen and inside the PWA.
- [ ] Hosting DPA (e.g. Hetzner AVV) and servers pinned to Germany.
- [ ] Terms of use: 18+, no guarantee, check official websites.
- [ ] Lawyer / Datenschutzberater: DPIA needed for activity variety (and § 38 BDSG)? Impressum
      without the home address? Consent withdrawal for shared feedback? Web Push services as
      processors? UK GDPR if UK parents are targeted?

**App features**
- [x] AI disclosure in the chat plus a machine-readable marker on answers (AI Act Art. 50).
- [ ] Health / personal-data keyword check on every free-text field: a basic version is done
      (chat, budget table, reject reason, edited values); before launch the Datenschutzberater
      re-checks the word lists and coverage, and the AI provider DPA with zero data retention
      (above) remains the real safeguard.
- [ ] Licence notices for what the app sends to browsers (6.4): a licences list on the About page
      for Streamlit's frontend, its fonts (SIL OFL 1.1) and the Material Symbols (Apache-2.0),
      since both licences ask for the licence text to go with copies (T1.10, legal-reviewer).
- [ ] Invite codes (hashes and counters only) and per-code daily limits.
- [ ] Web Push: own opt-in screen, minimal payload, subscriptions deleted after the trip date.
- [ ] Ticketmaster: family events only, drop 18+ events; privacy link in the footer.
- [ ] Overpass: own or another instance; caching. (Identifying User-Agent with the repository as
      contact: done, `config.HTTP_USER_AGENT`.)
- [ ] Transitous: request counter (coordinate above 720 `/plan` per day).
- [ ] Coordinates from OpenStreetMap, not Google; `place_id_checked_on` for Place IDs.
- [ ] Re-check `data/fares.json` prices and every knowledge base entry (closed places).
- [ ] Long-term memory (2.11): set `config.LONG_TERM_MEMORY_ENABLED = False` (the visitor check
      is only a second line; sharing the demo through a tunnel such as ngrok counts as a
      deployment), and set `server.allowedHosts` in `.streamlit/config.toml` to the
      real host names; or move the memory to the parent's device (or behind a login, per
      account) with a record of each consent, wording that does not say "on this computer" and its
      own text in the Datenschutzerklärung. Lawyer / Datenschutzberater: must switching off delete
      the data (Art. 7(3), 17(1)(b))? Does the personalised order need more than the 5.3 note
      (§ 5b UWG)?

**Before earning money** (in addition)
- [ ] Replace Transitous, the free Open-Meteo API and the public Overpass server; turn off
      Ticketmaster or join its affiliate programme (no revenue from the API otherwise).
- [ ] Business registration, Steuerberater, residence-status check.
- [ ] Affiliate labels, commission-blind ranking, each programme's terms read.
- [ ] Subscriptions: Stripe Checkout, order and cancellation buttons, withdrawal notice, terms by
      a lawyer.

---

## Register: data sources

The terms, limits and attribution rules of each outside service, with the dates they were read, are in `docs/THIRD_PARTY_TERMS.md`.

| Source | Used for | Licence / terms | Commercial use | Notes |
|---|---|---|---|---|
| Own knowledge base | Places | Project's own text | Yes | No copied text or images |
| `data/fares.json` | Ticket rules and prices | Facts copied by hand from bahn.de, notes in the project's own words | Yes (facts) | Keep `source_url` and `checked_on`; owner re-checks prices before each release |
| OpenStreetMap (Overpass, overpass-api.de) | Nearby places | ODbL, attribution; Overpass usage policy (fair use, no heavy load) | Yes (data); the public server is for light use only | Queried live, not stored; identifying User-Agent with the repository as contact; attribution shown under answers by the app |
| Open-Meteo | Weather, geocoding | CC BY 4.0, attribution | **No on the free API** | Paid plan, or DWD / Bright Sky, before income; attribution shown under answers by the app |
| Ticketmaster Discovery API | Family events | Ticketmaster Discovery API terms (attribution, no caching beyond the terms, privacy link) | Check terms; revenue only through its affiliate programme | Optional key, read only through `config.get_secret()`; family events only; attribution shown under answers by the app |
| Google Maps URLs, Place IDs | Directions, transit | Public URL scheme, no key | Yes | Place IDs may be stored |
| Transitous | Train journeys (current code) | Free for open-source, non-commercial projects only | No | Owner decision 2026-11-19: the repository stays public while Transitous is used. **Must be switched off before the repository goes private or the app earns money.** Visible link to https://transitous.org/sources/ (About page); its sources' conditions apply (OSM attribution); coordinate with Transitous above 720 `/plan` requests per day; the service may stop at any time, so DELFI + MOTIS is the fallback |
| DELFI GTFS (planned) | Timetables | CC BY 4.0 | Yes | Self-hosted MOTIS |
| gtfs.de realtime (planned) | Live delays | CC BY-SA 4.0 | Yes, share-alike on derived data | No warranty of completeness |

## Register: processing

| Data | Purpose | Legal basis | Where | Retention |
|---|---|---|---|---|
| Chat message, country and city, children's age groups | Answer the question | Contract (Art. 6(1)(b)) | Server memory, OpenRouter → model provider | Deleted on new conversation or after 2 h idle |
| Trip settings: budget, number of adults, Deutschlandticket holders; ticket comparison results; budget items (labels, amounts, notes typed by the parent) | Plan a budget day trip | Contract (Art. 6(1)(b)) | Server memory, OpenRouter → model provider | As above |
| Approval panel: the reason the parent types when rejecting a step, and the tool values the parent edits (town names, country, place type, dates, departure time in the form; any argument in the JSON editor for other tools; budget items) | Run, change or skip the planned tool calls | Contract (Art. 6(1)(b)) | Server memory, OpenRouter → model provider (the reject reason and the edited values become part of the conversation the model reads); edited values for a live tool also go to that tool's services, as in the rows below | As above |
| Start and destination town names → coordinates, date, time | Train journeys | Contract (Art. 6(1)(b)) | Open-Meteo geocoder, Transitous | Not stored by the app |
| Town or city name, country, place category | Nearby places | Contract (Art. 6(1)(b)) | Open-Meteo geocoder, Overpass (OpenStreetMap) | Not stored by the app; the service sees the server's IP address and User-Agent, not the parent's |
| Town or city name, country, dates | Family events | Contract (Art. 6(1)(b)) | Open-Meteo geocoder, then Ticketmaster (US) with the geocoder's town name | Not stored by the app; only with the optional key |
| Town or city name, country, dates | Weather forecast | Contract (Art. 6(1)(b)) | Open-Meteo geocoder and forecast | Not stored by the app |
| Feedback rating and technical facts (model, country, tools, grounding); question, answer and comment plus a random browser-session id only when the parent ticks "share" | Evaluation | Rating: legitimate interest (Art. 6(1)(f)); shared text: consent (Art. 6(1)(a)), withdrawable with the "Delete the questions and answers I shared" button while the page is open | Local file on the server | 90 days, then deleted automatically by the background cleaner (no records from before the consent tick existed; checked 2026-11-20) |
| Long-term memory: liked or avoided place categories and indoor/outdoor (fixed choices only), each with the date it was saved (T5.11) | Tailor suggestions in later conversations | Consent (Art. 6(1)(a)): the sidebar switch, off by default; withdrawn by switching off and "Forget everything" | Local file on the computer that runs the app (`data/memory/`, gitignored); with each question while the switch is on: OpenRouter → model provider | 30 days after it was last saved, or at once with "Forget everything" |
| Activity history (themes, dates) | Variety nudges | Consent; stays on the device | Phone only | Until the parent deletes it |
| Push subscription (planned) | Trip notifications | Consent | Server | Until the trip date |
| Invite code, request counts (planned) | Access control, cost limits | Legitimate interest (Art. 6(1)(f)) | Server | While the code is active |

## Register: processors and affiliate programmes

OpenRouter's and the model providers' terms (red-teaming, data use) are summarised in `docs/THIRD_PARTY_TERMS.md`.

| Name | Role | Location | DPA / terms checked |
|---|---|---|---|
| OpenRouter (+ model providers, incl. the embedding model's providers). Models: `openai/gpt-5-mini`, `openai/gpt-5-nano`, `openai/gpt-5` (OpenAI terms via OpenRouter); embeddings `qwen/qwen3-embedding-8b` (Apache-2.0 per the model card, checked 2026-11-20; providers possibly in China / Singapore). OpenAI's usage policies and OpenRouter's terms checked 2026-11-24 (`docs/THIRD_PARTY_TERMS.md`); embedding seen served by DeepInfra on 2026-11-24 (location not checked); the hosting providers' terms: not yet checked (owner, before launch) | AI model access | US / other countries; EU routing only on Business/Enterprise plans | **Not possible today:** the project uses the school's OpenRouter account, so the owner cannot sign a DPA or set zero data retention / no-training providers. Allowed only with synthetic data (see "Before a public deployment") |
| Hosting provider (to be chosen, EU) | Server | EU | To do before launch |
| Affiliate programmes | — | — | None active |
