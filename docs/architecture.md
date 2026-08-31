# Architecture map

This is a navigational map of `gaxi` for developers and architects. It is not a
second specification: use the [domain glossary](../CONTEXT.md), the
[clean-sheet design](design/gitea-axi-bridge-clean-sheet.md), and the
[architecture decisions](adr/) for normative language and rationale.

## System context

`gaxi` is an AXI bridge between a concrete caller request and one capability
advertised by a Gitea-compatible instance. It combines instance facts with local
semantic policy, but does not hide either source behind a generated API client.

```mermaid
flowchart LR
    caller["Developer or software agent"]
    git["Current Git repository<br/>root, branch, remotes"]
    env["Session environment<br/>GITEA_SERVER + GITEA_TOKEN"]
    config["User configuration<br/>instances, overlays, helpers"]
    helper["External credential helper"]
    cache["Capability cache<br/>Swagger document + validators"]
    gaxi["gaxi<br/>AXI bridge"]
    instance["Gitea-compatible instance<br/>discovery, Swagger, API"]
    stdout["stdout<br/>TOON by default; JSON/YAML opt-in"]
    stderr["stderr<br/>debug diagnostics only"]

    caller -->|"verb or discovery command"| gaxi
    git -.->|"repository context"| gaxi
    env -.->|"explicit instance and ephemeral credential"| gaxi
    config <-->|"read settings; explicit mutations only"| gaxi
    helper <-->|"get / store / erase origin-bound token"| gaxi
    cache <-->|"read, revalidate, atomically replace"| gaxi
    gaxi <-->|"discover capabilities; execute request"| instance
    gaxi -->|"structured result or failure"| stdout
    gaxi -.->|"optional redacted trace"| stderr
```

The instance origin is a trust boundary. Credentials, configuration, cached
descriptions, and overlays are all bound to an exact normalized origin.

## Code map

The package is organized as a pipeline with `Session` as the lazy composition
root. Arrows show the main call or data-flow direction, not every import.

```mermaid
flowchart TB
    entry["__main__.py<br/>installed gaxi entry point"]

    subgraph surface["Command surface"]
        cli["cli.py<br/>parse, dispatch, exit codes"]
        commands["commands/*<br/>home, context, capabilities,<br/>auth, skill, setup"]
        helpdoc["helpdoc.py + docsgen.py<br/>runtime and generated CLI help"]
    end

    subgraph context["Lazy runtime context"]
        session["session.py<br/>Session + Options"]
        repo["repo_context.py<br/>Git repository discovery"]
        config["config.py<br/>origin-scoped configuration"]
        discovery["discovery.py<br/>origin selection + catalog cache"]
        credentials["credentials.py<br/>origin-bound token + redaction"]
    end

    subgraph model["Advertised capability model and semantics"]
        swagger["swagger.py<br/>compile Swagger 2.0"]
        capability["capability.py<br/>Capability, Param, ResponseSpec"]
        catalog["catalog.py<br/>search, match, resolve"]
        policy["policy.py + policy_data.py<br/>execution and presentation policy"]
    end

    subgraph execution["Validated request execution"]
        invoke["invoke.py<br/>orchestrate and enforce safety"]
        binding["binding.py + jsonbody.py<br/>schema-directed input binding"]
        invocation["invocation.py<br/>validated request state"]
        planner["planner.py<br/>next-action command templates"]
        transport["transport.py<br/>HTTP exchange and response stream"]
    end

    subgraph output["Content-first output"]
        results["results.py<br/>shape response outcome"]
        classify["classify.py<br/>runtime response kind"]
        projection["projection.py<br/>fields + truncation"]
        render["render.py + document.py<br/>logical result document"]
        encode["encode.py<br/>TOON, JSON, YAML"]
    end

    shared["Shared vocabulary<br/>errors.py, naming.py, jsonshape.py"]

    entry --> cli
    cli --> commands
    cli --> session
    cli --> invoke
    cli --> helpdoc
    session --> repo
    session --> config
    session --> discovery
    session --> credentials
    session --> policy
    session --> transport
    discovery --> catalog
    catalog --> swagger
    swagger --> capability
    invoke --> catalog
    invoke --> policy
    invoke --> binding
    invoke --> invocation
    invoke --> planner
    invoke --> transport
    invoke --> results
    results --> classify
    results --> projection
    results --> planner
    results --> render
    cli --> encode
    render --> encode
    shared -.-> surface
    shared -.-> context
    shared -.-> model
    shared -.-> execution
    shared -.-> output
```

