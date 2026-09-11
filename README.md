# form-nv

**Status: NOT IMPLEMENTED — interface only.**

Every public function below is published with its signature and its
effect row, and every body is `todo()`. Installing this package works;
calling it panics with `not implemented`.

## What this is

The two encodings an HTML form sends, decoded from bytes:
`application/x-www-form-urlencoded` to the WHATWG rules, and
`multipart/form-data` as a parser that never holds a part.

- `formscan` — the urlencoded scanner as `@value` state; the device
  claim;
- `formurl` — urlencoded: an ordered pair list of spans, and a lookup
  over it;
- `formpart` — multipart: feed and drain, with limits that refuse;
- `formfield` — typed extraction whose errors name the field;
- `formerr` — every refusal, and the status it should produce.

```
novo pkg add form-nv
novo pkg build
novo test
```

## The one example that will work

An upload handler that streams a file to disk and never holds it.

```novo ignore
use formpart

fn receive<W: Write[e]>(sink: W, content_type: Str, socket: Socket) -> Result<Int, FormError> [e]
    let boundary = formpart.boundary_of(content_type)!
    var r = formpart.reader(boundary, formpart.default_limits())
    var written = 0
    loop
        let chunk = read_some(socket)
        let step = formpart.drain(r, chunk)!
        r = step.reader
        for e in step.events
            match e
                FormBodyChunk(start, end) =>
                    written = written + write_range(sink, chunk, start, end)
                _ =>
                    pass
        if formpart.is_complete(r)
            break
    Ok(written)
```

## The load-bearing interface: `FormEvent`

```novo ignore
pub enum FormEvent
    FormPartStart(info: FormPartInfo)
    FormBodyChunk(start: Int, end: Int)
    FormPartEnd(info: FormPartInfo)
    FormBodyEnd
```

The argument for it is a **security** one rather than an efficiency one.

A multipart body is how a file upload arrives. The obvious API —
`parse(body: Bytes) -> [FormPart]` with a `value: Bytes` on each part —
makes an upload endpoint's memory the **client's** decision: the server
holds every byte of every part before it can look at any of them, and a
request that claims to be a 4 GB video is 4 GB of server memory before a
single check has run. Every framework that shipped that API shipped the
advisory afterwards.

So `FormBodyChunk` carries a **range into the chunk the caller just
fed**. The reader holds no part, no part's bytes, and nothing whose size
the client chooses — `formpart.pending_bytes` is at most the boundary's
length plus four, which is the longest prefix of a boundary that can
straddle two chunks, and it is published precisely so a test can assert
the reader is not accumulating.

A handler that wants the whole part in memory writes the three lines
that accumulate it. The fact that those three lines are the **handler's**
is the point.

`formpart.collect` exists for the caller that genuinely has the whole
body — a test, a small settings form, a queued job — and it takes the
same `FormLimits`. What is deliberately **not** published is a variant
without limits: `collect(body, boundary)` with no bound is the API this
package argues against.

## The second decision: the limits refuse rather than grow

`FormLimits` is parameters, not advice. A part longer than
`max_part_bytes`, a body longer than `max_total_bytes`, more than
`max_parts` parts, a header section longer than `max_headers_bytes`, a
field name longer than `max_name_bytes` — each stops the parse with a
named refusal **at the byte the bound was crossed**, before the byte
after it has been read. A limit checked afterwards is a limit the
attacker has already spent.

Two bounds and not one, because a thousand small parts is the other
shape of the same attack. And they are a value the caller owns:
`default_limits()` is what a public upload endpoint can live with, and
`small_form_limits()` is named because "this endpoint takes no files" is
a decision worth being able to state — a settings form behind
`default_limits()` is an endpoint that will accept 32 MiB.

## The third: `formerr` names the field, and `status_for` is published

A handler reading `age` out of a form gets a `Str`, and the conversion
is three lines it writes per field. Written by hand, the failure is a
`400` with no body, because the handler has no name to put in one. Every
field variant here carries the field's name, so the 400 says which field
and what was expected — which is the difference between a form a person
can correct and a form they abandon. `formfield.check` answers **every**
failed expectation and not the first, because a form with six bad fields
should tell a person about six.

