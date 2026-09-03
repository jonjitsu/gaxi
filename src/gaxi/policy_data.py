"""The built-in Gitea semantic policy bundle.

Rules are matched by the normalized `method:path-template` key, or by the
response-schema fingerprint (the Swagger definition name) for presentation
properties. The bundle ships with the CLI and never invents a capability.
"""

BUNDLE_VERSION = "2026.08.30"

# Response-schema fingerprint -> (collection name, detail name, projection)
ENTITIES = {
    "Issue": ("issues", "issue", ["number", "title", "state", "updated_at"]),
    "PullRequest": ("pull_requests", "pull_request", ["number", "title", "state", "merged"]),
    "Repository": ("repositories", "repository", ["full_name", "private", "fork", "updated_at"]),
    "User": ("users", "user", ["login", "full_name", "is_admin"]),
    "Label": ("labels", "label", ["id", "name", "color", "exclusive"]),
    "Milestone": ("milestones", "milestone", ["id", "title", "state", "due_on"]),
    "Release": ("releases", "release", ["id", "tag_name", "name", "draft"]),
    "Branch": ("branches", "branch", ["name", "protected", "user_can_push"]),
    "Tag": ("tags", "tag", ["name", "id"]),
    "Commit": ("commits", "commit", ["sha", "commit.message", "commit.author.date"]),
    # ADR 0019: comment lists include body by default (truncated per ADR 0008).
    "Comment": ("comments", "comment", ["id", "user.login", "body", "created_at"]),
    "TimelineComment": ("timeline", "timeline_entry", ["id", "type", "created_at"]),
    "Organization": ("organizations", "organization", ["username", "full_name", "visibility"]),
    "Team": ("teams", "team", ["id", "name", "permission"]),
    "Hook": ("hooks", "hook", ["id", "type", "active"]),
    "NotificationThread": ("notifications", "notification", ["id", "subject.title", "unread"]),
    "ContentsResponse": ("contents", "content", ["name", "path", "type", "size"]),
    "Attachment": ("attachments", "attachment", ["id", "name", "size"]),
    "Reference": ("references", "reference", ["ref", "object.sha"]),
    "PullReview": ("reviews", "review", ["id", "user.login", "state"]),
    "PullReviewComment": ("review_comments", "review_comment", ["id", "path", "user.login"]),
    "CommitStatus": ("statuses", "status", ["id", "state", "context"]),
    "CombinedStatus": ("combined_statuses", "combined_status", ["sha", "state", "total_count"]),
    "AccessToken": ("tokens", "token", ["id", "name", "scopes"]),
    "PublicKey": ("keys", "key", ["id", "title", "read_only"]),
    "DeployKey": ("deploy_keys", "deploy_key", ["id", "title", "read_only"]),
    "GPGKey": ("gpg_keys", "gpg_key", ["id", "key_id", "can_sign"]),
    "Email": ("emails", "email", ["email", "verified", "primary"]),
    "TrackedTime": ("tracked_times", "tracked_time", ["id", "user_name", "time"]),
    "StopWatch": ("stopwatches", "stopwatch", ["issue_index", "created", "seconds"]),
    "Cron": ("crons", "cron", ["name", "schedule", "next"]),
    "GitBlobResponse": ("blobs", "blob", ["sha", "size", "encoding"]),
    "GitTreeResponse": ("trees", "tree", ["sha", "total_count", "truncated"]),
    "WatchInfo": ("subscriptions", "subscription", ["subscribed", "ignored", "reason"]),
    "ServerVersion": ("versions", "version", ["version"]),
    "ActivityPub": ("activities", "activity", ["@context"]),
    "Package": ("packages", "package", ["id", "name", "version", "type"]),
    "Runner": ("runners", "runner", ["id", "name", "status"]),
    "ActionWorkflow": ("workflows", "workflow", ["id", "name", "state"]),
    "ActionRun": ("runs", "run", ["id", "title", "status", "run_number"]),
    "ActionArtifact": ("artifacts", "artifact", ["id", "name", "size_in_bytes"]),
    "Secret": ("secrets", "secret", ["name", "created_at"]),
    "ActionVariable": ("variables", "variable", ["name", "data"]),
    "WikiPage": ("wiki_pages", "wiki_page", ["title", "sub_url", "last_commit.sha"]),
    "WikiPageMetaData": ("wiki_pages", "wiki_page", ["title", "sub_url", "updated_at"]),
    "Compare": ("comparisons", "comparison", ["total_commits"]),
    "IssueTemplate": ("issue_templates", "issue_template", ["name", "title", "about"]),
    "GitHook": ("git_hooks", "git_hook", ["name", "is_active"]),
    "OAuth2Application": (
        "oauth2_applications", "oauth2_application", ["id", "name", "confidential_client"]),
    "Topic": ("topics", "topic", ["topic_name", "repo_count"]),
    "TopicName": ("topics", "topic", ["topics"]),
    "SearchResults": ("repositories", "repository", ["full_name", "private", "fork", "updated_at"]),
}

