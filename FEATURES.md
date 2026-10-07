# RadReport

**Speak the report. Get it back finished, checked and ready to sign.**

RadReport turns a radiologist's spoken dictation into a complete, structured medical report. It listens, writes, double-checks its own work, flags anything risky, and hands the doctor a draft that only needs a quick review and a signature.

<!-- tab: features | Features -->

## The problem

When a radiologist looks at an X-ray, CT or MRI scan, they usually speak their findings into a recorder. Someone then types it up, fits it into the hospital's report layout, and sends it back for checking. That takes hours, typing mistakes creep in, and an urgent finding can sit unnoticed in a pile.

Voice-typing tools help with the typing, but they bring new risks. They mishear medical words, they sometimes write down words nobody said, and they don't understand when a doctor corrects themselves mid-sentence ("left lung — sorry, right lung").

## What RadReport does

1. **The doctor speaks.** They dictate the way they always have.
2. **RadReport writes the report.** It fills in the lab's own report layout, section by section.
3. **RadReport checks itself.** Every statement is linked to the moment in the recording where it was said. Anything it can't back up is flagged instead of guessed.
4. **The doctor reviews and signs.** Risky or uncertain parts are shown first, and urgent findings raise an alert straight away.
5. **The report goes to the hospital** in the formats hospital systems already accept.

## Features

### For radiologists

**Speak, don't type**
Dictate naturally. RadReport turns speech into a finished report in the lab's own layout, with sections, measurements and standard phrases in the right places.

> **Why:** Radiologists already dictate, and asking busy doctors to change their habits is the quickest way to lose them. RadReport fits around the way they work instead of asking them to fill in forms.

**Understands corrections**
Doctors correct themselves all the time: "left — sorry, right". RadReport removes the slip and keeps the correction, so the report says what the doctor meant, not what they said first.

> **Why:** Ordinary voice typing writes down both the slip and the fix. In radiology the slip is often which side of the body, and the wrong side is one of the most dangerous mistakes a report can contain.

**Click any sentence to hear it**
Every line in the draft is linked to the exact second of the recording it came from. One click plays that moment, so checking a line takes seconds instead of replaying the whole recording.

> **Why:** A draft only saves time if checking it is quicker than writing it. Being able to hear any line in one click is where the time saving comes from.

**Urgent findings can't hide**
If the doctor mentions something dangerous, such as a collapsed lung or bleeding in the brain, RadReport raises an alert at once and starts a response clock. A report with an alert nobody has acknowledged can't be signed. It also understands "no": "no fracture" does not raise a fracture alert.

> **Why:** A missed urgent finding is the worst thing that can happen in radiology. So this check follows fixed, written rules rather than AI: it behaves the same way every time, and it can be tested. It reads "no" carefully, so "no fracture, but a collapsed lung" still raises the alarm for the lung.

**The risky parts come first**
RadReport rates how sure it is about each part of the report. The parts it is least sure of, and the medically important ones, go to the top and are clearly marked, so the doctor's attention goes where it matters.

> **Why:** An overall "looks good" rating can hide one shaky but important detail among thirty solid ones. RadReport's rating is pulled down by its weakest important part, because that one part is exactly what the doctor needs to see.

**Anything added automatically is marked**
If a standard "everything is normal" sentence was filled in for the doctor rather than spoken, it is visibly tagged, so nobody signs something they didn't actually say.

> **Why:** A signature means "I said this". If filled-in text looked the same as spoken text, a doctor could sign a sentence they never said. Automatic filling is also switched off unless a lab chooses to turn it on.

**Mark a draft as useless**
If a draft is wrong, one button says so and why. That feedback is counted in the quality reports and used to make the next drafts better.

> **Why:** A draft that wasted the doctor's time is easy to miss: the doctor just quietly rewrites it. One click turns that into something the team can count and fix.

### Safety built in

**It never makes things up**
Every detail in the report must point to the words in the recording that support it. If it can't, the detail is removed and flagged, never quietly kept.

> **Why:** AI can write fluent, convincing text that isn't in the source. RadReport checks each detail against the exact words it claims to come from, not just anywhere in the recording, so an invented finding cannot slip through.

**Several listeners vote on every word**
RadReport can listen to the same recording with more than one speech engine and let them vote, word by word. A word that only one of them "heard" loses the vote. This removes the most dangerous kind of mistake: findings that were never said.

