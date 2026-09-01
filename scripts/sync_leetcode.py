#!/usr/bin/env python3
"""
sync_leetcode.py

Pulls your recent Accepted submissions from LeetCode (via its internal
GraphQL API) and commits them into this repo, split into dsa/ and sql/
folders, one folder per problem.

Auth: LeetCode doesn't have a public API. We authenticate the same way
your browser does: by sending your LEETCODE_SESSION + csrftoken cookies
with each request. These are read from environment variables so they can
be stored as GitHub Actions secrets and never committed to the repo.

Env vars required:
    LEETCODE_SESSION   - value of the LEETCODE_SESSION cookie
    LEETCODE_CSRFTOKEN  - value of the csrftoken cookie

Optional:
    SUBMISSION_LIMIT    - how many recent submissions to check each run
                          (default 20)
"""

import os
import re
import sys
import time
import html
import json
import pathlib
import requests

try:
    from markdownify import markdownify as html_to_md
except ImportError:
    print("Missing dependency 'markdownify'. Run: pip install markdownify", file=sys.stderr)
    sys.exit(1)

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

SESSION_COOKIE = os.environ.get("LEETCODE_SESSION")
CSRF_TOKEN = os.environ.get("LEETCODE_CSRFTOKEN")
SUBMISSION_LIMIT = int(os.environ.get("SUBMISSION_LIMIT", "20"))

if not SESSION_COOKIE or not CSRF_TOKEN:
    print("ERROR: LEETCODE_SESSION and LEETCODE_CSRFTOKEN env vars are required.", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "content-type": "application/json",
    "x-csrftoken": CSRF_TOKEN,
    "referer": "https://leetcode.com",
    "user-agent": "Mozilla/5.0 (sync-bot)",
}
COOKIES = {
    "LEETCODE_SESSION": SESSION_COOKIE,
    "csrftoken": CSRF_TOKEN,
}

# Maps LeetCode's submission "lang" field to a file extension + folder type.
LANG_EXT = {
    "python": "py",
    "python3": "py",
    "c": "c",
    "cpp": "cpp",
    "csharp": "cs",
    "java": "java",
    "javascript": "js",
    "typescript": "ts",
    "php": "php",
    "swift": "swift",
    "kotlin": "kt",
    "dart": "dart",
    "golang": "go",
    "ruby": "rb",
    "scala": "scala",
    "rust": "rs",
    "racket": "rkt",
    "erlang": "erl",
    "elixir": "ex",
    "mysql": "sql",
    "mssql": "sql",
    "oraclesql": "sql",
    "postgresql": "sql",
    "pythondata": "py",
    "bash": "sh",
}
SQL_LANGS = {"mysql", "mssql", "oraclesql", "postgresql"}


def gql(query: str, variables: dict) -> dict:
    resp = requests.post(
        LEETCODE_GRAPHQL_URL,
        headers=HEADERS,
        cookies=COOKIES,
        json={"query": query, "variables": variables},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]


def fetch_recent_accepted_submissions(limit: int):
    query = """
    query recentAcSubmissions($username: String!, $limit: Int!) {
      recentAcSubmissionList(username: $username, limit: $limit) {
        id
        title
        titleSlug
        timestamp
        lang
      }
    }
    """
    username = get_username()
    data = gql(query, {"username": username, "limit": limit})
    return data["recentAcSubmissionList"]


def get_username() -> str:
    query = """
    query globalData {
      userStatus {
        username
        isSignedIn
      }
    }
    """
    data = gql(query, {})
    status = data["userStatus"]
    if not status["isSignedIn"]:
        raise RuntimeError("Not signed in — check your LEETCODE_SESSION cookie.")
    return status["username"]


def fetch_submission_code(submission_id: str) -> str:
    # The public recentAcSubmissionList doesn't include source code.
    # We pull it from the submission details endpoint instead.
    query = """
    query submissionDetails($submissionId: Int!) {
      submissionDetails(submissionId: $submissionId) {
        code
      }
    }
    """
    data = gql(query, {"submissionId": int(submission_id)})
    details = data.get("submissionDetails")
    return details["code"] if details else ""


def fetch_question(title_slug: str) -> dict:
    query = """
    query questionData($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        questionFrontendId
        title
        titleSlug
        content
        difficulty
        topicTags { name }
        categoryTitle
      }
    }
    """
    data = gql(query, {"titleSlug": title_slug})
    return data["question"]


def slugify_folder_name(question_id: str, title_slug: str) -> str:
    return f"{int(question_id):04d}-{title_slug}"


