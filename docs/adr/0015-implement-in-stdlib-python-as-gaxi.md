# Implement the bridge in stdlib Python as `gaxi`

The design deferred the executable name, implementation language, source layout, and
packaging system. The bridge is implemented as `gaxi`: a Python 3.13+ package under
`src/gaxi`, with no runtime dependencies outside the standard library, installed
through a `pyproject.toml` console script.

Python's standard library covers every transport and encoding the design needs
(`urllib`, `json`, `hashlib`, `subprocess`), so an agent-facing tool can be installed
without a compiler or a dependency tree, and the contract suites run with
`unittest` alone; the suites moved to pytest with the toolchain adopted in ADR 0016,
which also raised the interpreter floor to 3.13. TOON, the Swagger compiler, and the semantic policy bundle are
first-party modules rather than generated code, because the design requires the
catalog to come from the connected instance at runtime and forbids a checked-in
command catalog.

Credential storage delegates to an external helper process invoked as
`<helper> get|store|erase <origin>`, which keeps plaintext tokens out of ordinary
configuration without binding the bridge to one OS keychain.