`formerr.status_for` is published because the mapping is a decision and
two handlers making it separately will disagree — and the wrong answer
is a real failure: a `500` for a bad form field tells a client to retry,
and a client that retries a malformed form retries forever. 413 for a
limit, 415 for a content type that is not multipart, 400 for a field.

## The fourth: a boolean's spellings are the web's

```novo ignore
pub fn get_bool(b: FormBody, name: Str) -> Result<Bool, FormError>
pub fn checkbox(b: FormBody, name: Str) -> Bool
```

An HTML checkbox sends `on` when ticked and **nothing at all** when not.
A handler that required `true`/`false` never sees a ticked checkbox; one
that read an absent field as `false` is reading the right answer for the
wrong reason, and would read a *select* with a yes/no option as "no"
when the client simply failed to send it.

So `get_bool` accepts the web's spellings (`on`, `true`, `yes`, `1` and
their negatives) and answers `FormMissing` for an absent field, and
`checkbox` is the one call where absence means false — a separate name
so it cannot be reached by accident.

## The overlap with url-nv, named

url-nv 0.1.1's `qs` module already parses query strings, and the two
packages are **not** two spellings of one thing: that one implements
`urllib.parse`'s rules and this one implements the WHATWG URL
Standard's `application/x-www-form-urlencoded` parser, which is what a
browser sends and therefore what a server receives. They differ in four
places a test can see:

| | url-nv `qs` (urllib) | form-nv `formurl` (WHATWG) |
| --- | --- | --- |
| a field with no value | dropped unless `keep_blank_values` | **always** a key with an empty value |
| the safe set for writing | keeps `~` | percent-encodes `~` |
| hex case on output | lower | **upper** |
| what a parse answers | decoded `Str` pairs, copied | spans into the caller's bytes, decoded on demand |

The first is the one that matters: a browser sends an empty value for a
text input the user left alone, and a parser that dropped it makes "the
user cleared this field" indistinguishable from "the field was not on
the form" — which is how a form's save silently stops clearing values.
The second and third produce bodies that decode to the same string and
compare unequal, which is how a signature over a form body stops
verifying.

**form-nv does not depend on url-nv**, and the second reason is the
device claim: the embedded probe builds everything the modules it names
depend on, and url-nv's parse allocates.

## The device claim is built

`formscan`, and only `formscan`. A firmware serving its own
configuration page gets back `ssid=home&psk=hunter2&chan=6` and has four
kilobytes of RAM; what it cannot do is what `str.split(body, "&")` does
— allocate a list of strings, split each again, and percent-decode each
half into another string. What it can do is walk the body once carrying
four integers in its own stack frame, and that is `FormScan`.

Decoding is **part of the walk** rather than a pass over a copy:
`scan_byte` answers the decoded byte along with the position, so a
device writes straight into its own fixed buffer and never builds the
encoded form. `scan_in_key` is the whole of the dispatch it needs.

What the `@value` shape costs is stated rather than discovered. A
`@value` struct holds scalars only (SPEC § 14.2), so nothing in
`formscan` names a `Str` or a `Bytes`; and a `Result` payload is not a
position a `@value` type may occupy (SPEC § 14.5), so the one refusal it
can carry — a `%` that began no valid escape — is a flag,
`scan_bad_escape`. The WHATWG parser *keeps* such a byte and carries on,
so a device's answer is a browser's answer, and the flag is how a caller
stricter than the standard finds out. base64-nv's decoder and
router-nv's segment scanner answer the same constraint the same way.

`formurl`, `formpart`, `formfield` and `formerr` are **not** claimed:
each names `Bytes` or builds a list, and `tests/embedded_probe.nv` says
so in its own header.

## The layer, and why

`core`. A form body is bytes the caller already holds — the socket that
received them belongs to the server — and decoding one is arithmetic
over those bytes. The multipart half is a feed-and-drain state machine,
which is `docs/publishing.md` § How a `core` package takes bytes from
its host's first shape, chosen over the others because a part is a file
rather than a record and the payload must never accumulate.