The important ownership boundaries are:

- `cli.py` owns command grammar and process behavior, not API semantics.
- `Session` owns lazy context and dependency reuse for one invocation.
- `Catalog` owns what the instance advertises; `Policy` owns what those
  capabilities mean for safe execution and compact presentation.
- `invoke.py` decides whether and how a request may be sent; `results.py`
  decides what the returned response becomes.
- `Document` is the shared logical output model. Encoders do not rediscover
  response semantics.

## Request lifecycle

The main verb path resolves and validates everything before sending a mutation.
Dashed portions are lazy and may be satisfied from memory or cache.

```mermaid
sequenceDiagram
    actor Caller
    participant CLI as cli.py
    participant Session as Session
    participant Discovery as discovery + Catalog
    participant Invoke as invoke.py
    participant Policy as Policy
    participant Bind as binding.py
    participant Auth as CredentialResolver
    participant HTTP as Transport / Gitea
    participant Result as results.py
    participant Output as Document + encoder

    Caller->>CLI: gaxi METHOD /path name=value [options]
    CLI->>CLI: parse bridge options and API assignments
    CLI->>Session: create invocation-scoped lazy context
    CLI->>Invoke: run_request(method, path, assignments)
    Invoke-->>Session: request catalog
    Session-->>Discovery: resolve origin, then load or refresh description
    Discovery-->>HTTP: discovery / Swagger request when needed
    HTTP-->>Discovery: advertised API description
    Discovery-->>Session: compiled Catalog
    Invoke->>Discovery: resolve concrete request to one Capability
    Invoke-->>Session: request semantic policy
    Session-->>Policy: build built-ins plus origin/repository overlays
    Policy-->>Invoke: effect, confirmation, retry, response, projection
    Invoke->>Bind: validate and route inputs using capability schema
    Bind-->>Invoke: query, body, form, files, defaults
    Invoke->>Invoke: enforce mutation and transport policy

    alt --dry-run
        Invoke->>Result: build validated unsent request document
    else execute
        Invoke-->>Session: request credential
        Session-->>Auth: resolve exact-origin environment/helper token
        Auth-->>Invoke: credential or anonymous
        Invoke->>HTTP: send, retry or follow redirects only when allowed
        HTTP-->>Invoke: final status, headers, and body/stream
        Invoke->>Result: classify, project, truncate, add next actions
    end

    Result->>Output: logical Document or explicit raw bytes
    Output-->>CLI: encoded document or unchanged bytes
    CLI-->>Caller: stdout and meaningful exit code
```

Special commands (`home`, `context`, `capabilities`, `auth`, `skill`, and
`setup`) branch in `cli.dispatch`; they reuse the same `Session`, `Document`, and
encoding infrastructure where applicable.

## Origin and credential safety

Origin discovery and credential discovery are deliberately separate. Repository
context may select an instance, but it can never scope a bare `GITEA_TOKEN`.

