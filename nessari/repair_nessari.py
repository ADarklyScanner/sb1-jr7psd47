#!/usr/bin/env python3
"""Repair Nessari's broken preset in ~/chatbot/index.html.

What it does:
  1. Copies every existing variant into ~/chatbot/recovery/ (never overwrites
     an earlier recovery copy).
  2. Finds the `{ name: 'Nessari', text: ... }` preset, pulls out the
     personality text even if the string literal is broken (raw newlines,
     unescaped quotes), and re-writes it as one valid, escaped JS string.
  3. Checks every inline <script> with `node --check` when node is installed.
  4. Writes the result to ~/chatbot/index.html only if the checks pass.
     If the current file can't be repaired, it tries the backups in order.

Usage (in Termux):
  python repair_nessari.py            # repair
  python repair_nessari.py --dry-run  # report only, change nothing
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CHAT = Path.home() / "chatbot"
TARGET = CHAT / "index.html"
CANDIDATES = ["index.html", "index.html.backup", "index.html.before_yandere"]

PRESET_START = re.compile(r"\{\s*name:\s*(['\"])Nessari\1\s*,\s*text:\s*")
# The preset after Nessari (e.g. Friendly helper), or the end of the array.
NEXT_PRESET = re.compile(r"\n([ \t]*)\{\s*name:\s*['\"]")
ARRAY_END = re.compile(r"\n([ \t]*)\]\s*;")


def unescape_js(body):
    """Undo JS string escapes without touching non-ASCII characters."""
    out, i = [], 0
    simple = {"n": "\n", "t": "\t", "r": "", "\\": "\\", '"': '"', "'": "'",
              "`": "`", "/": "/", "b": "", "f": "", "0": "", "\n": ""}
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            n = body[i + 1]
            if n == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", body[i + 2:i + 6]):
                out.append(chr(int(body[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(simple.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def extract_persona(raw):
    """Turn whatever sits between `text:` and the closing `}` into plain text."""
    raw = raw.strip()
    raw = re.sub(r"\}\s*,?\s*$", "", raw).strip()  # drop the preset's closing }
    raw = raw.rstrip(",").strip()
    # A `"a" + "b"` concatenation from an earlier fix attempt: join the pieces.
    pieces = re.findall(r'"((?:[^"\\]|\\.)*)"', raw, flags=re.S)
    if raw.startswith('"') and pieces and re.fullmatch(
            r'\s*(?:"(?:[^"\\]|\\.)*"\s*\+?\s*)+', raw, flags=re.S):
        return "".join(unescape_js(p) for p in pieces)
    # Otherwise strip one pair of outer quotes, whatever kind they are.
    if raw[:1] in "\"'`":
        q = raw[0]
        raw = raw[1:]
        if raw.endswith(q):
            raw = raw[:-1]
    return unescape_js(raw)


def normalize(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def encode_js(text):
    s = json.dumps(text, ensure_ascii=False)
    # Keep the HTML parser from ending the <script> early.
    return s.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def repair(html):
    starts = list(PRESET_START.finditer(html))
    if not starts:
        raise ValueError("no Nessari preset found")
    if len(starts) > 1:
        raise ValueError(f"{len(starts)} Nessari presets found (expected 1)")
    m = starts[0]
    rest = html[m.end():]
    nxt = NEXT_PRESET.search(rest)
    end_match = nxt or ARRAY_END.search(rest)
    if not end_match:
        raise ValueError("could not find where the Nessari preset ends")
    raw = rest[:end_match.start()]
    persona = normalize(extract_persona(raw))
    if len(persona) < 50:
        raise ValueError("extracted personality is suspiciously short")
    trail = "," if nxt else ""
    fixed = html[:m.start()] + "{ name: 'Nessari', text: " + encode_js(persona) + " }" + trail
    return fixed + rest[end_match.start():], persona


def inline_scripts(html):
    return [m.group(1) for m in re.finditer(
        r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, flags=re.S | re.I)]


def js_ok(html):
    """True/False from node --check, or None when node isn't installed."""
    node = shutil.which("node")
    if not node:
        return None, "node not installed; skipped syntax check"
    for n, code in enumerate(inline_scripts(html)):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(code)
        r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
        Path(f.name).unlink()
        if r.returncode != 0:
            err = (r.stderr or r.stdout).strip().splitlines()
            return False, f"script #{n + 1}: " + " | ".join(err[:4])
    return True, "JavaScript syntax OK"


def structure_ok(html):
    checks = {
        "const PRESETS": html.count("const PRESETS") == 1,
        "function systemPrompt()": "function systemPrompt()" in html,
        "</script>": "</script>" in html,
        "</html>": "</html>" in html.lower(),
    }
    bad = [k for k, v in checks.items() if not v]
    return not bad, ("structure OK" if not bad else "missing/odd: " + ", ".join(bad))


def main():
    dry = "--dry-run" in sys.argv
    if not TARGET.exists():
        sys.exit(f"ERROR: {TARGET} does not exist")

    if not dry:
        rec = CHAT / "recovery" / time.strftime("%Y%m%d-%H%M%S")
        rec.mkdir(parents=True, exist_ok=True)
        for name in CANDIDATES:
            p = CHAT / name
            if p.exists():
                shutil.copy2(p, rec / name)
        print(f"Saved copies of all variants to {rec}\n")

    chosen = None
    for name in CANDIDATES:
        p = CHAT / name
        if not p.exists():
            continue
        html = p.read_text(encoding="utf-8", errors="replace")
        print(f"== {name} ({len(html)} bytes)")
        try:
            fixed, persona = repair(html)
        except ValueError as e:
            print(f"   cannot repair: {e}\n")
            continue
        s_ok, s_msg = structure_ok(fixed)
        j_ok, j_msg = js_ok(fixed)
        print(f"   personality: {len(persona)} chars (~{len(persona) // 4} tokens)")
        print(f"   {s_msg}; {j_msg}")
        print(f"   starts: {persona[:90]!r}...\n")
        if s_ok and j_ok is not False:
            chosen = (name, fixed, j_ok)
            break

    if not chosen:
        sys.exit("No variant could be repaired. Nothing was changed. "
                 "Send me the output above.")

    name, fixed, j_ok = chosen
    if dry:
        print(f"[dry run] Would write repaired {name} to {TARGET}")
        return
    TARGET.write_text(fixed, encoding="utf-8")
    print(f"Wrote repaired {name} -> {TARGET}")
    if j_ok is None:
        print("Tip: `pkg install nodejs` lets this script fully verify the JavaScript.")
    print("\nNext: run `chat`, open http://127.0.0.1:8080, then "
          "Settings -> Personality -> Nessari, and start a new chat.")


if __name__ == "__main__":
    main()