There is **no effect-polymorphic signature in this package**, which is
worth naming because every other `core` package in this lane has one. A
writer would be the natural place for it, and this package writes
nothing: the urlencoded serialiser answers a `Str` or fills the caller's
buffer, and the multipart half is a reader. A handler streaming a part
to a sink passes its own `Write` impl to its own function, and the range
this package answered is what it writes.

## The reference implementations

`serde_urlencoded` and the WHATWG URL Standard § 5.1 for the first half;
the standard is the normative one and the crate supplies the API shape,
minus its serde derive — this package answers pairs and `formfield` is
the typed layer, because novo-lang's implicit `Serialize` is a run-time
walk over a value and cannot see a field's optionality.

`multipart` (Rust) and RFC 7578 for the second, with RFC 2046 § 5.1.1
for the boundary grammar. What is ported is its streaming reader; what
is not is its `SaveBuilder`, which writes files — that is a `host`
concern and belongs to whatever adopts this.

The vectors are the WHATWG's own `urlencoded` web-platform tests for the
first half, and `multipart`'s own fixture bodies plus the four cases
every multipart parser is measured on for the second: a boundary
appearing inside a part's body, a part whose headers straddle two
chunks, a body with no final `--`, and a `filename` containing a path
separator.

## The consumers, and what adopting this would take

**`compiler/stdlib/http_server.nv`** is the first, and it has both
halves by hand. `http_server_query_get(query, key)` walks `&`-separated
fields with `str.split` and answers the **first** match — so a repeated
key silently loses every value but one, which is a multi-select's whole
content — and `http_server_url_decode` is a 25-line percent-decoder
beside it, with `http_server_hex_pair` and a 22-arm `http_server_hex_digit`
match under that. `formurl.get_all` is the first, `formurl.decode` the
second, and `formscan.hex_value` the third; adopting them deletes about
sixty lines and gains the repeated key.

The standard library has **no multipart support at all**, so an upload
endpoint written against it today has to write the parser. That is the
gap this package is for.

**`web`** (the planned `web`/`host` row, "routing, middleware,
extractors") is the named consumer in the plan, and `formfield`'s shape
is what an extractor calls: `check` answers every bad field, and an
extractor turns that list into a 400 whose body a person can act on.

**`orbit/http-server`** is the pool's own client and is named here only
so the absence is on the record: it serves a fixed response and parses
no bodies, so it is not a consumer until it grows a form.

## What a row wanted to widen

Nothing widened. Every function in this package is `[]`, and unlike its
siblings none of them is effect-polymorphic, for the reason in § The
layer.

Three findings:

1. **The plan's row and url-nv overlap, and the overlap is a feature
   rather than a duplicate** — but only because the two implement
   different standards, and that is a sentence somebody has to be
   willing to defend. § The overlap with url-nv is that defence, with
   four differences a test can see. If the answer is "one of them
   should go", the decision belongs to whoever owns both rows and the
   WHATWG half is the one a server needs.
2. **The stdlib's own form handling loses repeated keys**, silently,
   today. That is not a limitation of an interface package; it is a
   defect in shipped code that this package's existence makes visible,
   and § The consumers names the three calls that fix it.
3. **The device claim covers one module of five**, and the probe says so
   in its own header rather than leaving a reader to infer it from a
   passing row. `core-embedded` is green because `tests/embedded_probe.nv`
   names `formscan` and nothing else.

## The surface

| module | `pub fn` | `pub struct` | `pub enum` |
| --- | --- | --- | --- |
| `formscan` | 21 | 1 (`@value`) | 0 |
| `formurl` | 20 | 3 | 0 |
| `formpart` | 24 | 7 | 2 |
| `formfield` | 22 | 1 | 1 |
| `formerr` | 6 | 0 | 1 |
| **total** | **93** | **12** | **4** (34 variants) |

One `impl Error` block, for `FormError`.
