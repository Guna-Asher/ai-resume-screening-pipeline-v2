"""A tiny OpenAI-compatible server for controlled tests (no real model, no network).

It "analyses" a resume with keyword rules, so the real adapter, prompt, parser and
scoring integration can be exercised end to end. Markers placed inside a resume
select failure behaviour:  STUB:500  STUB:MALFORMED  STUB:SLOW

Run standalone:  python tests/stub_llm_server.py 8765
"""

import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SIGNAL_RULES = [
    (r"openai|chatbot|llm|gpt", "llm_usage"),
    (r"dense vectors|\brag\b|retriev", "rag"),
    (r"dense vectors|embedding", "embeddings"),
    (r"checks that run on every commit|pytest|unit test", "testing"),
    (r"langgraph|agent", "agents"),
    (r"state", "state_management"),
]


def analyse(prompt: str) -> dict:
    projects: dict[str, list[dict]] = {}
    current = None
    for line in prompt.splitlines():
        m = re.match(r"\[PROJECT: (.+)\]", line)
        if m:
            current = m.group(1)
            projects.setdefault(current, [])
            continue
        if line.startswith("[") or current is None or not line.strip():
            current = current if not line.startswith("[") else None
            continue
        for pattern, signal in SIGNAL_RULES:
            if re.search(pattern, line, re.I):
                projects[current].append({"signal": signal, "evidence": line.lstrip("-• ").strip()})
    out = []
    for name, signals in projects.items():
        kinds = {s["signal"] for s in signals}
        out.append(
            {
                "project_name": name,
                "summary": f"Stub analysis of {name}",
                "signals": signals,
                "depth_assessment": "shallow" if kinds <= {"llm_usage"} and kinds else "moderate",
                "shallow_wrapper": bool(kinds) and kinds <= {"llm_usage"},
                "concerns": [],
            }
        )
    return {"projects": out, "overall_evidence": ["stub"], "confidence_notes": []}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _send(self, status: int, body: dict | str):
        data = (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        user = payload["messages"][-1]["content"]
        self.server.requests.append(user)  # type: ignore[attr-defined]
        if "STUB:500" in user:
            return self._send(500, "SECRET-PROVIDER-ERROR-BODY")
        if "STUB:SLOW" in user:
            time.sleep(3)
        content = "this is not json" if "STUB:MALFORMED" in user else json.dumps(analyse(user))
        self._send(200, {"choices": [{"message": {"content": content}}]})


def start(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.requests = []  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


if __name__ == "__main__":
    srv, url = start(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
    print(f"stub LLM listening on {url}", flush=True)
    threading.Event().wait()
