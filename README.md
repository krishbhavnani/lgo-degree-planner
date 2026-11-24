# LGO Degree Planner

A course planner for **MIT Leaders for Global Operations (LGO)** students: browse graduate courses,
lay out your two years term by term, and track progress toward the dual **SM + MBA** degree. It runs
in your browser with no sign-in, and the course data refreshes itself from MIT every week.

**Live site: <https://krishbhavnani.github.io/lgo-degree-planner/>**

> **Planning aid, not an official degree audit.** This tool is unofficial and can be wrong or out of
> date. Confirm requirements and course details with the LGO program office, your department and the
> [MIT Subject Listing](https://student.mit.edu/catalog/) before you register.

---

## Using the planner

### Browse

743 graduate subjects from the departments LGO students draw on most: Course 15 (Sloan, 401),
Course 2 (MechE, 171), Course 6 (EECS, 162), plus Common Ground modules and the EECS special
subjects that other departments list. A special subject (a number like 15.S04 that carries a
different topic each term) gets one row per topic.

For each course you see the title, research area, units, schedule, prerequisites, instructor and
description, and:

- **Your terms:** your current and upcoming terms (from your plan's graduation year) in which the
  course is offered, each with a badge. A term the course isn't offered in doesn't appear. The
  **Key** button above the table explains the badges, and hovering a badge gives the details:

  | Badge | Meaning |
  |---|---|
  | ✓ | Offered: on MIT's schedule for that term |
  | ~ | Likely offered: usually offered then, but MIT hasn't posted that term's schedule yet |
  | ? | Check with the department: offered irregularly |

- **AAGS** status, taken only from the EECS AAGS list. EECS special subjects whose EECS page says
  "AAGS in …" but that aren't on the list show **"AAGS ? needs approval"**: you decide whether to count
  them (see Plan).
- **Workload:** average weekly hours in and out of class from MIT subject evaluations, with a
  Light → Very Heavy label (about 360 courses). *Eval match* flags when the evaluation was for a
  different instructor; `*` marks fewer than 5 responses.
- Marks for **🎨 LGO pre-approved design classes** (faded: conditionally approved) and
  **🧪 Action Learning labs**, and an **H1/H2** chip for half-term courses.

Filter by department, **Offered in** (any of your terms), AAGS, design, Action Learning, research
area, units and weekly hours; search; sort any column; show or hide columns. Browse lists courses
offered now or later; tick *Include not currently offered* to see the rest, dimmed, with the reason.
Star courses (★) and export the starred ones as CSV. **＋** adds a course to your plan.

### Plan

- **Your graduation year.** The first time you open Plan it asks which class you're in
  ("Graduating 2028" = Summer 2026 → Spring 2028). Change it any time from the Plan header; every
  term relabels and your courses move with them. Years on offer: the incoming class and the three
  before it.
- **The base plan.** Your plan starts with the LGO-required courses in their usual terms. Two
  required courses have a choice of term: the second 15.792 seminar starts in year-1 Spring and
  15.769 starts in *Unassigned*; each can only go in its allowed terms (year-1 or year-2 Spring).
  Base-plan courses keep their category.
- **Adding courses.** *＋ Add course* searches the catalog; each result shows its badge for the term
  you're adding to, best first. For a term that's already over, only courses offered that term are shown.
  You can also type in a course that isn't in the catalog. *＋ Placeholder* holds a spot ("MBA
  Elective placeholder, 9u") for a course you haven't picked yet; it counts like a real course.
- **Each course** shows its badge for its term (✓ ~ ? as above, ✕ not offered; the **Key** button
  explains them). Pick which requirement it counts toward (one
  category per course), toggle **LGO Design**, change its units, move it, or mark it **audit**
  (shown, not counted). Courses in *Unassigned* don't count until you place them.
- **AAGS on your own call.** A special subject (or a course EECS describes as AAGS but that isn't
  on the list) has a **"+ AAGS?"** toggle. Turn it on to count the course toward the AAGS core; it's
  marked *AAGS (your call)*, and the AAGS requirement reminds you to get it approved.
- **Terms** show their total units and flag anything over **72 units**. Terms with half-term courses
  also show the load in each half (H1 / H2).
- **Requirements tracker,** live as you edit:
  - **MBA:** core (36u) + LGO-required (71u) + free electives (≥49u) = **156u**
  - **EECS SM:** AAGS core (3 AAGS courses, 36u) + LGO-required engineering (24u) + engineering
    electives beyond the AAGS core (≥6u) = **≥66u**. 6.C51 taken with one 6u co-requisite module
    (e.g. 15.C51) counts as a single 12u AAGS course.
  - **SM thesis** (24u), **Python** (6.S090), and **LGO Design** (a pre-approved design course
    fulfills it automatically).
  - Targets are editable under *⚙ Requirements* (and reset to the defaults).
- **Export / Import** your plan as a file; *Reset* returns to the base plan; *Start blank* clears
  everything except the required courses.

### Your data

Your plan, stars and column choices are saved in your browser only (`localStorage`); nothing about
your plan is sent anywhere. Plans saved by earlier versions of the site are converted automatically
the first time you open the new one (the original is kept in your browser). The site counts visits
anonymously (GoatCounter, no cookies).

---

## What it can't do (yet)

- **It isn't an official audit.** Rules are modeled from the LGO handbook and program material and
  can be incomplete; a few details are still being confirmed with LGO staff (for example, whether
  pass/fail classes count toward credits, and the exact MBA free-elective total).
- **One major:** the requirement tracker models **EECS SM + MBA**. Other engineering majors can browse
  and plan courses as electives, but their requirements aren't modeled yet.
- **Course coverage:** Course 6 subjects listed only on catalog page m6e (about 84, e.g. Gordon
  Engineering Leadership) aren't included yet. The EECS IAP offerings page and next spring's EECS
  subject updates aren't read yet; IAP courses come from the MIT catalog only.
- **Terms before Fall 2026** have no catalog record (tracking began then), and MIT hasn't published
  terms beyond the current catalog. Courses in those terms get no badge; the term's header says why.
- **6.C51 pairing** is simplified: a module without 6.C51 still counts as an engineering elective.
- **Workload hours** come from the most recent evaluation and may reflect another instructor or
  year. MechE, Common Ground and new special subjects mostly have none; special-subject hours only
  show when the evaluation's title matches the topic.
- **Action Learning labs** come from Sloan's yearly booklet: a brand-new lab, or one running under a
  special-subject number, appears only once the booklet is published.
- Not designed for phones yet.

---

## What's next

1. **Feedback from LGO staff and a demo with EECS students,** who enter their real plans and check
   the totals. Their corrections come first.
2. **One-category model, finished:** LGO Design only alongside an elective; conditionally approved
   design courses shown as an indicator only.
3. **More EECS courses:** the m6e catalog page, the spring EECS subject updates and the EECS IAP
   list as soon as MIT publishes them.
4. **Handoff:** a maintainer guide (refreshes, the once-a-term evaluation run, adding a major).
5. **A second major.**

---

## How it's built (for maintainers)

The site is static: `index.html` plus plain JavaScript in `app/` (no build step, no npm) and three
generated files:

| File | What it holds | Made from |
|---|---|---|
| `db.js` | every course and its term offerings, statuses, designations, eval hours | the course database on the [`data` branch](https://github.com/krishbhavnani/lgo-degree-planner/tree/data) |
| `changes.js` | the recent change feed (courses added, dropped, changed) | the same branch |
| `programs.js` | the degree rules | `programs/lgo.json` (shared LGO rules, base plan, terms) and `programs/eecs.json` |

Code: `app/catalog.js` reads `db.js`; `app/engine.js` evaluates requirements from the program files
(pure functions, tested in node); `app/state.js` is the saved plan; `app/browse.js` and
`app/plan.js` are the two tabs. **Degree rules live only in `programs/*.json`**; a test fails if a
course number or category name appears in the app code.

### The data pipeline

`scrape.py` (Python 3, standard library plus `pypdf`) fetches every source politely, parses it,
checks it, archives it and merges it into the course database. Nothing is maintained by hand.

| Source | What it provides |
|---|---|
| [MIT Subject Listing](https://student.mit.edu/catalog/) | every graduate subject: terms, units, schedule, offering status; the academic year is read from the pages |
| MIT Subject Listing index | department names for subjects outside the scraped departments |
| EECS [AAGS](https://eecsis.mit.edu/degree_requirements.pcgi?program=AAGS) list | AAGS approval (the only source for it) |
| EECS [subject updates](https://www.eecs.mit.edu/academics/subject-updates/) | this and next term's EECS special subjects; their "AAGS in …" wording is kept as a note, never as approval |
| LGO handbook, Appendix 2 | pre-approved and conditionally approved design classes |
| MIT Sloan [Action Learning](https://mitsloan.mit.edu/action-learning) booklet | which courses are Action Learning labs |
| MIT subject evaluations | workload hours (refreshed once per term by a logged-in run; only the extracted hours are published) |

- **Weekly refresh:** GitHub Actions runs `scrape.py --refresh` every Monday (08:00 UTC), commits the
  results to the `data` branch and redeploys. Pushes to `main` redeploy from the stored data.
- **Guardrails:** every run checks what it fetched before publishing: pages returned and complete,
  no login pages, catalog pages from the same day, course counts not down more than 30%, required
  fields present. If the catalog or AAGS checks fail, nothing is published. If another source breaks,
  the run keeps that source's last good data, publishes, and fails the job so the maintainer is
  emailed.
- **History:** raw copies of every page (saved only when they change), the parsed data per source,
  the course database and its change feed all live on the `data` branch.

### Running it locally

```bash
pip install -r requirements.txt
git worktree add .data data          # the data branch
python3 scrape.py --from-archive     # write db.js, changes.js, programs.js (fetches nothing)
open index.html                      # or serve the folder over http
python3 scrape.py --refresh          # fetch live from MIT, check, archive, update the database
python3 -m unittest discover -s tests -t .   # Python tests
node --test tests/js/*.test.js               # JS tests: requirement goldens, saved plans, rules
```

To add a department, add it to `CATALOG_DEPARTMENTS` in `pipeline/config.py`. To change a degree
rule, edit `programs/*.json`; the JS tests check every reference.

---

All course content belongs to MIT and its departments; this tool only reorganizes publicly listed
information for planning. Questions or corrections: open an issue on this repository.
