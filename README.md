# LGO Degree Planner

A fast, offline-friendly dashboard for **MIT Leaders for Global Operations (LGO)** students to
browse graduate courses, plan a two-year schedule term by term, and track progress toward the dual
**SM + MBA** degree requirements — all in a single HTML page with no sign-in and no server.

> **Planning aid, not an official degree audit.** This tool is unofficial and may contain errors or
> stale data. Always confirm requirements and course details against the
> [MIT Course Catalog](https://student.mit.edu/catalog/), your department, and the LGO program
> office before registering.

---

## What it does

**Browse** — 730 graduate subjects across the departments LGO students most commonly draw from:

| Dept | Courses | Covers |
|------|--------:|--------|
| Course 6 — EECS | 158 | engineering electives, AAGS core |
| Course 15 — Management (Sloan) | 396 | MBA core, LGO-required, MBA electives |
| Course 2 — MechE | 170 | non-EECS engineering electives |
| Common Ground for Computing (other depts) | 6 | 6.C51 co-requisite modules and similar |

For each course: number, title, category, term offered, offering status (e.g. *not offered this
year*), units (and total), prerequisites (resolved to names), parsed schedule, description,
instructor, **AAGS** approval status (taken only from the EECS AAGS page), and **workload** —
average weekly hours in and out of class from MIT subject evaluations, with a Light → Very Heavy
difficulty label (about 400 EECS and Sloan courses have evaluation data). Filter by department, term, offering, category, AAGS,
unit range, **🎨 pre-approved design classes**, and **🧪 Action Learning labs**; search and sort on
any column; show/hide columns.

**Plan** — switch to the Plan tab for a sandbox schedule:

- An 8-term grid (Summer → Spring across two years) plus an "Unassigned" holding area. Courses in
  Unassigned don't count toward requirements until you place them in a term.
- Starts from a **base plan of LGO-required courses**. Required courses with a flexible term
  (15.769 Operations Strategy; the second 15.792 seminar — both Spring 2027 or Spring 2028) start in Unassigned: they
  can't be removed, and can only be scheduled in their allowed terms. Base-plan courses keep their
  requirement designation (tags can't be changed); courses you add are fully editable.
- Each term shows its total units (every course counts) and flags anything over **72 units**.
- Add any catalog course (or a custom one), move it between terms, set units, add tags, or mark it
  as **audit** (shown but not counted toward credit).
- A live **requirements tracker** for the LGO dual degree:
  - **MBA** — core (36u) + LGO-required (71u) + free electives (≥49u) = **156u**
  - **EECS SM** (mirrors the LGO handbook, Appendix 5A) — AAGS core (3 AAGS-approved courses / 36u)
    + LGO-required eng (24u) + eng electives beyond the AAGS core (≥6u) = **≥66u**. 6.C51 taken with
    a 6u co-requisite module (e.g. 15.C51) counts as one 12u AAGS course.
  - **SM thesis** (24u), **Python** (6.S090), and the **LGO Design** requirement
  - Pre-approved design courses satisfy the Design requirement automatically.
- Requirement targets are **editable** (and resettable to defaults), so the model isn't locked in.
- Export or import your plan as JSON.

Everything you do — your plan, flagged courses, column preferences, and requirement edits — is saved
in your browser's `localStorage`, so each visitor gets their own private dashboard.

---

## Quick start

No build step. **Open `index.html` in any modern browser** (double-click it, or serve the folder
over `http://` if you prefer). It loads `data.js` and runs entirely client-side.

---

## How the data is built

Course data is built into `data.js` / `courses.json` by `scrape.py` (Python 3; standard library
plus `pypdf` for one PDF, see `requirements.txt`). Nothing is maintained by hand: every source has
a fetcher in `pipeline/sources/`.

```bash
pip install -r requirements.txt
python3 scrape.py --refresh    # fetch everything live from MIT, check, publish
python3 scrape.py              # rebuild from the locally cached pages
python3 -m unittest discover -s tests -t .
```

| Source | What it provides |
|--------|------------------|
| [MIT Subject Listing](https://student.mit.edu/catalog/) | every graduate subject, terms, units, schedule, offering status; the academic year is read from the pages |
| MIT Subject Listing index | department names for subjects outside the scraped departments |
| EECS [AAGS](https://eecsis.mit.edu/degree_requirements.pcgi?program=AAGS) list | AAGS approval (the only source for it) |
| EECS [subject updates](https://www.eecs.mit.edu/academics/subject-updates/) | this and next term's EECS special subjects (all graduate ones) |
| LGO handbook, Appendix 2 | pre-approved and conditionally approved design classes |
| MIT Sloan [Action Learning](https://mitsloan.mit.edu/action-learning) course booklet | which courses are Action Learning labs |
| `evals.json` | workload hours from MIT subject evaluations (refreshed once per term by a logged-in run; only the extracted hours are published) |

**Guardrails.** Every run checks what it fetched before publishing anything: pages returned and
complete, no login pages, catalog pages from the same day, course counts not down more than 30%
from the last good run, required fields present. If the catalog or AAGS checks fail, nothing is
written. If one of the other sources breaks (a page redesign, a late booklet), the run keeps that
source's last good data, still publishes, and exits with a warning.

**History.** Raw copies of every page are archived on the
[`data` branch](https://github.com/krishbhavnani/lgo-degree-planner/tree/data) (saved only when
they change), along with the parsed data per source.

**Known limitation.** The Action Learning booklet is the only source that marks courses as labs.
Regular-numbered labs stay labs from year to year without it, but a brand-new lab, or a lab that
runs under a special-subject number (15.Sxx), is only picked up once Sloan publishes the booklet.

To add a department, add it to `CATALOG_DEPARTMENTS` in `pipeline/config.py` and re-run.

---

## Notes & limitations

- **Requirement model.** The built-in requirement tracker reflects the **LGO EECS SM + MBA** dual
  degree. Courses from other departments are browsable and plannable as electives, but per-major
  requirement models for other engineering programs aren't built in yet.
- **Term labels** currently span a fixed two-year window and fit one cohort at a time.
- **Workload data coverage.** Hours come from the most recent MIT subject-evaluation report for each
  course, which may reflect a different instructor or year (the *Eval match* column flags this; a `*`
  marks small response counts). MechE, Common Ground and brand-new special subjects have no
  evaluation data yet.
- **No ratings.** Subjective "worth-taking" ratings are personal and are not included; the Rating
  columns are empty. Letting users import their own ratings/notes is on the roadmap.

---

## Data sources

See [How the data is built](#how-the-data-is-built). All course content belongs to MIT and its departments; this tool only reorganizes publicly listed
information for planning convenience.

---

## Status

Early public version. Feedback and requirement corrections from LGO students across majors are
welcome — please open an issue.