> **Why:** A speech engine that invents a word usually does so with confidence. When three listeners compare notes, a word only one of them heard is outvoted two to one.

**A second AI double-checks the first**
A separate AI reviewer reads each draft against the recording and questions anything that doesn't hold up, before a person ever sees it.

> **Why:** Fixed rules catch the mistakes someone thought of in advance. A reviewer that reads the whole draft catches contradictions nobody predicted. If the reviewer itself has a problem, the draft still goes to a person, so the safety net can never block the work.

**Only radiologists can sign**
An assistant can edit a draft, but only a radiologist can sign it. Every edit and every signature is recorded.

> **Why:** Assistants make checking cheaper, but the medical and legal responsibility stays with the radiologist. The rule is enforced by the system itself, so there is no screen or shortcut that lets an assistant sign.

**Trust is earned, and taken back automatically**
For routine kinds of report, RadReport can earn the right to send reports without a person checking each one, but only after a long, measured track record. A small share is always still checked by a person, and if quality slips, the permission switches off by itself. Earning it is hard. Losing it is instant.

> **Why:** Skipping the check is the biggest time saving and the biggest risk. Earning it needs proof, enough reports and the radiologist's own agreement. Losing it needs nothing: the system watches quality all the time and withdraws the permission the moment it drops.

### For labs and hospitals

**Setting up a new lab in 8 guided steps**
A checklist walks a new lab through everything RadReport needs: the staff list (with their consent), report layouts, past reports, the lab's own medical words, sample recordings, standard "normal" sentences and the rules for urgent findings. A final check says exactly what is still missing before the lab goes live.

> **Why:** How well an AI system works depends mostly on how it is set up. The final check means a lab can't go live with something important missing, and everyone can see what is left to do.

**Learns each lab's words**
Every lab has its own terms, abbreviations and habits. RadReport learns them from the lab's report layouts and past reports, and spots words that sound alike but mean different things (such as two body parts with almost the same name) before they cause a mistake.

> **Why:** General voice typing stumbles on each lab's own words. Catching sound-alike words before they are added stops a confusing pair from ever entering the lab's vocabulary.

**Understands shorthand**
Labs can upload their list of abbreviations ("LLL = left lower lobe"), and RadReport learns to recognise the shorthand when it is spoken, as well as the full words.

> **Why:** Radiologists speak in abbreviations. Without the list, a speech engine hears "LLL" as "eel ell ell", and the finding never reaches the report.

**Knows when two words mean the same thing**
Different doctors say the same thing in different ways. RadReport knows that "hepatic steatosis" and "fatty liver" are the same finding, using a reviewed list of radiology terms.

> **Why:** If "fatty liver" and "hepatic steatosis" were counted as different findings, the lab's statistics would be split and matches would be missed. Using a reviewed list means every pairing has been checked by a person rather than guessed.

**Picks up new words from daily use**
Every night RadReport looks at the words doctors typed into their reports, finds medical terms the lab's vocabulary doesn't have yet ("ground glass opacity", used 5 times) and lists them for a radiologist. One click adds them.

> **Why:** A word list goes out of date the day it is written. Doctors' own corrections are the best sign of what is missing, and a radiologist approves every new word, so nothing is added without a person agreeing.

**Only asks when it isn't sure**
When a spoken phrase sounds like a known term, RadReport decides how sure it is. If it is sure, it uses the term. If it is unsure, it asks a radiologist a simple question ("Is 'plural effusion' the same as 'pleural effusion'?"). If the match is weak, it leaves it alone. Abbreviations need more certainty, because one letter can change the finding.

> **Why:** Asking about everything wastes doctors' time; asking about nothing lets mistakes in. RadReport only asks where it is genuinely unsure, and it counts how often doctors disagree with it, so its judgement can be adjusted over time.

**Works with untidy report layouts too**
Neatly organised report layouts are read instantly. Untidy ones (long paragraphs, bullet lists, tables) are also read by an AI assistant the lab chooses, which can run on the lab's own computers. It may only add sections the document actually mentions, and a radiologist checks every section before the layout is used.

> **Why:** Most layouts are simple and are read for free; only the hard ones need AI. The AI is not allowed to invent sections, and a person approves the result, so a messy layout never turns into a wrong one.

