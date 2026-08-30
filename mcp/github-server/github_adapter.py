from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


MOCK_FILES: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "payments": {
        "src/main/java/com/example/payment/PaymentClient.java": [
            {"line": 1, "content": "package com.example.payment;"},
            {"line": 2, "content": "public class PaymentClient {"},
            {"line": 20, "content": "  private static final int GATEWAY_TIMEOUT_MS = 3000;"},
            {"line": 84, "content": "  public ChargeResult charge(PaymentRequest req) throws PaymentTimeoutException {"},
            {"line": 85, "content": "    try (Connection conn = pool.borrow(3000, MILLISECONDS)) {"},
            {"line": 86, "content": "      return doCharge(req, conn, 3000);"},
            {"line": 87, "content": "    } catch (TimeoutException te) {"},
            {"line": 88, "content": "      throw new PaymentTimeoutException(\"Stripe gateway did not respond within \" + GATEWAY_TIMEOUT_MS + \"ms\");"},
            {"line": 95, "content": "  }"},
            {"line": 140, "content": "}"},
        ],
        "src/main/java/com/example/payment/config/PaymentGatewayConfig.java": [
            {"line": 1, "content": "package com.example.payment.config;"},
            {"line": 10, "content": "@Configuration"},
            {"line": 11, "content": "public class PaymentGatewayConfig {"},
            {"line": 25, "content": "  // v2.4.1: Reduced gateway timeout from 5000ms to 3000ms per performance review."},
            {"line": 26, "content": "  public int gatewayTimeoutMs() { return 3000; }"},
            {"line": 30, "content": "  // v2.4.1: Reduced connection borrow timeout from 5000ms to 3000ms."},
            {"line": 31, "content": "  public int connectionBorrowTimeoutMs() { return 3000; }"},
            {"line": 35, "content": "}"},
        ],
        "src/main/java/com/example/payment/retry/RetryPolicy.java": [
            {"line": 1, "content": "package com.example.payment.retry;"},
            {"line": 12, "content": "public class RetryPolicy {"},
            {"line": 15, "content": "  public static final int MAX_ATTEMPTS = 3;"},
            {"line": 16, "content": "  public static final long BACKOFF_MS = 50;"},
            {"line": 30, "content": "  // Timeouts count towards retries per v2.4.1 change."},
            {"line": 31, "content": "  private boolean isRetryable(Throwable t) { return t instanceof TimeoutException || t instanceof IOException; }"},
            {"line": 50, "content": "}"},
        ],
    },
    "auth": {
        "src/main/java/auth/TokenVerifier.java": [
            {"line": 5, "content": "public class TokenVerifier { public boolean verify(String t) { return Jwts.parser().verify(t); } }"}
        ],
    },
}


MOCK_COMMITS: Dict[str, List[Dict[str, Any]]] = {
    "payments": [
        {
            "sha": "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
            "message": "Increase payment gateway performance: reduce connection borrow timeout 5000→3000",
            "author": "jane.smith",
            "timestamp": "2026-08-30T14:24:12",
            "branch": "main",
            "pr_number": 421,
            "files_changed": [
                "src/main/java/com/example/payment/config/PaymentGatewayConfig.java",
                "src/main/java/com/example/payment/PaymentClient.java",
                "src/main/java/com/example/payment/retry/RetryPolicy.java",
            ],
        },
        {
            "sha": "b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
            "message": "Upgrade Jackson to 2.17.1 (security patch CVE-2026-1234)",
            "author": "dependabot",
            "timestamp": "2026-08-29T20:02:45",
            "branch": "main",
            "pr_number": 420,
            "files_changed": ["pom.xml"],
        },
        {
            "sha": "c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
            "message": "Add payment_method field to order event for analytics",
            "author": "bob.jones",
            "timestamp": "2026-08-28T16:14:03",
            "branch": "main",
            "pr_number": 419,
            "files_changed": ["src/main/java/com/example/payment/OrderEvent.java"],
        },
        {
            "sha": "d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
            "message": "Refactor checkout workflow metrics labels",
            "author": "jane.smith",
            "timestamp": "2026-08-26T11:48:19",
            "branch": "main",
            "pr_number": 417,
            "files_changed": ["src/main/java/com/example/payment/CheckoutMetrics.java"],
        },
        {
            "sha": "e5f60718293a4b5c6d7e8f90a1b2c3d4",
            "message": "Bump version to 2.4.0",
            "author": "release-bot",
            "timestamp": "2026-08-20T09:00:00",
            "branch": "main",
            "pr_number": 415,
            "files_changed": ["pom.xml", "version.txt"],
        },
    ],
    "auth": [
        {"sha": "aa11bb", "message": "Minor: token verifier logging", "author": "ops", "timestamp": "2026-08-27T10:00:00", "branch": "main", "pr_number": 301, "files_changed": ["src/main/java/auth/TokenVerifier.java"]},
    ],
}


