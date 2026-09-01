"""Small synthetic Swagger documents used by the contract suites."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaxi.jsonshape import JsonObject

PULL_REQUEST = {
    "type": "object",
    "properties": {
        "number": {"type": "integer"},
        "title": {"type": "string"},
        "state": {"type": "string"},
        "updated_at": {"type": "string"},
        "body": {"type": "string"},
        "html_url": {"type": "string"},
    },
}

ISSUE = {
    "type": "object",
    "properties": {
        "number": {"type": "integer"},
        "title": {"type": "string"},
        "state": {"type": "string"},
        "updated_at": {"type": "string"},
        "body": {"type": "string"},
    },
}

WIDGET = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
        "status": {"type": "string"},
        "colour": {"type": "string"},
        "description": {"type": "string"},
        "avatar_url": {"type": "string"},
    },
}

PAGINATION = [
    {"name": "page", "in": "query", "type": "integer"},
    {"name": "limit", "in": "query", "type": "integer"},
]

REPO_PATH = [
    {"name": "owner", "in": "path", "type": "string", "required": True},
    {"name": "repo", "in": "path", "type": "string", "required": True},
]


def _repo_params(extra: Sequence[JsonObject] = ()) -> list[JsonObject]:
    return [*REPO_PATH, *extra]


DOCUMENT = {
    "swagger": "2.0",
    "basePath": "/api/v1",
    "info": {"title": "Gitea API", "version": "1.27.2"},
    "produces": ["application/json"],
    "consumes": ["application/json"],
    "securityDefinitions": {
        "AuthorizationHeaderToken": {
            "type": "apiKey", "name": "Authorization", "in": "header",
        },
    },
    "definitions": {
        "PullRequest": PULL_REQUEST,
        "Issue": ISSUE,
        "Comment": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "body": {"type": "string"},
                           "user": {"type": "object"}, "created_at": {"type": "string"}},
        },
        "User": {
            "type": "object",
            "properties": {"login": {"type": "string"}, "full_name": {"type": "string"},
                           "is_admin": {"type": "boolean"}},
        },
        "Widget": WIDGET,
        "CreateIssueOption": {
            "type": "object",
            "required": ["title"],
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "closed": {"type": "boolean"},
                "labels": {"type": "array", "items": {"type": "integer"}},
            },
        },
        "EditIssueOption": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "state": {"type": "string"}},
        },
        "SearchResults": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"},
                           "data": {"type": "array", "items": {"$ref": "#/definitions/Widget"}}},
        },
    },
    "responses": {
        "PullRequestList": {
            "description": "PullRequestList",
            "schema": {"type": "array", "items": {"$ref": "#/definitions/PullRequest"}},
        },
        "empty": {"description": "APIEmpty"},
    },
    "paths": {
        "/repos/{owner}/{repo}/pulls": {
            "get": {
                "operationId": "repoListPullRequests",
                "summary": "List a repository's pull requests",
                "tags": ["repository"],
                "parameters": _repo_params([
                    *PAGINATION,
                    {"name": "state", "in": "query", "type": "string",
                     "enum": ["open", "closed", "all"]},
                    {"name": "labels", "in": "query", "type": "array",
                     "items": {"type": "integer"}, "collectionFormat": "multi"},
                ]),
                "responses": {"200": {"$ref": "#/responses/PullRequestList"}},
            },
        },
        "/repos/{owner}/{repo}/pulls/{index}": {
            "get": {
                "operationId": "repoGetPullRequest",
                "summary": "Get a pull request",
                "parameters": _repo_params([
                    {"name": "index", "in": "path", "type": "integer", "required": True}]),
                "responses": {"200": {"description": "PullRequest",
                                      "schema": {"$ref": "#/definitions/PullRequest"}}},
            },
        },
        "/repos/{owner}/{repo}/pulls/{index}.{diffType}": {
            "get": {
                "operationId": "repoDownloadPullDiffOrPatch",
                "summary": "Get a pull request diff or patch",
                "produces": ["text/plain"],
                "parameters": _repo_params([
                    {"name": "index", "in": "path", "type": "integer", "required": True},
                    {"name": "diffType", "in": "path", "type": "string", "required": True}]),
                "responses": {"200": {"description": "string", "schema": {"type": "string"}}},
            },
        },
        "/repos/{owner}/{repo}/issues": {
            "get": {
                "operationId": "issueListIssues",
                "summary": "List a repository's issues",
                "parameters": _repo_params([
                    *PAGINATION,
                    {"name": "state", "in": "query", "type": "string",
                     "enum": ["open", "closed", "all"]},
                    {"name": "type", "in": "query", "type": "string",
                     "enum": ["issues", "pulls"]},
                ]),
                "responses": {"200": {"description": "IssueList",
                                      "schema": {"type": "array",
                                                 "items": {"$ref": "#/definitions/Issue"}}}},
            },
            "post": {
                "operationId": "issueCreateIssue",
                "summary": "Create an issue",
                "parameters": _repo_params([
                    {"name": "body", "in": "body",
                     "schema": {"$ref": "#/definitions/CreateIssueOption"}}]),
                "responses": {"201": {"description": "Issue",
                                      "schema": {"$ref": "#/definitions/Issue"}}},
            },
        },
        "/repos/{owner}/{repo}/issues/{index}": {
            "get": {
                "operationId": "issueGetIssue",
                "parameters": _repo_params([
                    {"name": "index", "in": "path", "type": "integer", "required": True}]),
                "responses": {"200": {"description": "Issue",
                                      "schema": {"$ref": "#/definitions/Issue"}}},
            },
            "patch": {
                "operationId": "issueEditIssue",
                "parameters": _repo_params([
                    {"name": "index", "in": "path", "type": "integer", "required": True},
                    {"name": "body", "in": "body",
                     "schema": {"$ref": "#/definitions/EditIssueOption"}}]),
                "responses": {"201": {"description": "Issue",
                                      "schema": {"$ref": "#/definitions/Issue"}}},
            },
            "delete": {
                "operationId": "issueDelete",
                "parameters": _repo_params([
                    {"name": "index", "in": "path", "type": "integer", "required": True}]),
                "responses": {"204": {"$ref": "#/responses/empty"}},
            },
        },
        "/repos/{owner}/{repo}/issues/{index}/comments": {
            "get": {
                "operationId": "issueGetComments",
                "parameters": _repo_params([
                    {"name": "index", "in": "path", "type": "integer", "required": True}]),
                "responses": {"200": {"description": "CommentList",
                                      "schema": {"type": "array",
                                                 "items": {"$ref": "#/definitions/Comment"}}}},
            },
            "post": {
                "operationId": "issueCreateComment",
                "parameters": _repo_params([
                    {"name": "index", "in": "path", "type": "integer", "required": True},
                    {"name": "body", "in": "body",
                     "schema": {"type": "object", "required": ["body"],
                                "properties": {"body": {"type": "string"}}}}]),
                "responses": {"201": {"description": "Comment",
                                      "schema": {"$ref": "#/definitions/Comment"}}},
            },
        },
        "/repos/{owner}/{repo}/issues/comments/{id}": {
            "delete": {
                "operationId": "issueDeleteComment",
                "parameters": _repo_params([
                    {"name": "id", "in": "path", "type": "integer", "required": True}]),
                "responses": {"204": {"$ref": "#/responses/empty"}},
            },
        },
        "/repos/{owner}/{repo}/archive/{archive}": {
            "get": {
                "operationId": "repoGetArchive",
                "produces": ["application/octet-stream"],
                "parameters": _repo_params([
                    {"name": "archive", "in": "path", "type": "string", "required": True}]),
                "responses": {"200": {"description": "success", "schema": {"type": "file"}}},
            },
        },
        "/repos/{owner}/{repo}/releases/{id}/assets": {
            "post": {
                "operationId": "repoCreateReleaseAttachment",
                "consumes": ["multipart/form-data"],
                "parameters": _repo_params([
                    {"name": "id", "in": "path", "type": "integer", "required": True},
                    {"name": "name", "in": "query", "type": "string"},
                    {"name": "attachment", "in": "formData", "type": "file", "required": True}]),
                "responses": {"201": {"description": "Attachment",
                                      "schema": {"type": "object"}}},
            },
        },
        "/repos/{owner}/{repo}/redirect": {
            "get": {
                "operationId": "repoRedirect",
                "parameters": _repo_params(),
                "responses": {"302": {"description": "redirect"}},
            },
        },
        "/repos/search": {
            "get": {
                "operationId": "repoSearch",
                "summary": "Search repositories",
                "parameters": [*PAGINATION, {"name": "q", "in": "query", "type": "string"}],
                "responses": {"200": {"description": "SearchResults",
                                      "schema": {"$ref": "#/definitions/SearchResults"}}},
            },
        },
        "/repos/{id}": {
            "get": {
                "operationId": "repoGetByID",
                "parameters": [{"name": "id", "in": "path", "type": "integer", "required": True}],
                "responses": {"200": {"description": "Repository", "schema": {"type": "object"}}},
            },
        },
        "/org/{org}/widgets": {
            "get": {
                "operationId": "orgListWidgets",
                "parameters": [{"name": "org", "in": "path", "type": "string", "required": True}],
                "responses": {"200": {"description": "WidgetList",
                                      "schema": {"type": "array",
                                                 "items": {"$ref": "#/definitions/Widget"}}}},
            },
        },
        "/org/{owner}/widgets": {
            "get": {
                "operationId": "orgListWidgetsAlias",
                "parameters": [{"name": "owner", "in": "path", "type": "string", "required": True}],
                "responses": {"200": {"description": "WidgetList",
                                      "schema": {"type": "array",
                                                 "items": {"$ref": "#/definitions/Widget"}}}},
            },
        },
        "/user": {
            "get": {
                "operationId": "userGetCurrent",
                "responses": {"200": {"description": "User",
                                      "schema": {"$ref": "#/definitions/User"}}},
            },
        },
        "/admin/unsupported": {
            "get": {
                "operationId": "adminUnsupported",
                "parameters": [{"name": "shape", "in": "query", "type": "object"}],
                "responses": {"200": {"description": "ok"}},
            },
        },
        "/admin/broken": {
            "get": {
                "operationId": "adminBroken",
                "parameters": [{"$ref": "#/parameters/Missing"}],
                "responses": {"200": {"description": "ok"}},
            },
        },
    },
}