**Hindi, French and Spanish**
Doctors can say or type medical terms in Hindi, French or Spanish, and RadReport turns them into the right English medical term ("गुर्दे की पथरी" becomes "renal calculus", a kidney stone). Each lab chooses its languages.

> **Why:** Many doctors switch between languages as they speak. Turning every term into the same English term keeps one consistent report, whatever language a word was spoken in.

**Every layout change can be undone**
Every change to a report layout is kept as a new version. If a change causes problems, the lab can go back to the previous one in one click.

> **Why:** A bad layout change affects every report written after it. Because old versions are kept, any change can be undone, and every past report still shows the exact layout it was written with.

**Sends reports straight to hospital systems**
Finished reports are produced in the two formats most hospital record systems accept, so they arrive without anyone retyping them.

> **Why:** Hospitals don't change their systems for a new supplier, so RadReport speaks the language they already use. It would rather not send a report at all than send one with a missing patient case number.

**Poor recordings are caught on arrival**
A recording that is too quiet, too short, too noisy or saved in a low-quality format is turned away the moment it is uploaded, with a clear reason. The same recording uploaded twice is recognised and not processed again.

> **Why:** A poor recording becomes a poor report hours later, when it is much harder to fix. Turning it away straight away, with the reason, lets the doctor simply record it again.

### For the people running RadReport

**One place to manage everything**
The team running RadReport sets up labs, staff accounts and permissions from one admin screen, which works on a phone as well as a computer, in light or dark mode. Every important action is written to a record that can't be altered.

> **Why:** "Who changed this, and when?" is the first question a hospital or an inspector asks. The record can be added to but never edited, so the answer can always be trusted.

**The right AI for each job, for each lab**
Writing a report takes several AI-powered steps. Each step can use a different AI, chosen separately for each lab: the most capable one for the important steps, a cheaper one for simple ones. No AI is allowed to work on real reports until it has passed a test against reports known to be correct.

> **Why:** Not every step needs the most expensive AI, but the important ones refuse anything less than capable. The test means switching to a cheaper AI can never quietly make reports worse.

**Costs kept under control**
Every report has a spending limit, and RadReport avoids paying twice for the same AI work. A dashboard for each lab shows what each report costs, which steps cost the most and how that changes over time, and flags any sudden jump.

> **Why:** AI costs grow with every report. A limit stops a single report from running up a large bill, and reusing earlier work keeps the everyday cost low.

**Quality you can measure**
Signed reports are graded on a five-level scale, from "no change needed" to "serious medical error". Quality is tracked all the time, and an early warning is raised if new recordings start to look different from the ones RadReport was set up for.

> **Why:** "It seems fine" doesn't convince a hospital. Grading every report, and comparing the results with the lab's own error rate before RadReport, turns quality into a number that can be tracked and defended.

**A fair contest between speech engines**
RadReport can compare different speech engines on the lab's own recordings and rank them, with a heavy penalty for any engine that adds words that weren't said, however good it is otherwise.

> **Why:** The engine that gets most words right can still be the one that invents findings, so invented words are scored separately. Only recordings from the lab's current microphones count, so the winner is the best engine for the equipment the lab actually uses.

**Adjustable without a software update**
The admin screen lets the team adjust how cautious RadReport is, for all labs or for one: how sure it must be before using a match, when an untidy layout goes to the AI, which languages a lab uses, and how long old data is kept. Every change is recorded.

> **Why:** A lab that has just started needs different settings from one that has used RadReport for a year. Making these settings adjustable means the team can fine-tune them in minutes, and every change can be traced to a person and a time.

**Gets better from approvals, with permission**
Labs that agree can share their approved report layouts and decisions to help train a better layout reader. Only blank layouts and decisions are shared; report text and patient information never are.

> **Why:** Shared examples make RadReport better for everyone, but medical data needs clear permission. The question is asked when a lab joins, when the answer is easiest to give and record.

**A live view of how it's running**
Live dashboards show how quickly every screen and every step of report writing is working, what the AI is costing and how much work is waiting. Problems are reported the moment they happen.

> **Why:** A system you can't see into fails quietly. The dashboards never show patient information or name individual labs, so they can be shared with the team safely.

