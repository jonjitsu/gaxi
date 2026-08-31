# Changelog

## Unreleased

- Renamed the bridge to `gaxi`: the console script, the import package, the
  `GAXI_*` environment variables, and the `.gaxi-cache` directory all change with
  no compatibility alias (ADR 0017).
- Raised the supported interpreter floor to Python 3.13 (ADR 0016).
- Replaced the Makefile and `scripts/` with the `python-codeforge` Invoke gate:
  `uv run invoke verify` runs the quality gates and the CLI-documentation
  freshness check (ADR 0016).
- Moved the suites to `tests/gaxi/{unit,properties,integration}` under pytest,
  with the live-instance suite marked `network`.
- Annotated the whole package and both suites; `mypy --strict` and `pyright` in
  strict mode pass (ADR 0018).
- Split `gaxi.capability`, `gaxi.results`, `gaxi.invocation`, and `gaxi.jsonbody`
  out of the modules that had accumulated them (ADR 0018).
- Renamed `GaxError` to `GaxiError`, completing the rename in ADR 0017.
- `--save` now streams a successful response straight to disk; the classifier no
  longer drains the body first (ADR 0018).
- Raised statement and branch coverage to 100% and removed four unreachable
  branches the coverage run exposed (ADR 0018).
- A path that carries an origin (`gaxi get https://host/api/v1/user`) is still
  refused, but the suggested command is now directly runnable: it drops the origin
  and, when the catalog is reachable, the instance base path too. Previously it
  prefixed a slash to whatever was typed.
- A path that repeats the instance base path (`/api/v1/user`) names that as the
  reason and suggests the capability it would have matched.

## 1.0.0

First implementation of the clean-sheet design.

- Hybrid capability model: Swagger 2.0 compilation, versioned semantic policy,
  runtime inspection, conservative fallback, and origin-scoped overlays.
- Verb commands (`get`, `post`, `put`, `patch`, `delete`) over concrete
  API-relative paths, with `--as`/`--operation` disambiguation.
- Schema-routed `name=value` input binding, `query:`/`body:`/`form:` qualifiers,
  repeated array assignments, file inputs, and `--input-json`.
- Independent `effect`, `confirmation`, and `retry` properties; `--yes`,
  `--allow-unknown`, and `--dry-run`; no interactive prompts.
- Content-first TOON results with `--output json|yaml`, a 160-character
  truncation contract, `--fields`, `--full`, and bounded pagination defaults.
- Explicit transport modes: structured text, `--raw`, `--save` with atomic
  rename and a receipt, bounded GET redirects, and refused mutation redirects.
- Discovery surface: live home view, `capabilities`, `capability`, `context`,
  `skill`, `setup`, and `auth`.
