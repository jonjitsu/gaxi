# Gitea AXI Bridge

This context describes the language used to turn a Gitea instance's advertised API capabilities into safe, compact interactions for software agents.

## Language

**AXI bridge**:
The boundary that translates a Gitea **capability** into an agent-efficient request and response while preserving the operation's meaning.
_Avoid_: API wrapper, generated client

**Capability**:
An operation that a target **instance** advertises as available, including its inputs, transport, and documented responses.
_Avoid_: Command, endpoint

**Capability resolution**:
The bridge's internal mapping from a concrete **request** to exactly one advertised **capability**. Callers identify what they want to request; they select a capability explicitly only when the mapping is ambiguous.
_Avoid_: Operation selection, route guessing

**Instance**:
One configured Gitea-compatible server and its advertised capabilities.
_Avoid_: Host, environment

**Input binding**:
The mapping of a caller-supplied name and value to the query, body, or form input declared by the resolved **capability**.
_Avoid_: Flag parsing, payload construction

**Execution policy**:
The independent effect, confirmation, and retry properties attached to a **capability** by semantic policy. It states how a request may execute without collapsing different safety concerns into one risk score.
_Avoid_: Risk level, danger score

**Request**:
An intended HTTP method, concrete API-relative path, and associated inputs directed to an **instance**.
_Avoid_: Capability, command

**Projection**:
The ordered subset of response fields presented for an entity. Semantic policy may choose a projection, but projected field names remain faithful to the instance response.
_Avoid_: View model, renamed schema

**Repository context**:
The instance origin, owner, and repository identity derived from the current Git repository's remote without changing the repository. It is ambient context, not a source of credentials.
_Avoid_: Repository configuration, login profile

**Semantic policy**:
Gitea-specific meaning needed to make a capability safe and AXI-compliant when that meaning is absent or incomplete in the advertised API description. Examples include whether a response is a collection and whether an operation is destructive.
_Avoid_: Heuristic, hard-coded endpoint

## Example dialogue

> **Developer:** The instance advertises the `repoListPullRequests` capability, but its description omits the total-count header.
>
> **Domain expert:** Repository context identifies `gitea.home.arpa/acme/widgets`; invoke `GET /repos/acme/widgets/pulls state=open`. Capability resolution finds the advertised capability and the pull-request projection emits `index`, `title`, `state`, and `user.login`.