**Secure sign-in for everyone**
Admins and lab staff each sign in with their own account. Passwords are stored in a scrambled form that can't be read back, sessions end automatically after a while, and an admin can sign a person out of every device at once.

> **Why:** If someone's sign-in were ever stolen, it would stop working within minutes. Repeated wrong guesses are slowed down, and a wrong password and an unknown email get the same reply, so nobody can find out which accounts exist.

**Try it without signing up**
The sign-in page has a **Test credentials** tab with ready-to-use demo accounts. One click fills in the form. Real customer installations don't show it.

> **Why:** Visitors and evaluators shouldn't need an account to look around. The demo accounts can look at every screen but change nothing, and they only exist where they have been deliberately set up.

## Privacy and security

- **Every lab is kept separate.** Each lab's information is locked away from every other lab's at the deepest level of the system, so even a mistake in one screen can't show one lab's reports to another. The tests deliberately try to break this, and fail.
- **Patient consent is recorded.** Permission to use a voice and permission to use data for improvement are recorded separately, with dates, so it's always possible to show what was allowed and when.
- **Recordings are protected.** Audio is stored encrypted and played back through links that stop working after a short time.
- **Passwords to outside services are kept apart** from the rest of the data, in a separate secure store.
- **No real patient information is used while building RadReport.** Developers work only with made-up sample data.
- **Every action is checked.** Each person can do only what their role allows, and unusual bursts of activity are slowed down.

## What's next

- Connecting directly to each hospital's radiology system, once the details are agreed with each hospital
- Connecting to the systems that store the scan images, if labs need it
- A layout reader trained on labs' approved layouts (it's ready to start once enough labs have shared examples)
- Measuring cost and speed in real use at a large hospital

<!-- tab: for-recruiters | For Recruiters -->

## For Recruiters

### Lab screens — signed in as the Auditor (auditor@sunrise.local)

<!-- media: demo-sign-in | Signing in to the demo lab with the Test credentials tab, straight into the review queue -->

### Admin panel — signed in as Support (support@radreport.local)

<!-- media: admin-panel | The read-only admin account: every lab on the platform, then cost and usage -->

## By the numbers

