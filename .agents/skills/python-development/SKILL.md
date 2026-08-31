---
name: python-development
description: >-
  Python engineering standard for typed, gated, property-tested code: strict
  typing rules, hypothesis-first testing, per-package coverage and complexity
  floors, quality-gate discipline, and module style. Use when writing, editing,
  refactoring, testing, or reviewing Python in a project that enforces a quality
  gate, and when deciding how to structure packages, tests, or automation tasks.
  Not for choosing a web/data framework and not for non-Python code.
user-invocable: false
---

# Python development standard

Reference conventions applied while doing other Python work. They assume a
`src/` layout, a lockfile-managed environment, and a single command that runs
the whole quality gate.

Boundaries: TDD loop mechanics live in the `tdd` skill; bug-hunting test design
in `qa-tester`; review classification in `code-review`. This skill supplies the
constraints those workflows must satisfy in Python.

## Discover before applying

These are defaults, not overrides. Before enforcing a rule, read the project's
`pyproject.toml`, agent instructions, and task namespace (`invoke --list`), and
follow the project's actual thresholds, tool set, and task names. Where the
project is silent, use the values below.

**pyinvoke is the automation framework.** `invoke check` is the gate;
`invoke ci` adds security. No make, no pre-commit, no nox, no loose `scripts/`
directory — a Makefile or shell script doing gate work is something to port
into a task, not a pattern to follow. `tasks.py` puts `src/` on `sys.path`, so
a bare `invoke` works; prefer `uv run invoke …` when the venv may be stale.

## Non-negotiables

1. **Types everywhere.** Every function, method, and module-level name is
   annotated. `mypy --strict` and `pyright` strict must both be clean. No bare
   `Any`, no untyped `dict[str, Any]` crossing a module boundary — parse into a
   dataclass or pydantic model at the edge. `# type: ignore` requires an error
   code and a comment saying why; ruff's `ANN` rules are never silenced.
2. **Property-based testing first.** Reach for a hypothesis property before an
   example test. Write examples only for what a property cannot state: a named
   regression, an exact rendered string, a concrete boundary worth naming.
   State the invariant, let hypothesis pick the data, add a regression example
   when it finds a failure. Keep `filterwarnings = error` and `xfail_strict` on.
3. **Tests partitioned by package, then by kind** —
   `tests/<package>/{unit,properties}/`. A package's tests import only that
   package. Test support that a package's *users* would want ships inside the
   package (hypothesis strategies, recording/fake contexts), never in a shared
   `tests/` module. Root `conftest.py` holds hypothesis profiles only;
   per-package fixtures go in `tests/<package>/conftest.py`. Suffix property
   modules `_properties.py` so no two test modules share a basename — mypy
   resolves modules by path.
4. **Per-package coverage floors,** not a repo-wide average: a well-tested
   package must not mask a thin one. Lower a floor deliberately, in a commit
   that says why.
5. **Complexity ceilings.** CRAP ≤ 10 (`cc² · (1−coverage)³ + cc`), cyclomatic
   ≤ 10, cognitive ≤ 9, maintainability index ≥ 40. Fix by splitting the
   function or covering the branches — never by raising the limit. See
   [reference.md](reference.md) for what each metric actually catches.
6. **Security gates block.** bandit and a dependency auditor (pip-audit) fail
   the build. No secrets in the repo; credentials come from `.env` / env vars,
   with a checked-in `.env.example`.
7. **Dead code is deleted, not commented out.** vulture runs in the gate; git
   remembers the old version.
8. **No loose scripts.** An unimported script is untyped by the gate, untested,
   and uncallable from another task. Every gate is a pure `(root) -> Report`
   function in a real, tested package that a thin invoke task body hands to a
   shared `emit`. Metric gates run in-process, not as subprocesses.
   Generic file checks (merge markers, private keys, oversized files, trailing
   whitespace, parseable config) belong in that package over `git ls-files`
   rather than in a second tool's config, and waivers name the rule
   (`# hygiene: allow <rule>`) so they are never blanket.

## Gate discipline

- The gate must be green before any commit. Never `git commit --no-verify`; a
  hook bypass env var, if the project has one, is justified in the commit.
- Never run raw `pip`. Dependencies go through the project's manager (`uv add` / `uv add --group dev`) so the lockfile stays authoritative.
- Run type checkers and tools through the project runner (`uv run …`); no `venvPath` is pinned and the environment path may not be `.venv`.
- Tests must never hit the network — mark anything that would
  (`@pytest.mark.network`) and keep it out of the default run.
- Untyped third-party APIs get one typed facade module that is the only importer of that library, with a scoped `# pyright:` header relaxing the unknown-type rules. Everything else stays strict.

## Style

- **`from __future__ import annotations`: deliberate, not reflexive.** On 3.13,
  `list[str]` and `X | Y` already work in annotations without it, so the
  remaining reasons are narrow — unquoted forward references, and importing
  types under `if TYPE_CHECKING:` to break a cycle or cut import cost. Add it to
  a module that needs one of those. Do not add it to a module whose annotations
  are resolved at runtime (pydantic models, third-party `get_type_hints`,
  typer/FastAPI signatures) unless every name in them is importable at module
  scope; stringized annotations fail to resolve otherwise, and the error appears
  far from the import. PEP 649 makes annotations lazy by default from 3.14,
  which retires the import — a codebase that applied it per-need has less to
  unwind.
- Frozen `@dataclass(slots=True)` for value objects; pydantic only where input is untrusted (config, external payloads).
- Google-style docstrings on public functions; ruff formats (line length 100).
- Prefer pure functions over classes-with-state; keep I/O at the edges so the core is trivially testable.
- Data-handling rules (money as `Decimal`, tz-aware UTC boundaries, raise rather than silently repair bad input) are in [reference.md](reference.md).

## Before handing work back

- `invoke check` green, including per-package coverage and every metric floor.
- New public names annotated and documented; no new `# type: ignore` without a code and reason.
- Each new invariant has a property test; each fixed bug has a regression example.
- No new loose script, no dead code left commented out, no new dependency added outside the lockfile.
