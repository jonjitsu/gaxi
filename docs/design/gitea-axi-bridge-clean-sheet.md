# Gitea AXI bridge — clean-sheet design

**Status:** Design complete
**Started:** 2026-08-30
**Inputs:** repository AXI contract, live instance Swagger, observed HTTP behavior

This document intentionally does not inherit the structure or conclusions of `gaxi.md`. It starts from the interface contract and evidence exposed by the target instance.

## Evidence from the reference instance

The reference instance reports Gitea 1.27.2. `/api/swagger` is an HTML discovery page whose `data-source` points to `/swagger.v1.json`; that document is Swagger 2.0 with base path `/api/v1`.

The document contains:

- 308 paths and 482 operations: 243 GET, 97 POST, 27 PUT, 32 PATCH, and 83 DELETE;
- a unique, non-empty `operationId` for every operation;
- 956 path parameters, 412 query parameters, 121 JSON body parameters, and 3 file-upload parameters;
- 103 operations with a `page` parameter;
- JSON, plain text, HTML, binary file, redirect, and empty status-only responses;
- seven globally declared authentication schemes but no operation-level overrides, even though some live operations allow anonymous access.

After resolving reusable response references one level, 118 operations advertise array responses and 201 advertise referenced object responses, while 148 successful responses expose no usable schema. Only three paginated response definitions declare a total header. In contrast, a live anonymous request to `/api/v1/repos/search?limit=2` returned `X-Total-Count`, although its operation does not document that header.

These observations establish two constraints:

1. Swagger is strong enough to discover and bind capabilities, but not strong enough to determine all output, authentication, pagination, and mutation semantics.
2. Runtime behavior must never be presented as if it were guaranteed by the schema; the bridge needs explicit known/unknown states.

## Settled decision

The bridge uses a hybrid capability model ([ADR 0001](../adr/0001-use-a-hybrid-capability-model.md)):

- the instance description is authoritative for which capabilities exist and how requests are encoded;
- versioned Gitea semantic policy supplies known domain meaning missing from the description;
- runtime inspection supplies facts such as actual content type and total-count headers;
- conservative fallback keeps an unknown capability invocable without pretending its semantics are known;
- instance-local policy may correct a server fork or deployment without changing the binary.

## First-principles interface constraints

The eventual command design must satisfy these constraints:

- **One stable address per capability.** Discovery output must provide a value that can be passed back without guessing or normalization.
- **No fabricated certainty.** Unknown totals, response shapes, authentication requirements, or mutation risk must be named explicitly.
- **One structured stdout contract.** Successes, empty results, validation failures, HTTP failures, redirects, and saved binary responses must all be distinguishable without consulting stderr.
- **Bounded defaults.** Discovery and API collections must have deterministic page sizes and at most four default fields.
- **Schema-aware validation.** Unknown parameters and invalid enum/type values fail before a mutation is sent when the description contains enough information to validate them.
- **Explicit mutation risk.** Destructive calls and mutations with unknown semantics never depend on an interactive prompt.
- **Credential-safe rendering.** Authentication material used by the bridge is never emitted through results, dry runs, errors, generated help, or debug logging; values intentionally returned by an invoked API remain response data.
- **Transport fidelity.** Text, uploads, downloads, empty responses, and redirects are first-class cases rather than accidental JSON fallbacks.
- **Context is observable.** Any value supplied from repository, instance, environment, or configuration context is visible in dry-run or capability-detail output before execution.
- **Help is executable.** Suggested next actions carry fixed context and use placeholders only for values still required.

## Candidate internal boundary

The smallest architecture consistent with those constraints has six stages:

```text
instance discovery → description compiler → capability catalog
                                            + semantic policy
request intent     → validated invocation  → HTTP exchange
HTTP exchange      → response classifier   → AXI renderer
catalog + result   → next-action planner    → help[]
```

The description compiler produces a normalized capability catalog rather than exposing Swagger objects directly. The semantic policy decorates catalog entries; it cannot invent a capability absent from the connected instance. The response classifier uses both the advertised response and the actual status, headers, and content type. Rendering occurs only after classification.

## Decision 1: request grammar and capability resolution

The primary invocation is an HTTP verb subcommand followed by one concrete API-relative path:

