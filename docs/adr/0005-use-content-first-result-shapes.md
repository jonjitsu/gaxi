# Use content-first result shapes

Successful output will begin with the useful domain content and use a shape appropriate to a collection, detail object, or status-only result instead of wrapping every response in generic HTTP metadata. A universal response envelope was rejected because it repeats request, operation, and status fields that the caller already knows; errors remain explicitly enveloped, and metadata is included only when needed to interpret the result.
