# 18. Satisfy the gate by changing the code, not the thresholds

Status: accepted

## Context

Adopting the Codeforge gate (ADR 0016) surfaced 1930 lint findings, an unannotated
package, eleven modules below the maintainability floor, twenty-three functions over
the cognitive-complexity limit, and 83% test coverage against a 100% floor. Every one
of those numbers could be made green either by changing the code or by moving the
threshold, and the two are not equivalent.

## Decision

The code changes; thresholds move only where the metric measures something other than
what it claims to.

Types are now complete: every function and method in `src/` and `tests/` carries
parameter and return annotations, `mypy --strict` and `pyright` in strict mode both
pass, and decoded instance JSON is named `Any` in one place — `gaxi.jsonshape` — so
the admission is visible rather than scattered. The Swagger value objects became
dataclasses, which removed the eleven- and twelve-argument constructors along with
their boilerplate.

Four modules were split, each along a seam the metric only made visible:
`gaxi.capability` holds the capability model that `gaxi.swagger` compiles into;
`gaxi.results` holds result shaping, which the invoker no longer owns;
`gaxi.invocation` holds the two values both of those need; and `gaxi.jsonbody` holds
whole-body validation. Twenty-three functions were decomposed to reach the cognitive
limit of nine.

Coverage is 100% of statements and branches, reached by writing tests rather than by
lowering the floor. Four unreachable branches were deleted instead of being covered:
the transport's non-GET redirect path (only GET is ever redirected, and every other
method is a mutation, which is refused earlier), the catalog's second selector match,
and two trailing returns after loops that always return or raise.

Two thresholds moved:

- `mi_floor` is 20, Radon's own A/B boundary, not the default of 40. The
  maintainability index falls with module length regardless of how clear a module
  is, so a floor of 40 forces modules to be split by line count rather than by
  responsibility. Every module ranks A; the lowest scores 24.
- `reportPrivateUsage` is off in Pyright and enforced by Ruff's `SLF001` instead,
  because Ruff can distinguish directories: product code may not reach into another
  module's privates, while a white-box test may address the unit's own helpers.

`D107` is ignored (a class documents its own construction), `max-args` is 8 with
`max-positional-args` left at 5 (so anything wider must be keyword arguments), and
the test suites additionally ignore the rules that only make sense for product code.
Each ignore carries its reason in `pyproject.toml`.

## Consequences

The first run of a new gate is a design review, and it should be answered as one. The
one place this cost real behaviour was `--save`: the classifier drained the response
before the writer saw it, so streaming never streamed. Coverage found it because the
streaming branch was unreachable; `--save` now writes a successful response straight
through, and only failures and redirects reach the classifier.

The thresholds that moved are documented in `pyproject.toml` next to their values, so
a later reader can disagree with a reason rather than with a number.