```text
<cli> get /repos/acme/widgets/pulls
<cli> patch /repos/acme/widgets/issues/42
<cli> delete /repos/acme/widgets/issues/comments/17 --yes
```

The path begins with `/` and is relative to the Swagger `basePath`; it does not include the instance origin or `/api/v1`. The fixed verb commands are `get`, `post`, `put`, `patch`, and `delete`. Each supports `--help`, and unknown verbs fail as unknown commands with exit 2.

Before binding other inputs, the bridge resolves the method and concrete path against the catalog's method and path templates. Exact static segments take precedence over parameter segments. A unique match supplies the Swagger operation and semantic policy for validation, safety, rendering, and contextual help.

Resolution failures are structured ordinary failures on stdout with exit 1:

- no match reports the method and path and suggests capability discovery;
- multiple matches report compact candidate keys without issuing an HTTP request;
- `--as <method:path-template>` or `--operation <operationId>` explicitly disambiguates a request, but neither is required for a unique match.

The catalog's stable internal key is the lowercase method, a colon, and the exact Swagger path template, for example `get:/repos/{owner}/{repo}/pulls`. Gitea's `operationId` is retained as searchable metadata and an accepted disambiguation alias. Generated help uses concrete paths when all values are known and `<name>` placeholders otherwise.

## Decision 2: schema-routed input assignments

API inputs are non-option `name=value` arguments after the concrete path. Options beginning with `--` belong exclusively to the bridge, preventing an API input such as `output` from colliding with the bridge's `--output` option.

```text
<cli> get /repos/acme/widgets/pulls state=open page=2 limit=20
<cli> post /repos/acme/widgets/issues title="Broken deployment" body="Observed after upgrading"
<cli> get /repos/acme/widgets/issues labels=3 labels=7
```

After capability resolution, input binding follows these rules:

1. Match an unqualified name against the capability's query parameters, top-level JSON body properties, and form fields.
2. Bind it when exactly one location matches.
3. Require `query:<name>=`, `body:<name>=`, or `form:<name>=` when multiple locations match.
4. Reject an unknown name, ambiguous name, duplicate scalar, missing required input, invalid enum, or invalid schema type on stdout with exit 2 before any HTTP request.
5. Coerce booleans, integers, and numbers from their Swagger types; strings remain literal shell arguments.
6. Represent `collectionFormat: multi` and array properties with repeated assignments in caller order.
7. Treat `name=@path` as file input only when the resolved Swagger input has type `file`; `@` has no implicit file meaning for strings.

`--input-json <json|@path|->` supplies the complete JSON body for nested or prebuilt payloads. It may be combined with query assignments but is mutually exclusive with `body:` and unqualified assignments that resolve to body properties. The bridge validates supplied JSON against the available schema before sending it.

A query string in the concrete path is accepted and decoded as query input, but generated help and documentation use assignments as the canonical form. Supplying the same scalar through both forms is an error; repeated values are valid only for declared arrays.

## Decision 3: independent execution properties

Semantic policy records three independent properties for each capability:

```text
effect:       read | mutate
confirmation: none | required | unknown
retry:        safe | unsafe | unknown
```

They are exposed by capability discovery, detail output, and `--dry-run`, but are omitted from ordinary successful responses unless directly useful. The properties do not form an ordinal risk score.

Execution follows these rules:

- A known destructive mutation has `confirmation: required` and requires `--yes` on every invocation, regardless of TTY state.
- A mutation whose semantics are absent from policy has `confirmation: unknown` and requires `--allow-unknown`; generic `--yes` does not conceal semantic uncertainty.
- Reads and ordinary known mutations with `confirmation: none` execute without a confirmation option.
- The CLI never prompts interactively.
- Automatic retry is permitted only for `retry: safe`. Unsafe and unknown requests are attempted at most once.
- `--dry-run` performs discovery, capability resolution, input binding, validation, and execution-policy checks but sends no HTTP request or mutation.
- A missing acknowledgement is a structured stdout error with exit 1 and an exact `help[]` retry command carrying forward the concrete target and fixed inputs.

`--yes` is an explicit intent boundary, not proof of human approval. Authorization remains the instance's responsibility and is limited by the configured credential.

## Decision 4: content-first result shapes