MOCK_PRS: Dict[str, Dict[int, Dict[str, Any]]] = {
    "payments": {
        421: {
            "number": 421,
            "title": "Reduce payment gateway timeout thresholds for improved tail latency",
            "author": "jane.smith",
            "status": "MERGED",
            "merged_at": "2026-08-30T14:26:45",
            "branch": "main",
            "head_sha": "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
            "files_changed": 3,
            "review_state": "APPROVED",
            "description": (
                "Reduce connection borrow timeout from 5000ms to 3000ms per perf review. "
                "Also reduce overall gateway timeout to match. Expected to reduce p95 latency "
                "by ~200ms under good conditions. Risk: may cause more timeouts during "
                "degraded Stripe response times. Monitoring will be required post-deploy."
            ),
        },
        420: {
            "number": 420,
            "title": "Upgrade Jackson to 2.17.1 (CVE-2026-1234)",
            "author": "dependabot",
            "status": "MERGED",
            "merged_at": "2026-08-29T20:04:00",
            "branch": "main",
            "head_sha": "b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
            "files_changed": 1,
            "review_state": "APPROVED",
            "description": "Security patch only — no logic changes.",
        },
    },
}


class GitHubAdapter:
    """
    GitHub adapter. Mock mode by default.

    The GitHub token is loaded from GITHUB_TOKEN environment variable INSIDE this adapter,
    and is NEVER surfaced into MCP responses, which means the LLM can never observe it.
    """

    def __init__(self, use_mock: Optional[bool] = None) -> None:
        if use_mock is None:
            use_mock = os.environ.get("GITHUB_MCP_USE_MOCK", "true").lower() in ("1", "true", "yes")
        self._use_mock = use_mock
        self._mock_latency_ms = int(os.environ.get("GITHUB_MCP_MOCK_LATENCY_MS", "40"))
        self._gh_client = None
        if not self._use_mock:
            try:
                from github import Github  # type: ignore
                token = os.environ.get("GITHUB_TOKEN")
                if not token:
                    logger.warning("GITHUB_TOKEN empty — fallback to mock")
                    self._use_mock = True
                else:
                    endpoint = os.environ.get("GITHUB_API_URL")
                    self._gh_client = Github(token, base_url=endpoint) if endpoint else Github(token)
            except Exception as e:
                logger.warning("PyGithub unavailable (%s). Mock fallback.", e)
                self._use_mock = True

    def _sleep(self):
        if self._mock_latency_ms > 0:
            time.sleep(self._mock_latency_ms / 1000.0)

    def search_code(self, repository: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        self._sleep()
        if self._use_mock:
            return self._mock_search_code(repository, query, limit)
        return self._pygithub_search_code(repository, query, limit)

    def _mock_search_code(self, repo: str, query: str, limit: int) -> List[Dict[str, Any]]:
        q = query.lower()
        files_for_repo = MOCK_FILES.get(repo, MOCK_FILES["payments"])
        hits: List[Dict[str, Any]] = []
        for file_path, lines in files_for_repo.items():
            for entry in lines:
                content = f"{file_path}\n{entry.get('content', '')}"
                if q in content.lower() or not q:
                    snippet_lines = []
                    idx = lines.index(entry)
                    for i in range(max(0, idx - 2), min(len(lines), idx + 3)):
                        snippet_lines.append(f"L{lines[i]['line']}: {lines[i]['content']}")
                    hits.append(
                        {
                            "repository": repo,
                            "file": file_path,
                            "line": entry["line"],
                            "snippet": "\n".join(snippet_lines),
                        }
                    )
        hits = hits[: max(1, min(limit, 50))]
        return hits

    def _pygithub_search_code(self, repo, query, limit):  # pragma: no cover
        assert self._gh_client is not None
        out = []
        for result in self._gh_client.search_code(f"repo:{repo} {query}")[:limit]:
            try:
                content = result.decoded_content.decode("utf-8", errors="ignore")
                lines = content.splitlines()
                first_hit = 0
                for i, line in enumerate(lines):
                    if query.lower() in line.lower():
                        first_hit = i + 1
                        break
                snippet = "\n".join(lines[max(0, first_hit - 3) : min(len(lines), first_hit + 4)])
                out.append(
                    {"repository": repo, "file": result.path, "line": first_hit, "snippet": snippet}
                )
            except Exception as e:
                logger.warning("Could not decode result %s: %s", result, e)
        return out

    def get_recent_commits(self, repository: str, branch: str = "main", limit: int = 10) -> List[Dict[str, Any]]:
        self._sleep()
        if self._use_mock:
            commits = MOCK_COMMITS.get(repository, MOCK_COMMITS["payments"])
            return [dict(c) for c in commits[: max(1, min(limit, len(commits)))]]
        return self._pygithub_commits(repository, branch, limit)

    def _pygithub_commits(self, repo, branch, limit):  # pragma: no cover
        assert self._gh_client is not None
        gh_repo = self._gh_client.get_repo(repo)
        out = []
        for c in gh_repo.get_commits(sha=branch)[:limit]:
            out.append(
                {
                    "sha": c.sha,
                    "message": c.commit.message.splitlines()[0],
                    "author": getattr(c.commit.author, "name", "?"),
                    "timestamp": c.commit.author.date.isoformat() if c.commit.author and c.commit.author.date else "",
                    "branch": branch,
                    "files_changed": [f.filename for f in (c.files or [])[:5]],
                }
            )
        return out

    def get_pull_request(self, repository: str, number: int) -> Optional[Dict[str, Any]]:
        self._sleep()
        if self._use_mock:
            prs = MOCK_PRS.get(repository, MOCK_PRS["payments"])
            pr = prs.get(number)
            return dict(pr) if pr else None
        return self._pygithub_pr(repository, number)

    def _pygithub_pr(self, repo, number):  # pragma: no cover
        assert self._gh_client is not None
        gh_repo = self._gh_client.get_repo(repo)
        p = gh_repo.get_pull(number)
        return {
            "number": p.number,
            "title": p.title,
            "author": p.user.login if p.user else "",
            "status": "MERGED" if p.merged else ("OPEN" if p.state == "open" else p.state.upper()),
            "merged_at": p.merged_at.isoformat() if p.merged_at else "",
            "branch": p.base.ref,
            "head_sha": p.head.sha,
            "files_changed": p.changed_files,
            "review_state": "",
            "description": p.body or "",
        }

    def get_file(self, repository: str, file_path: str, ref: str = "main") -> Optional[Dict[str, Any]]:
        self._sleep()
        if self._use_mock:
            files_for_repo = MOCK_FILES.get(repository, MOCK_FILES["payments"])
            lines = files_for_repo.get(file_path)
            if lines is None:
                return None
            content = "\n".join(f"L{l['line']}: {l['content']}" for l in lines)
            return {
                "repository": repository,
                "file_path": file_path,
                "ref": ref,
                "size_bytes": len(content),
                "line_count": len(lines),
                "content": content,
            }
        return self._pygithub_file(repository, file_path, ref)

    def _pygithub_file(self, repo, file_path, ref):  # pragma: no cover
        assert self._gh_client is not None
        gh_repo = self._gh_client.get_repo(repo)
        contents = gh_repo.get_contents(file_path, ref=ref)
        if isinstance(contents, list):
            return None
        body = contents.decoded_content.decode("utf-8", errors="ignore")
        return {
            "repository": repo,
            "file_path": file_path,
            "ref": ref,
            "size_bytes": contents.size,
            "line_count": body.count("\n") + 1,
            "content": body,
        }
