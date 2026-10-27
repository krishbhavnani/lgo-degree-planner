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

Course data is scraped once into `data.js` / `courses.json` by `scrape.py` (Python 3, standard
library only). The snapshot in this repo was pulled **2026-07-30**.

```bash
python3 scrape.py              # uses cached catalog HTML if present in .scratch/
python3 scrape.py --refresh    # re-download the catalog + AAGS list from MIT
```

The scraper pulls the public [MIT Course Catalog](https://student.mit.edu/catalog/) pages and the
EECS [AAGS](https://eecsis.mit.edu/degree_requirements.pcgi?program=AAGS) approved-subject list,
merges in the small public data files below, and writes `data.js`.

| File | What it is |
|------|------------|
| `index.html` | the app (UI + logic) |
| `data.js` | generated: `window.COURSE_DATA`, loaded by the page |
| `courses.json` | the same data as JSON, for inspection |
| `scrape.py` | the catalog + AAGS scraper |
| `al.json` | MIT Sloan Action Learning labs (lab codes, terms) |
| `design.json` | LGO pre-approved design classes (approved / conditional) |
| `extra.json` | hand-added special subjects not in the main catalog pages |
| `evals.json` | workload hours from MIT subject evaluations (most recent report per course) |

To add a department, add an entry to the `DEPARTMENTS` list at the top of `scrape.py` and re-run it.

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

- MIT Course Catalog — `student.mit.edu/catalog`
- EECS AAGS approved-subject list — `eecsis.mit.edu`
- LGO Online Handbook (degree requirements, pre-approved design classes)
- MIT Sloan Action Learning booklet

All course content belongs to MIT and its departments; this tool only reorganizes publicly listed
information for planning convenience.

---

## Status

Early public version. Feedback and requirement corrections from LGO students across majors are
welcome — please open an issue.