The default renderer emits TOON and selects the smallest result shape that fully describes the outcome. Successful responses do not receive a universal HTTP envelope.

A collection starts with its aggregate and then a named, typed table:

```toon
count: 2 of 17 total
pull_requests[2]{index,title,state,updated_at}:
  41,Fix race,open,2026-08-29T18:12:00Z
  37,Update docs,open,2026-08-28T09:31:00Z
help[2]:
  - <cli> get /repos/acme/widgets/pulls/<index>
  - <cli> get /repos/acme/widgets/pulls state=closed
```

A detail object is named by semantic policy and does not emit the meaningless aggregate `count: 1`:

```toon
issue:
  index: 42
  title: Broken deployment
  state: open
  user.login: alice
```

A successful response without an entity is never silent:

```toon
result:
  status: 204
  outcome: completed
```

Failures use an explicit error object on stdout:

```toon
error:
  message: issue 42 not found
  status: 404
  request: GET /repos/acme/widgets/issues/42
```

Relevant failures and successful results append one to three executable `help[]` suggestions in the same root document. Field order is stable. Explicit JSON and YAML formats encode the same logical result rather than exposing a different response model.

## Decision 5: explicit non-JSON transport modes

The response classifier uses the actual final status and `Content-Type`, consulting the advertised response only when runtime metadata is absent. Plain text and HTML are structured and truncated by default:

```toon
content:
  media_type: text/plain
  size: 8421
  truncated: true
  text: "diff --git a/…"
help[1]:
  - <cli> get /repos/acme/widgets/pulls/42.diff --raw
```

`--full` disables truncation while preserving the structured content object. `--raw` instead writes the exact successful response body to stdout, appends no `help[]`, and is the sole documented exception to structured successful output. HTTP and local failures remain structured on stdout even when `--raw` was requested.

Binary responses require either `--save <path>` or explicit `--raw`. When Swagger advertises binary output and neither is present, validation fails before the request. If an undocumented binary response arrives, the client stops consuming it and emits a structured error with an exact retry suggestion.

`--save` streams to a temporary file in the destination directory and atomically renames it only after a successful complete response. An existing destination fails without modification unless `--overwrite` is present. Stdout receives a receipt:

```toon
file:
  path: ./artifact.zip
  size: 18432
  media_type: application/zip
  sha256: 83a1…
```

GET redirects are bounded and followed. Credentials are removed whenever the origin changes. Cross-origin redirects for mutations are refused unless a future explicit policy allows a specific capability and target origin.

## Decision 6: source-faithful projections

Semantic policy chooses useful response fields but does not rename them. Output headers contain exact JSON property names or dotted paths for selected nested scalars:

```toon
count: 2 of 17 total
pull_requests[2]{index,title,state,user.login}:
  41,Fix race,open,alice
  37,Update docs,open,bob
```

Known collection entities have an ordered policy projection of at most four fields. An unknown collection uses a deterministic fallback: prefer an externally usable identifier, then `name` or `title`, then `state` or `status`, then short top-level scalar properties in lexical order. Verbose content, URLs, and nested objects are excluded from fallback projections.

`--fields <path,...>` replaces the default projection and preserves caller order. Dotted paths select nested values without emitting their enclosing objects. A field unknown to the advertised or observed response shape is a structured validation failure rather than a silently omitted column. An optional field absent from a particular row emits `null`.

Field selection and content truncation are independent: explicitly selecting a field does not imply `--full`, and `--full` does not add fields.

## Decision 7: one explicit truncation contract

Every projected string is limited to 160 Unicode characters by default. The limit is applied after projection and before output encoding. A truncated value uses its first 159 characters followed by `…`, preserving a maximum rendered value length of 160 characters before format escaping.

Truncation adds original-size metadata and an executable complete-content suggestion:

```toon
issue:
  index: 42
  title: Broken deployment
  body: "The deployment began failing after the runner upgrade…"
truncated[1]{field,characters}:
  body,1843
help[1]:
  - <cli> get /repos/acme/widgets/issues/42 --fields index,title,body --full
```

Collection metadata adds a one-based `row` column so each truncated cell is identifiable. Identifiers, field names, aggregates, control metadata, and executable help commands are never truncated. Text responses use the same limit in structured mode.