```mermaid
flowchart TD
    start["Need an instance origin"] --> server{"--server supplied?"}
    server -->|yes| selected["Normalize exact origin"]
    server -->|no| envserver{"GITEA_SERVER set?"}
    envserver -->|yes| selected
    envserver -->|no| originremote{"Repository origin remote maps?"}
    originremote -->|yes| selected
    originremote -->|no| sole{"Exactly one remote maps?"}
    sole -->|yes| selected
    sole -->|no| default{"Configured default instance?"}
    default -->|yes| selected
    default -->|no| originerror["Structured setup failure"]

    selected --> anonymous{"--anonymous?"}
    anonymous -->|yes| noauth["Send no credential"]
    anonymous -->|no| token{"GITEA_TOKEN set?"}
    token -->|yes| envpair{"GITEA_SERVER also set?"}
    envpair -->|no| autherror["Structured credential error<br/>send nothing"]
    envpair -->|yes| paired{"Environment origin<br/>exactly matches?"}
    paired -->|yes| transport{"HTTPS, or HTTP explicitly<br/>allowed for this origin?"}
    paired -->|no| helper{"Credential helper configured<br/>for this exact origin?"}
    token -->|no| helper
    helper -->|yes, token found| transport
    helper -->|no token, env mismatch| autherror
    helper -->|no token, no env token| noauth
    transport -->|yes| auth["Attach Authorization header"]
    transport -->|no| autherror

    auth --> redirect{"Redirect response?"}
    redirect -->|no| complete["Return response"]
    redirect -->|yes| mutation{"Mutation?"}
    mutation -->|yes| refused["Refuse redirect"]
    mutation -->|no| target{"Target under instance origin?"}
    target -->|yes| keep["Credential may be forwarded"]
    target -->|no| drop["Drop Authorization header"]
```

## AXI result shaping

Response handling is content-first. There is no universal HTTP envelope; each
outcome receives the smallest shape that remains definitive and actionable.

```mermaid
flowchart TD
    response["Final HTTP response"] --> save{"Successful --save?"}
    save -->|yes| receipt["Stream atomically to file<br/>file receipt + SHA-256"]
    save -->|no| classify["Classify actual status,<br/>content type, headers, body"]
    classify --> failed{"Failure?"}
    failed -->|yes| error["Structured error + help[]<br/>exit 1"]
    failed -->|no| rawopt{"--raw?"}
    rawopt -->|yes| raw["Unchanged response bytes"]
    rawopt -->|no| kind{"Classified kind"}
    kind -->|redirect| redirect["Status + location"]
    kind -->|binary| binary["Structured guidance to --save"]
    kind -->|text| text["Size + truncation metadata"]
    kind -->|status| status["Status + outcome"]
    kind -->|collection| collection["Count before typed table"]
    kind -->|detail| detail["Named projected object"]

    collection --> fields["Policy/default --fields<br/>max 4 by default"]
    detail --> fields
    fields --> truncate["160-character shared limit<br/>unless --full"]
    truncate --> next["Planner adds 1-3 concrete<br/>next-command templates"]

    receipt --> document["Logical Document"]
    error --> document
    redirect --> document
    binary --> document
    text --> document
    status --> document
    next --> document
    document --> encode["Stable TOON default<br/>or JSON / YAML"]
    encode --> redact["Redact credential material"]
    redact --> stdout["stdout"]
    raw --> rawstdout["stdout<br/>explicit raw escape hatch"]
```

Runtime classification uses the actual response first and consults the
advertised response schema only when metadata is absent. Projection preserves
the instance's field names; policy selects fields but does not rename them.

## Where to change behavior

| Change | Start here | Usually verify alongside |
|---|---|---|
| Command or option grammar | `src/gaxi/cli.py`, `src/gaxi/helpdoc.py` | `src/gaxi/docsgen.py`, CLI tests |
| Instance discovery or cache | `src/gaxi/discovery.py` | `src/gaxi/repo_context.py`, discovery tests |
| Capability matching | `src/gaxi/catalog.py`, `src/gaxi/capability.py` | `src/gaxi/swagger.py`, catalog tests |
| API input behavior | `src/gaxi/binding.py` | `src/gaxi/jsonbody.py`, binding tests |
| Mutation/retry semantics | `src/gaxi/policy.py`, `src/gaxi/policy_data.py` | `src/gaxi/invoke.py`, policy tests |
| Response schema or truncation | `src/gaxi/results.py`, `src/gaxi/projection.py` | `src/gaxi/render.py`, result/contract tests |
| TOON/JSON/YAML syntax | `src/gaxi/document.py`, `src/gaxi/encode.py` | encoder/document tests |
| Authentication | `src/gaxi/credentials.py`, `src/gaxi/commands/auth.py` | config and credential tests |
| Agent context generation | `src/gaxi/commands/context.py`, `skill.py`, `setup.py` | command and setup tests |

Run `uv run invoke verify` after changes. CLI documentation is generated from
the runtime help model with `uv run invoke docs`.