def is_sql_problem(question: dict, lang: str) -> bool:
    if lang in SQL_LANGS:
        return True
    if question.get("categoryTitle", "").lower() == "database":
        return True
    tags = [t["name"].lower() for t in question.get("topicTags", [])]
    return "database" in tags


def write_problem_folder(question: dict, lang: str, code: str) -> pathlib.Path:
    folder_type = "sql" if is_sql_problem(question, lang) else "dsa"
    folder_name = slugify_folder_name(question["questionFrontendId"], question["titleSlug"])
    folder_path = REPO_ROOT / folder_type / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    ext = LANG_EXT.get(lang, "txt")
    solution_path = folder_path / f"solution.{ext}"
    solution_path.write_text(code, encoding="utf-8")

    tags = ", ".join(t["name"] for t in question.get("topicTags", []))
    body_md = html_to_md(html.unescape(question["content"] or ""), heading_style="ATX")

    readme = f"""# {question['questionFrontendId']}. {question['title']}

**Difficulty:** {question['difficulty']}
**Tags:** {tags if tags else '—'}
**Link:** https://leetcode.com/problems/{question['titleSlug']}/

---

{body_md}
"""
    (folder_path / "README.md").write_text(readme, encoding="utf-8")
    return folder_path


def build_index():
    """Regenerate dsa/README.md, sql/README.md, and the root README.md."""
    for folder_type in ("dsa", "sql"):
        base = REPO_ROOT / folder_type
        if not base.exists():
            continue
        rows = []
        for entry in sorted(base.iterdir()):
            if not entry.is_dir():
                continue
            readme = entry / "README.md"
            if not readme.exists():
                continue
            text = readme.read_text(encoding="utf-8")
            title_line = text.splitlines()[0].lstrip("# ").strip()
            diff_match = re.search(r"\*\*Difficulty:\*\*\s*(\w+)", text)
            link_match = re.search(r"\*\*Link:\*\*\s*(\S+)", text)
            difficulty = diff_match.group(1) if diff_match else "?"
            link = link_match.group(1) if link_match else ""
            rows.append((title_line, difficulty, link, entry.name))

        lines = [f"# {folder_type.upper()} Problems\n", "| # | Problem | Difficulty |", "|---|---------|------------|"]
        for title_line, difficulty, link, folder_name in rows:
            lines.append(f"| {folder_name.split('-')[0]} | [{title_line}]({folder_name}/) | {difficulty} |")
        (base / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    dsa_count = len([p for p in (REPO_ROOT / "dsa").iterdir() if p.is_dir()]) if (REPO_ROOT / "dsa").exists() else 0
    sql_count = len([p for p in (REPO_ROOT / "sql").iterdir() if p.is_dir()]) if (REPO_ROOT / "sql").exists() else 0

    root_readme = f"""# LeetCode Solutions

Auto-synced from my LeetCode submissions.

## 📊 Stats
- DSA solved: {dsa_count}
- SQL solved: {sql_count}

See [`dsa/README.md`](dsa/README.md) and [`sql/README.md`](sql/README.md) for the full indexes.
"""
    (REPO_ROOT / "README.md").write_text(root_readme, encoding="utf-8")


def already_synced(question_id: str, title_slug: str) -> bool:
    folder_name = slugify_folder_name(question_id, title_slug)
    return (REPO_ROOT / "dsa" / folder_name).exists() or (REPO_ROOT / "sql" / folder_name).exists()


def main():
    submissions = fetch_recent_accepted_submissions(SUBMISSION_LIMIT)
    new_count = 0

    # Process oldest-first so folder creation order matches solve order.
    for sub in reversed(submissions):
        title_slug = sub["titleSlug"]
        question = fetch_question(title_slug)
        if already_synced(question["questionFrontendId"], title_slug):
            continue

        code = fetch_submission_code(sub["id"])
        if not code:
            print(f"WARNING: no code found for {title_slug}, skipping.")
            continue

        folder = write_problem_folder(question, sub["lang"], code)
        print(f"Synced: {folder.relative_to(REPO_ROOT)}")
        new_count += 1
        time.sleep(1)  # be polite to LeetCode's API

    if new_count > 0:
        build_index()
        print(f"Done. {new_count} new problem(s) synced.")
    else:
        print("No new accepted submissions found.")

    # Signal to the GitHub Action whether there's anything to commit.
    print(f"::set-output name=new_count::{new_count}")


if __name__ == "__main__":
    main()

