# Resolve capabilities from concrete requests

The primary CLI grammar will use an HTTP verb and concrete API-relative path, such as `get /repos/acme/widgets/pulls`; the bridge resolves that request to the matching Swagger path template internally. Requiring callers to select a generated key or server-authored `operationId` was rejected because method and concrete path already express the request, while explicit capability identifiers remain available only to resolve ambiguous matches.