| | |
|---|---|
| **17** | automated steps between "doctor speaks" and "report ready" |
| **11** | AI-powered steps that can each run on a different model, chosen per lab |
| **8** | guided steps to bring a new lab on board |
| **68** | database tables, each lab's rows walled off |
| **1,100+** | automated tests, including tests that try to read one lab's data from another |
| **9 of 9** | deliberate crashes handled in the [crash test](FEATURES.md#crash-test) |
| **500** | users at once in the load test, 99.99% of requests served |
| **2** | hospital data standards supported for sending reports (HL7 v2 and FHIR R4) |
| **3** | languages besides English for medical terms (Hindi, French, Spanish) |
| **~31,000** | lines of code |

<!-- tab: hld | System design -->

## Built to scale

RadReport is designed to grow from one lab to hundreds without a rewrite. These are the techniques that make that possible, in plain words.

| Technique | In plain words | Where RadReport uses it |
|---|---|---|
| **Multi-tenancy** | Many customers share one system, but each only ever sees their own data. | Every lab is isolated inside the database with row-level security. |
| **Database sharding** | Splitting data across several databases so no single one gets overloaded. | Labs can be spread across database shards, and a big lab can be pinned to its own. |
| **Consistent hashing** | A way to decide which shard a lab lives on so that adding a new shard only moves a few labs. | Picks each lab's shard; adding capacity doesn't reshuffle everyone. |
| **Table partitioning** | Splitting one huge table into monthly pieces so searches only look at the months they need. | Speech segments, reviewer edits, the audit log and pipeline step records are split by month, and recordings by lab. New months are added ahead automatically; old months can be detached and archived. |
| **Caching** | Keeping answers to common questions close at hand so they don't have to be worked out again. | AI prompt caching, AI response caching, and per-request caching of lab settings. |
| **Distributed cache (Redis)** | A shared, very fast memory store that every server can read. | Shares lab settings, roles, model choices and admin sessions across all servers, and can hold cached AI answers. |
| **Bloom filter** | A tiny, very fast "have I seen this before?" check that is never wrong when it says "no". | Instantly rules out duplicate recordings and unknown vocabulary words before touching the database. |
| **Message queues** | A waiting line for work, so a burst of uploads is handled steadily instead of all at once. | Each new recording becomes a job that workers pick up when they're free. |
| **Event streaming (Kafka)** | A permanent, replayable log of everything that happened, which many services can read independently. | "Recording uploaded", "draft ready", "report signed" events feed alerts, billing, analytics and hospital export separately. |
| **Transactional outbox** | Making sure a database change and the message announcing it either both happen or neither does. | No signed report can be missed by the hospital export, even if a server crashes mid-way. |
| **Idempotency** | Doing the same thing twice has the same effect as doing it once. | Re-uploading a recording or retrying a failed step never creates duplicates. |
| **Rate limiting** | Capping how often someone can make requests. | Per-user and per-address limits on every route, set in the access policy. |
| **Circuit breaker** | If a service keeps failing, stop calling it for a while instead of piling on. | Stops calling an AI provider that is failing, then tests it again after a cool-down. |
| **Retries with backoff** | Try again after a failure, waiting a little longer each time. | Temporary AI provider errors are retried with growing, randomised waits. |
| **Backpressure** | Slowing down intake when the system downstream is busy. | Caps how many AI and speech calls run at once, per provider. |
| **Connection pooling** | Reusing a small set of database connections instead of opening a new one for every request. | A connection pool in the app plus PgBouncer in front of the database; tested with 500 users at once. |
| **Read replicas** | Copies of the database that handle read-only traffic. | Dashboards, lists and exports read from a replica when one is set up; writes, and anything read right after a write, go to the main database. |
| **Materialized views** | Saving the result of an expensive report query and refreshing it on a schedule. | The evaluation set is pre-computed and refreshed daily. |
| **Vector search** | Finding things by meaning, not exact words. | Matches similar vocabulary terms and routes reports to the right template. |
| **Append-only audit log** | A record that can be added to but never edited. | Every sensitive action is logged; the logging account can't change or delete entries. |
| **Health and readiness checks** | Letting the load balancer know which servers are fit to take traffic. | `/health` says the server is alive and reports each dependency and the server's id; `/ready` checks the database, every shard and the schema version. |
| **Asynchronous processing** | Doing slow work without making anyone wait for it. | AI calls run in parallel, uploads hand the slow work to background workers, and part of the database layer is non-blocking. |
| **CDN** | Copies of the site's files kept close to visitors around the world. | Stylesheets and scripts are cached at the edge for a year; their address changes with every release, so nothing is ever stale. Pages, audio and lab data are never cached. |
| **Observability** | Measuring a running system from the outside: how fast, how busy, what failed. | Prometheus metrics, OpenTelemetry traces and Sentry error reports, with dashboards in Grafana. |

## Seeing inside it

| What | Tool | What it shows |
|---|---|---|
| **Metrics** | Prometheus + Grafana | Requests per second and slowest 5% per route, server errors, rate-limited requests, time per report-writing step, AI spend per hour, prompt-cache share, jobs waiting and their age, unsent events, cache hit rate |
| **Traces** | OpenTelemetry | One request followed through every database query and every report-writing step |
| **Errors** | Sentry | Every unhandled error, with request bodies, messages, cookies and passwords removed first |
| **Synthetic traffic** | k6 on a schedule | A light, steady load against the live demo, so the dashboards always show real numbers |

## Under the hood

**Language & framework:** Python, FastAPI
**Database:** PostgreSQL with pgvector (meaning-based search) and row-level security
**Storage:** S3-compatible object storage for audio
**AI:** Claude models (per-step choice), local open models, Whisper and Deepgram speech recognition
**Standards:** HL7 v2, FHIR R4
**Ops:** Docker, Alembic database migrations, PgBouncer, Redis, Redpanda/Kafka, background workers, Prometheus, Grafana, OpenTelemetry, Sentry, k6, automated test suite with 1,100+ tests

<!-- tab: crash-test | Crash test -->

## Crash test

Good systems are judged by what happens when things go wrong. The crash test breaks RadReport on purpose: it kills a worker in the middle of a job, crashes the message relay at the worst possible moment, takes the database and the cache away, and floods the site. It then records what actually happened. Nothing below is simulated in a slide; every number comes from the last real run.

<!-- include: docs/CRASH_TEST.md -->
