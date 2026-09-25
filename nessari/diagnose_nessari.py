#!/usr/bin/env python3
"""Find out why Nessari's replies hang. Run while `chat` is running in another
Termux session, then paste the whole output back.

  python diagnose_nessari.py
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8080"
HTML = Path.home() / "chatbot" / "index.html"
sys.path.insert(0, str(Path(__file__).resolve().parent))


def req(path, body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data,
                               headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode(errors="replace"), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace"), time.time() - t
    except Exception as e:
        return None, f"{type(e).__name__}: {e}", time.time() - t


def chat(system, timeout):
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": "Say hi in five words."}]
    code, body, secs = req("/v1/chat/completions",
                           {"messages": msgs, "max_tokens": 16, "stream": False}, timeout)
    try:
        j = json.loads(body)
        reply = j["choices"][0]["message"]["content"]
        usage = j.get("usage", {})
        return f"OK in {secs:.0f}s, prompt tokens={usage.get('prompt_tokens')}, reply={reply!r}"
    except Exception:
        return f"FAILED after {secs:.0f}s (HTTP {code}): {body[:300]}"


def main():
    print("1. health:", *req("/health")[:2])

    code, body, _ = req("/props")
    if code == 200:
        try:
            p = json.loads(body)
            gs = p.get("default_generation_settings", {})
            print(f"2. server: slots={p.get('total_slots')} "
                  f"ctx_per_slot={gs.get('n_ctx')} build={p.get('build_info', '?')}")
        except Exception:
            print("2. props:", body[:200])
    else:
        print("2. props:", code, body[:200])

    print("3. tiny chat, no personality:", chat(None, 120))

    persona = None
    if HTML.exists():
        html = HTML.read_text(encoding="utf-8", errors="replace")
        try:
            from repair_nessari import repair
            persona = repair(html)[1]
        except Exception as e:
            print("   could not read persona:", e)
        urls = sorted(set(re.findall(r"""['"`](/(?:v1/)?[a-z_/]*(?:completion|chat)[a-z_/]*)""", html)))
        print("4. endpoints the page calls:", urls or "none found")
        m = re.search(r"catch\s*\(\s*\w*\s*\)\s*\{[^}]{0,200}", html)
        print("   page has error handling:", bool(m))
    if persona:
        print(f"5. chat WITH Nessari personality ({len(persona)} chars):", chat(persona, 300))


if __name__ == "__main__":
    main()