`--full` disables truncation only for fields already present in the projection. It does not add fields, fetch additional pages, or change output format. TOON, JSON, and YAML share the same logical truncation behavior; successful `--raw` output remains exact.

## Decision 8: bounded, explicit pagination

When a resolved capability declares both `page` and `limit`, the bridge supplies `page=1 limit=20` for values the caller omitted. Caller assignments override those defaults. A request returns one page unless an explicit future aggregation mode is selected.

The response classifier uses observed total and navigation headers even when Swagger omits them. It never issues a hidden request solely to calculate a total.

A known total uses the required aggregate form:

```toon
count: 20 of 83 total
page: 1
issues[20]{index,title,state,updated_at}:
  …
help[1]:
  - <cli> get /repos/acme/widgets/issues page=2 limit=20
```

A paginated response without a server total names the uncertainty:

```toon
count: 20
total: unknown
page: 1
issues[20]{index,title,state,updated_at}:
  …
```

An unpaginated collection is complete and reports `count: N of N total`. Every empty collection emits the exact line `count: 0` followed by its named typed zero-row collection. Next-page help is emitted when response metadata proves another page exists or when a full page makes another page plausible; a plausible suggestion does not claim that another result exists.

## Decision 9: repository-first instance discovery

Instance selection follows this order:

1. An explicit `--server` value or opt-in session setting.
2. Repository context derived from the current Git repository's `origin` remote.
3. If `origin` is absent, the sole unambiguous configured Gitea remote.
4. A configured default instance outside a resolvable Gitea repository.
5. Otherwise, a structured setup failure.

An HTTP(S) Git remote supplies its scheme, origin, owner, and repository directly. An SSH remote supplies host, owner, and repository; its web origin comes from an exact saved mapping or an anonymous HTTPS Swagger probe. The bridge does not downgrade an SSH-derived host to HTTP automatically. Custom ports and installations below a URL subpath require a saved mapping because Git remotes do not reliably encode their API origin.

The inferred origin is verified anonymously through its Swagger discovery page before use. Stored credentials are attached only when their normalized configured origin exactly matches the resolved origin; repository content and previously unseen remotes cannot define or redirect credential sources. An explicitly HTTP remote may be discovered, but credential transport over plaintext is governed separately by authentication policy.

Repository discovery reads Git configuration without modifying it. Derived owner and repository values feed the home view and concrete contextual-help commands; they do not reintroduce template placeholders into primary request syntax.

## Decision 10: origin-scoped credentials

Credentials are keyed to an exact normalized instance origin: scheme, lowercase host, effective port, and installation base path. User information, query, fragment, and a trailing slash are not part of the origin. A credential is attached only when its bound origin equals the resolved request origin.

The first-class ephemeral agent source is an environment pair:

```text
GITEA_SERVER=https://gitea.example.com
GITEA_TOKEN=<secret>
```

Both variables must be present. `GITEA_TOKEN` alone is an error and is never paired with an origin inferred from repository content. `GITEA_SERVER` is an explicit session setting and therefore takes precedence over repository discovery. If `--server` selects a different origin, the environment token is not sent and the mismatch fails unless the caller explicitly requests anonymous execution or supplies credentials bound to the selected origin.

Persistent workflows may obtain a token through `auth add <server> --token-stdin` and an OS or external credential helper, but plaintext tokens are not stored in ordinary configuration or accepted as command-line arguments. Every provider returns an origin-token pair and follows the same matching rule.

Absent a matching credential, the request proceeds anonymously when the capability permits it; authentication failures are structured and suggest origin-scoped setup. Interactive credential prompts are disabled. Tokens are redacted from status, errors, dry runs, debug logs, caches, generated documentation, and help. Sending a credential over HTTP additionally requires an explicit insecure-transport setting for that exact origin.

The credential used to authenticate a request is control-plane data and is always redacted. Values intentionally returned by an invoked API capability, including newly created tokens or registration credentials, are response data and follow ordinary projection and output rules; they do not require a separate reveal or save mode. Semantic policy must choose a useful creation-response projection because repeating a non-idempotent creation solely to retrieve an omitted value is unsafe.

## Decision 11: capability-matched semantic policy

Semantic policy is a declarative bundle shipped and versioned with the CLI. Rules select capabilities primarily by the normalized `method:path-template` key and may add response-schema fingerprints or bounded version conditions when the same route has incompatible meaning across releases. The connected instance's observed catalog, not its version string alone, determines which rules apply.

