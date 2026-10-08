"""Tiny stand-in for the GitHub REST API, for controlled CLI runs (no real accounts).

Run:  python tests/stub_github_server.py 8766 /tmp/github_requests.log
Every request is appended to the log so a run can prove which accounts were (not) queried.
"""

import json
import sys
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _iso(days_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def _repo(name, desc, days, language="Python", topics=()):
    return {"name": name, "html_url": f"https://github.com/x/{name}", "description": desc, "language": language,
            "topics": list(topics), "fork": False, "archived": False, "size": 50,
            "pushed_at": _iso(days), "updated_at": _iso(days)}


def _events(n, spread):
    return [{"type": "PushEvent", "created_at": _iso(1 + (i % spread)), "repo": {"name": "x/y"}} for i in range(n)]


USERS = {
    "janedoe": {  # strong, relevant
        "repos": [_repo("rag-service", "RAG service with embeddings and FastAPI", 4, topics=("llm", "rag")),
                  _repo("agent-lab", "LangGraph agents for research workflows", 12)],
        "events": _events(30, 6),
    },
    "shared-dev": {  # moderate; two resumes point here
        "repos": [_repo("api-tools", "FastAPI helpers for small services", 30)],
        "events": _events(7, 2),
    },
    "alex-rejected": {  # exists, but must never be queried (candidate is rejected)
        "repos": [_repo("anything", "irrelevant", 1)], "events": _events(50, 8),
    },
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        with open(self.server.log_path, "a") as fh:  # type: ignore[attr-defined]
            fh.write(f"GET {path} auth={'yes' if 'Authorization' in self.headers else 'no'}\n")
        _, _, user, *rest = path.split("/")
        if user == "flaky-user":
            return self._send(500, {"message": "internal error"})
        spec = USERS.get(user)
        if spec is None:
            return self._send(404, {"message": "Not Found"})
        self._send(200, spec["events" if rest and rest[0] == "events" else "repos"])

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler)
    server.log_path = sys.argv[2]  # type: ignore[attr-defined]
    print(f"stub GitHub on {server.server_address}", flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Event().wait()
