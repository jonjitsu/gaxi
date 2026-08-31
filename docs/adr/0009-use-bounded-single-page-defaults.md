# Use bounded single-page defaults

Paginated capabilities will default to `page=1 limit=20`, use totals and navigation metadata observed on the actual response, and explicitly report `total: unknown` when the server provides no total. Hidden count requests and automatic multi-page aggregation were rejected because they add latency and unpredictable output cost; callers can override pagination through normal API assignments.