Precedence is:

1. non-overridable bridge invariants such as structured errors, credential origin binding, and destructive confirmation;
2. built-in capability-matched semantic policy;
3. user-level overlays for the exact normalized instance origin;
4. repository-local presentation overlays;
5. conservative schema/runtime fallback for unresolved properties.

User overlays may correct entity names, projections, workflow relationships, response classification, and execution properties without inventing a capability absent from Swagger. Repository-local overlays may alter presentation and suggestions but cannot weaken confirmation, credential, redirect, or transport protections. `capability` reports each resolved semantic property and its policy source.

Policy updates arrive through normal CLI releases or explicitly installed trusted bundles. Swagger and other instance responses are capability data, never automatically trusted policy or executable configuration.

## Decision 12: live home and bounded discovery

The command surface for orientation and discovery is:

```text
<cli>                              # live home
<cli> capabilities [search terms]  # list/filter advertised capabilities
<cli> capability <key|operationId> # inspect one capability
<cli> context                      # compact ambient repository context
<cli> skill                        # generate Agent Skill on stdout
```

Inside a resolved repository, the no-argument home view includes the home-abbreviated executable path, one-sentence description, server origin and version, authenticated user when known, repository identity, and live open-issue/open-pull aggregates. It ends with one to three concrete requests for the current repository. Outside a repository, it substitutes compact instance/user state and setup or discovery actions; it never falls back to a usage dump.

`capabilities` is an entity noun whose default is a bounded list. Search terms filter across method, path, summary, Swagger `operationId`, and tag. Its default TOON schema is exactly `method,path,summary,effect`; it reports returned and server-catalog totals before rows. `capability` emits resolved inputs, response classes, execution properties, policy provenance, and concrete examples without expanding referenced schema trees.

`context` emits only the compact, non-secret values needed before an agent acts: executable, instance, repository, current branch, identity status, and exact high-value command templates. An opt-in session hook invokes this command. `skill` generates repository-scoped Agent Skill guidance from the same templates and resolved capability vocabulary; it writes to stdout by default, contains no credential material, and requires an explicit setup command to install files or hooks.

## Decision 13: feature-based v1 compatibility

V1 supports the Swagger 2.0 features exercised by Gitea and resolves internal `$ref` values. It does not gate an instance on a recognized Gitea version. OpenAPI 3 is deferred until a Gitea capability requires it.

An unsupported construct affects only the capability that contains it. Discovery marks that capability unavailable with a compact reason while all other compiled capabilities remain usable. The reference acceptance instance currently advertises 482 operations; all must compile into unique catalog entries and resolve from representative concrete requests.

Tests do not maintain full Swagger snapshots as a historical version registry. The compatibility strategy is:

- small synthetic Swagger documents covering reference resolution, all supported parameter locations and scalar types, arrays, JSON bodies, uploads, response references, empty responses, text, binary, redirects, and overlapping route templates;
- mock HTTP exchanges covering every success and failure classifier and exact AXI output contract;
- an integration test that fetches the configured test instance's live Swagger and compiles every advertised capability dynamically;
- an ephemeral CI Gitea instance whose Swagger is fetched at test time;
- optional scheduled compatibility runs against newer releases, with no generated command catalog checked into the implementation.

Golden output tests verify stable TOON field order, known and unknown totals, typed empty collections, projection, truncation metadata, structured errors, status-only success, file receipts, and contextual `help[]`. Validation failures, dry runs, missing acknowledgements, and ambiguous capability resolution send no API request. A warm ordinary API invocation sends exactly one request; the multi-aggregate home view is an explicit exception. Swagger discovery uses conditional HTTP caching keyed by normalized origin and content identity.

The implementation is complete for v1 when the live reference catalog compiles fully, the contract and integration suites pass, generated CLI documentation is current, and proposed repository gates such as `uv run invoke verify` and `uv run invoke docs` exist and pass. These targets are design requirements, not claims about the currently empty implementation repository.

## Deferred implementation choices

The executable name, implementation language, source layout, packaging system, and concrete credential-helper backend remain open. They do not alter the interaction contracts above and should be selected during implementation planning.