# Capabilities whose mutation semantics are known. `confirmation: none` marks an
# ordinary mutation; `required` marks a known destructive or irreversible one.
MUTATIONS = {
    # issues and comments
    "post:/repos/{owner}/{repo}/issues": ("none", "unsafe"),
    "patch:/repos/{owner}/{repo}/issues/{index}": ("none", "unknown"),
    "post:/repos/{owner}/{repo}/issues/{index}/comments": ("none", "unsafe"),
    "patch:/repos/{owner}/{repo}/issues/comments/{id}": ("none", "unknown"),
    "post:/repos/{owner}/{repo}/issues/{index}/labels": ("none", "unsafe"),
    "put:/repos/{owner}/{repo}/issues/{index}/labels": ("none", "safe"),
    "post:/repos/{owner}/{repo}/issues/{index}/dependencies": ("none", "safe"),
    "post:/repos/{owner}/{repo}/issues/{index}/reactions": ("none", "safe"),
    "put:/repos/{owner}/{repo}/issues/{index}/subscriptions/{user}": ("none", "safe"),
    # pull requests
    "post:/repos/{owner}/{repo}/pulls": ("none", "unsafe"),
    "patch:/repos/{owner}/{repo}/pulls/{index}": ("none", "unknown"),
    "post:/repos/{owner}/{repo}/pulls/{index}/reviews": ("none", "unsafe"),
    "post:/repos/{owner}/{repo}/pulls/{index}/requested_reviewers": ("none", "unsafe"),
    "post:/repos/{owner}/{repo}/pulls/{index}/merge": ("required", "unsafe"),
    "post:/repos/{owner}/{repo}/pulls/{index}/update": ("none", "unsafe"),
    # repository metadata
    "post:/user/repos": ("none", "unsafe"),
    "post:/orgs/{org}/repos": ("none", "unsafe"),
    "patch:/repos/{owner}/{repo}": ("none", "unknown"),
    "post:/repos/{owner}/{repo}/forks": ("none", "unsafe"),
    "post:/repos/{owner}/{repo}/labels": ("none", "unsafe"),
    "patch:/repos/{owner}/{repo}/labels/{id}": ("none", "unknown"),
    "post:/repos/{owner}/{repo}/milestones": ("none", "unsafe"),
    "patch:/repos/{owner}/{repo}/milestones/{id}": ("none", "unknown"),
    "post:/repos/{owner}/{repo}/releases": ("none", "unsafe"),
    "patch:/repos/{owner}/{repo}/releases/{id}": ("none", "unknown"),
    "post:/repos/{owner}/{repo}/statuses/{sha}": ("none", "unsafe"),
    "post:/repos/{owner}/{repo}/hooks": ("none", "unsafe"),
    "patch:/repos/{owner}/{repo}/hooks/{id}": ("none", "unknown"),
    "post:/repos/{owner}/{repo}/branches": ("none", "unsafe"),
    "post:/repos/{owner}/{repo}/tags": ("none", "unsafe"),
    "post:/repos/{owner}/{repo}/contents/{filepath}": ("none", "unsafe"),
    "put:/repos/{owner}/{repo}/contents/{filepath}": ("none", "unknown"),
    "post:/repos/{owner}/{repo}/transfer": ("required", "unsafe"),
    "post:/repos/{owner}/{repo}/mirror-sync": ("none", "safe"),
    # user state
    "put:/user/starred/{owner}/{repo}": ("none", "safe"),
    "put:/repos/{owner}/{repo}/subscription": ("none", "safe"),
    "post:/user/emails": ("none", "unsafe"),
    "post:/user/keys": ("none", "unsafe"),
    "post:/users/{username}/tokens": ("none", "unsafe"),
    "patch:/user/settings": ("none", "unknown"),
    "put:/notifications": ("none", "safe"),
    "patch:/notifications": ("none", "safe"),
    "patch:/notifications/threads/{id}": ("none", "safe"),
    # organizations and teams
    "post:/orgs": ("none", "unsafe"),
    "patch:/orgs/{org}": ("none", "unknown"),
    "post:/orgs/{org}/teams": ("none", "unsafe"),
    "patch:/teams/{id}": ("none", "unknown"),
    "put:/teams/{id}/members/{username}": ("none", "safe"),
    "put:/teams/{id}/repos/{org}/{repo}": ("none", "safe"),
    "put:/orgs/{org}/members/{username}": ("none", "safe"),
    "put:/orgs/{org}/public_members/{username}": ("none", "safe"),
}

# Capabilities whose response classification Swagger states imprecisely.
RESPONSES = {
    "get:/repos/search": "collection",
    "get:/users/search": "collection",
    "get:/repos/{owner}/{repo}/pulls/{index}.{diffType}": "text",
    "get:/repos/{owner}/{repo}/raw/{filepath}": "text",
    "get:/repos/{owner}/{repo}/media/{filepath}": "file",
    "get:/repos/{owner}/{repo}/archive/{archive}": "file",
}

# Capabilities that return a total-count header Swagger does not declare.
TOTAL_HEADER_ORIGINS = ("X-Total-Count",)
