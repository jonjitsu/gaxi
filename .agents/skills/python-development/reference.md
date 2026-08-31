# Python development reference

Depth behind the rules in [SKILL.md](SKILL.md). Look things up here; do not
restate this in code comments.

## What each metric catches

| Metric | Limit | Signal |
|---|---|---|
| CRAP (`cc² · (1−coverage)³ + cc`) | 10 | Risk: complex code is allowed only when thoroughly tested |
| Cyclomatic complexity | 10 | Number of independent paths through a function |
| Cognitive complexity | 9 | How hard the code is to *read*; charges a nesting penalty per level |
| Maintainability index (radon) | 40 | Size and density (Halstead volume, length, comments) — a module has sprawled and wants splitting |
| Per-package coverage | project floor (often 100%) | Thin packages cannot hide behind well-tested ones |

Cyclomatic and cognitive complexity disagree on purpose. A flat chain of guard
clauses is cheap cognitively and dear under cyclomatic counting; a
triple-nested loop is the reverse. Cognitive 9 is deliberately tighter than the
common published default of 15, and tighter than the cyclomatic ceiling.

Maintainability index is a size signal, not a risk signal — CRAP covers risk. A
maintainability failure means "split this module", not "add tests".

## Gate ordering

Run cheap, high-signal checks first so failures surface fast:

hygiene → lint → types → dead code → maintainability → cognitive → tests →
coverage → CRAP.

Coverage-derived gates (coverage floors, CRAP) require a prior test run that
produced coverage data; they are not standalone entry points.

## Hypothesis profiles

Define named profiles in the root `conftest.py` and select with an env var:

- `dev` — ~50 examples, the default for local loops
- `ci` — ~300 examples, derandomized
- `thorough` — ~2000 examples, for deliberate soak runs

Property suites that carry a heavy budget get their own task so the default
test run stays fast.

## Three-layer automation structure

When the project's gates live in a real package rather than a single task file:

1. **Pure builders** — functions that construct a command string or a `Report`,
   with no shell and no I/O. All logic lives here; tested by asserting on the
   returned value.
2. **Typed facades** — one module per untyped third-party API (invoke itself,
   radon, complexipy). Invoke ships no types, so a `_invoke.py` re-declares
   `@task` as signature-preserving and is the single file that imports
   `invoke.tasks`; metric facades return a shared `CodeBlock`. These are the
   only modules importing those libraries and the only place unknown-type rules
   are relaxed, via a scoped `# pyright:` header.
3. **Thin task bodies** — one-line wrappers that hand a pure function's
   `Report` to a shared `emit`, grouped one module per invoke sub-namespace.
   Tested against a recording context that subclasses `invoke.Context`; a plain
   stub is rejected because invoke type-checks a task's first argument.

`tasks.py` stays a two-line shim that imports the namespace.

## Data-handling conventions

Apply when the project handles money, measurements, or time series:

- **Money is `Decimal`**, never float, in domain objects and any P&L or
  accumulation. Convert to float only inside a numeric kernel, at the last
  moment.
- **Timestamps are timezone-aware UTC** at the boundary. Convert to a local
  zone only for session or calendar logic, and store the derived local session
  date alongside the timestamp rather than recomputing it downstream.
- **Never silently forward-fill or drop bad records.** Validation failures
  raise a named domain error so analysis does not quietly run on garbage.
- **No lookahead.** A computation at step *t* may read only data through step
  *t*; effects land at *t+1* or later. Any new primitive that could leak future
  data needs a property test asserting it does not.
- **Derived values stay derived.** Reproduce them from a stored snapshot rather
  than mutating them in place.

## Vendor and external integrations

Each vendor or external service lands as its own module behind a `Protocol`,
plus its own optional extra in `pyproject.toml`, so the core installs without
vendor SDKs. Record a vendor constraint that forces an unwanted transitive
dependency in an ADR rather than in a code comment.

## Disabled tools

When a gate tool cannot run in the project's environment, wire it out of the
gate rather than deleting it: leave the on-demand task in place with a
preflight that prints what to do instead of a raw error, comment (do not
delete) the CI job, and record in one place exactly what to change to
re-enable it.
