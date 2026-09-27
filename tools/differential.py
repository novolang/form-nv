#!/usr/bin/env python3
"""Write tests/differential_tests.nv from Python's standard library.

Three second opinions, each used where it and the specification agree:

- `urllib.parse.parse_qsl(..., keep_blank_values=True)` reads random
  urlencoded bodies, and each body's pairs are compared with
  `formurl.parse`.  Python replaces an invalid UTF-8 sequence with
  U+FFFD, as the WHATWG parser does and this package does not, so a
  body whose answer holds U+FFFD is not used.
- `urllib.parse.urlencode(..., safe="*", quote_via=quote_plus)` writes
  random pairs, compared with `formurl.serialise`.  Python leaves `~`
  unescaped and the WHATWG serialiser escapes it, so a pair holding `~`
  is not used.
- `email.parser.BytesParser` with the `HTTP` policy reads random
  `multipart/form-data` bodies, and each part's name, filename and bytes
  are compared with `formpart.collect`.

Usage:
    python3 tools/differential.py > tests/differential_tests.nv
    novo fmt tests/differential_tests.nv
"""
import email.parser
import email.policy
import random
import sys
import urllib.parse

rng = random.Random(7578)


def nv(s):
    """A Novo string literal."""
    out = []
    for ch in s:
        if ch == '\\':
            out.append('\\\\')
        elif ch == '"':
            out.append('\\"')
        elif ch == '$':
            out.append('\\$')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\t':
            out.append('\\t')
        else:
            out.append(ch)
    return '"' + ''.join(out) + '"'


def urlencoded_cases(n):
    alphabet = list("ab=&+%2F4 1zé~.") + ["%41", "%C3%A9", "%2B", "%26", "%3D"]
    out = []
    while len(out) < n:
        body = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 14)))
        pairs = urllib.parse.parse_qsl(body, keep_blank_values=True)
        if any("�" in k or "�" in v for k, v in pairs):
            continue
        out.append((body, "|".join(k + "=" + v for k, v in pairs)))
    return out


def serialise_cases(n):
    alphabet = list("aZ09 *-._&=+/?é~") + ["€", "\t"]
    out = []
    while len(out) < n:
        pairs = [("".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 5))),
                  "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 6))))
                 for _ in range(rng.randrange(1, 4))]
        if any("~" in k or "~" in v for k, v in pairs):
            continue
        text = urllib.parse.urlencode(pairs, safe="*", quote_via=urllib.parse.quote_plus)
        out.append((pairs, text))
    return out


def multipart_cases(n):
    words = ["alpha", "b e t a", "--", "line one\r\nline two", "é", "x" * 40, "", "a=b; c"]
    out = []
    while len(out) < n:
        boundary = "b" + "".join(rng.choice("0123456789abcdef") for _ in range(12))
        parts = []
        for i in range(rng.randrange(1, 4)):
            name = "f%d" % i
            lines = ['Content-Disposition: form-data; name="%s"' % name]
            if rng.random() < 0.4:
                lines[0] += '; filename="file%d.txt"' % i
                lines.append("Content-Type: text/plain")
            content = rng.choice(words) + rng.choice(words)
            parts.append("\r\n".join(["--" + boundary] + lines + ["", content]))
        body = "\r\n".join(parts) + "\r\n--" + boundary + "--\r\n"
        head = "Content-Type: multipart/form-data; boundary=%s\r\n\r\n" % boundary
        msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
            head.encode() + body.encode())
        seen = []
        for p in msg.iter_parts():
            seen.append((p.get_param("name", header="content-disposition"),
                         p.get_filename() or "",
                         p.get_payload(decode=True).decode("utf-8")))
        out.append((boundary, body, seen))
    return out


def main():
    w = sys.stdout.write
    w("// differential_tests.nv — Python's urllib.parse and email packages as\n")
    w("// a second opinion.\n//\n")
    w("// Written by tools/differential.py with Python %s.  The tool's\n" % sys.version.split()[0])
    w("// docstring says which cases are used and why.\n\n")
    w("use std.test\nuse std.list\nuse std.str\nuse std.bytes\nuse formurl\nuse formpart\n\n")
    w("// Every pair of a body as `name=value`, decoded, joined with `|`.\n")
    w("fn pairs_of(src: Str) -> Str\n")
    w("    let b = formurl.parse_str(src)\n")
    w("    var out: [Str] = []\n")
    w("    for p in b.pairs\n")
    w("        list.push(out, formurl.key_str(b, p) + \"=\" + formurl.value_str(b, p))\n")
    w("    str.join(out, \"|\")\n\n")
    w("@test\nfn test_python_parse_qsl_reads_the_same_pairs() [io]\n")
    for body, want in urlencoded_cases(40):
        w("    test.assert(pairs_of(%s) == %s)\n" % (nv(body), nv(want)))
    w("\n@test\nfn test_python_urlencode_writes_the_same_body() [io]\n")
    for pairs, text in serialise_cases(30):
        lit = "[" + ", ".join("(%s, %s)" % (nv(k), nv(v)) for k, v in pairs) + "]"
        w("    test.assert(formurl.serialise(%s) == %s)\n" % (lit, nv(text)))
    w("\n@test\nfn test_python_email_reads_the_same_parts() [io]\n")
    for i, (boundary, body, seen) in enumerate(multipart_cases(12)):
        w("    let p%d = formpart.collect(bytes.from_str(%s), %s, formpart.default_limits())!\n"
          % (i, nv(body), nv(boundary)))
        w("    test.assert(list.len(p%d) == %d)\n" % (i, len(seen)))
        for j, (name, filename, content) in enumerate(seen):
            w("    test.assert(p%d[%d].info.name == %s)\n" % (i, j, nv(name)))
            w("    test.assert(p%d[%d].info.filename == %s)\n" % (i, j, nv(filename)))
            w("    test.assert(bytes.to_str(p%d[%d].bytes) == %s)\n" % (i, j, nv(content)))


main()
