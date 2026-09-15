# form-nv

An HTML form sends its fields to a server in one of two encodings.
`application/x-www-form-urlencoded` is a single line of `key=value`
pairs, specified by the
[WHATWG URL Standard section 5](https://url.spec.whatwg.org/#urlencoded-parsing).
`multipart/form-data` is a sequence of parts with their own headers,
specified by [RFC 7578](https://www.rfc-editor.org/rfc/rfc7578), and is
how a file upload arrives. This package reads both from bytes the
caller already holds, and writes the first.

**Status: NOT IMPLEMENTED — interface only.** Every function is
declared with its full signature, but every body is a `todo()` that
panics when called. The package is published so its design can be
reviewed and depended on before it is implemented. Version 0.1.0 will
be the first working release.

## What a form body is

A browser posting a form with no file inputs sends
`application/x-www-form-urlencoded`. The body is one line. Fields are
separated by `&`, a key is separated from its value by `=`, a space is
written as `+`, and any other byte outside a small safe set is written
as `%` and two hexadecimal digits. Section 5.1 of the standard is the
parser and section 5.3 is the serialiser.

A key may appear more than once. A checkbox group, a multi-select and a
repeated query parameter all send that, so a body is an ordered list of
pairs rather than a map. A field with no `=` is a key with an empty
value. The standard's parser has no error case at all: a `%` that
begins no valid escape is kept as a literal `%`.

A browser posting a form with a file input sends
`multipart/form-data`. The body is a sequence of **parts**. Each part
has its own header section, then a blank line, then its bytes. A
**boundary** string, given as a parameter of the request's
`Content-Type` header, separates the parts: the delimiter on the wire
is `--` followed by the boundary, and the body ends with that delimiter
plus a further `--`. RFC 2046 section 5.1.1 is the boundary grammar.

Each part carries a `Content-Disposition: form-data` header with a
`name` parameter, which is the form field's name (RFC 7578 section
4.2). A part that is a file also carries a `filename` parameter, and
may carry its own `Content-Type`. A file part without one is
`text/plain` (section 4.4).

This package reads a multipart body as a stream of **events**. A body
chunk arrives as a start and an end index into the chunk the caller
just fed, so the parser holds no part and no part's bytes. Whether to
accumulate a part in memory is then the caller's decision rather than
the client's.

Every function in this package performs no input and no output. It
opens no socket and writes no file.

## Install

```
novo pkg add form-nv
```

## Example

```novo
use std.bytes
use formurl
use formfield
use formerr

fn main() [io]
    // A form body as it arrived in the request, with one field repeated.
    let body = formurl.parse(bytes.from_str("name=ada+lovelace&tag=a&tag=b&age=36"))

    // The first value under a key. Nothing is decoded until asked for.
    match formurl.get(body, "name")
        Some(v) => println("name is ${v}")
        None    => println("no name field")

    // Every value under a repeated key, in the order the client sent.
    for t in formurl.get_all(body, "tag")
        println("tag ${t}")

    // A typed read. The refusal names the field, so the reply can too.
    match formfield.get_int(body, "age")
        Ok(n)  => println("age is ${n}")
        Err(e) => println("${formerr.status_for(e)} ${e.message()}")
```

Build and test with `novo pkg build` and `novo test`. Today `novo test`
fails on purpose: every test reaches a
`not implemented: form-nv.<module>.<fn>` panic. The tests are the
specification the implementation will have to satisfy.

## What the package contains

| Module | Contents |
| --- | --- |
| `formscan` | The urlencoded walk as a `@value` struct of four integers: one byte in, the decoded byte and the field boundaries out. |
| `formurl` | The urlencoded body as an ordered list of key and value ranges, the lookups over it, and the serialiser. |
| `formpart` | The multipart reader: the boundary, the limits, and the events a fed chunk produces. |
| `formfield` | Typed reads of a urlencoded body, and a list of expectations checked in one call. |
| `formerr` | Every refusal, the field it names, and the HTTP status it should produce. |

## How to choose an entry point

**`formurl.parse` reads a whole urlencoded body.** It cannot fail. Use
`parse_bounded` on a public endpoint, which refuses a body with more
than a given number of pairs.

**`formfield` is the typed layer over `formurl`.** `get_int`,
`get_bool`, `get_float`, `get_list` and their neighbours each answer a
`Result` whose error names the field. `check` takes a list of
expectations and answers every one that failed, so a reply can list six
bad fields at once.

**`formscan` is the urlencoded parser with no strings in it.** It takes
one byte at a time and answers the decoded byte with the position, so a
caller writes into a fixed buffer of its own. See "Running on a
microcontroller".

**`formpart.feed` and `take` are the multipart reader.** `feed` takes a
chunk and answers the next event with the reader to use next. `drain`
is `feed` followed by `take` until the events stop, which is the loop
most callers want. `finish` ends the body.

**`formpart.collect` reads a whole multipart body into a list of
parts.** Use it when the whole body is already in memory: a test, a
queued job, a small form. It takes the same limits as the reader, and
there is no variant without them.

## The rules a user needs

1. **A body is an ordered list of pairs, not a map.** `formurl.get`
   answers the first value under a key and `get_all` answers every one.
   A handler reading a checkbox group or a multi-select with `get` sees
   one of the values the client sent. WHATWG URL Standard section 5.1.
2. **A field with no value is a key with an empty value, always.** The
   WHATWG parser has no option to drop it. A browser sends one for a
   text input the user cleared, so dropping it makes "cleared" and "not
   on the form" the same request.
3. **`formurl.parse` cannot fail.** A `%` that begins no valid escape is
   kept as a literal `%`, and an entirely empty field is skipped. A
   caller stricter than the standard reads `FormBody.had_bad_escape` or
   counts the pairs.
4. **A pair is two ranges into the caller's bytes.** `key_str` and
   `value_str` decode one field each, so a handler reading three fields
   of a hundred pays for three.
5. **Pass `formpart.reader` the boundary, not the delimiter.** The
   `Content-Type` parameter is the boundary. The delimiter on the wire
   is `--` and then the boundary (RFC 2046 section 5.1.1).
   `formpart.boundary_of` extracts it from the header value.
6. **A `FormBodyChunk` event is a range into the chunk just fed**, not
   bytes the reader owns. Read or copy it before feeding the next
   chunk. `formpart.pending_bytes` is what the reader is holding, and
   it is at most the boundary's length plus four, which is the longest
   boundary prefix that can straddle two chunks.
7. **One call to `feed` produces one event.** A single read from a
   socket can complete several. Call `take` until it stops, or call
   `drain`, which is that loop written once.
8. **The limits refuse at the byte the bound is crossed.** A limit
   checked after the body has arrived is a limit the client has already
   spent. `FormLimits` has six bounds, and both a per-part and a
   whole-body byte bound, because a thousand small parts is the other
   shape of the same request.
9. **`small_form_limits()` is not `default_limits()`.** A settings form
   behind the default accepts 32 MiB. See the table below.
10. **A `filename` from a client is not a path.** RFC 7578 section 4.2
    says a client should send a basic name, and a client is free to
    send `../../etc/passwd`. Check with `formpart.filename_is_safe`
    before using one.
11. **A part with a `filename` is a file even when the filename is
    empty.** A browser sends that for a file input the user left alone.
    `FormPartInfo.is_file` is the flag and `filename` is the value.
12. **A file part with no `Content-Type` is `text/plain`** (RFC 7578
    section 4.4). `formpart.content_type_or_default` applies that rule.
13. **An absent checkbox sends nothing at all.** A ticked one sends
    `on`. `formfield.get_bool` accepts `on`, `true`, `yes`, `1` and
    their negatives, and answers `FormMissing` for an absent field.
    `formfield.checkbox` is the one call where absence means false, and
    it is a separate name so it cannot be reached by accident.
14. **`formfield.check` answers every failed expectation, not the
    first.** A form with six bad fields should tell a person about six.
15. **`formerr.status_for` is the status a refusal should produce.**
    413 for a limit, 415 for a content type that is not multipart, 400
    for a field. A 500 tells a client to retry, and a client retrying a
    malformed form retries forever.

## Sizes and limits

| `FormLimits` field | `default_limits()` | `small_form_limits()` |
| --- | --- | --- |
| `max_part_bytes` | 8 MiB | 64 KiB |
| `max_total_bytes` | 32 MiB | 64 KiB |
| `max_parts` | 64 | 32 |
| `max_headers_bytes` | 16 KiB | 16 KiB |
| `max_headers` | 32 | 32 |
| `max_name_bytes` | 256 | 256 |

The default numbers are the order nginx's `client_max_body_size` and
the common framework defaults sit at. A caller with a different threat
model writes its own `FormLimits`.

## Running on a microcontroller

novo-lang lets a package state which of its modules can run on a device
with no heap allocator, and the compiler checks that claim on every
build. Here the claim covers `formscan` and nothing else.

`FormScan` is four integers in a `@value` struct, carried in the
caller's own stack frame. `scan_byte` takes one byte and answers the
decoded byte with the position, so decoding is part of the walk and no
encoded copy is ever built. A firmware serving its own configuration
page receives `ssid=home&psk=hunter2&chan=6` and writes each decoded
byte straight into a fixed buffer.

```bash
novo build --target=nrf52-qemu tests/embedded_probe.nv
```

That command builds a Cortex-M4 executable today, against `formscan`
alone. It links the signatures and the types rather than a decoder,
because every body under `src/` is still a `todo()`. Keeping it green
once the bodies land is part of the implementation.

`formurl`, `formpart`, `formfield` and `formerr` are outside the claim.
Each names `Bytes` or builds a list, and one host-only function
anywhere in a compilation unit is an undefined symbol at link time on a
device.

`formscan` carries one refusal, a `%` that begins no valid escape, as
the flag `scan_bad_escape` rather than as a `Result`. A `@value`
struct's fields are scalars only (SPEC section 14.2), and a `@value`
type is not allowed as a `Result` payload (SPEC section 14.5). The
WHATWG parser keeps such a byte and carries on, so the flag is how a
caller stricter than the standard finds out.

## What is not included

- **A socket, a file and a clock.** This package declares no effects.
  The bytes arrive from the caller, and a part streamed to disk is
  written by the caller from the range this package answered.
- **A multipart writer.** This package reads `multipart/form-data` and
  does not produce it. The urlencoded serialiser is
  `formurl.serialise`.
- **An unbounded `collect`.** Every entry point that assembles anything
  takes a `FormLimits`.
- **Deserialising a form into a struct.** `formfield` answers typed
  values one field at a time. novo-lang's implicit `Serialize` is a
  run-time walk over a value and cannot see whether a field is
  optional.
- **Query-string parsing to urllib's rules.** See "Related packages".
- **A device build of anything but `formscan`.** See above.

## Related packages

- [url-nv](https://novo-lang.org/packages/url-nv) parses URLs, and its
  `qs` module parses query strings to Python `urllib`'s rules. This
  package implements the WHATWG URL Standard's parser, which is what a
  browser sends. The two differ in four places a program can see.

  | | url-nv `qs` | form-nv `formurl` |
  | --- | --- | --- |
  | a field with no value | dropped unless asked for | always a key with an empty value |
  | `~` when writing | kept | percent-encoded |
  | hexadecimal case when writing | lower | upper |
  | what a parse answers | decoded strings, copied | ranges into the caller's bytes |

  Take url-nv for a query string a program wrote. Take this package for
  a body a browser sent. This package does not depend on url-nv.
- [mime-nv](https://novo-lang.org/packages/mime-nv) parses a media type
  and its parameters. `formpart.boundary_of` is the whole of the
  dependency on it, kept in one function so a caller that already has
  the boundary never reaches it.
- [http-codec-nv](https://novo-lang.org/packages/http-codec-nv) reads
  and writes HTTP/1.1 messages, including the `Content-Type` header
  value this package needs and the body bytes it parses.
- [router-nv](https://novo-lang.org/packages/router-nv) matches the
  request path that decides which handler reads the form.
- `std.http_server` in the standard library parses query strings and
  percent-decodes by hand, and answers only the first value under a
  repeated key. It has no multipart support.

## Tests

```bash
novo test tests/formurl_tests.nv       # the WHATWG parser and serialiser
novo test tests/formpart_tests.nv      # the boundary, the events, the limits
novo test tests/formfield_tests.nv     # typed reads and the expectation list
```

The urlencoded vectors are the WHATWG's own web-platform tests for
`urlencoded` parsing and serialising. The reference implementation for
the API shape is the Rust crate `serde_urlencoded`. The multipart
vectors are the Rust crate `multipart`'s fixture bodies, with RFC 7578
for the part headers and RFC 2046 section 5.1.1 for the boundary
grammar.

The suite asserts the four cases every multipart parser is measured on:
a boundary string appearing inside a part's body, a part whose headers
straddle two fed chunks, a body with no closing `--`, and a `filename`
containing a path separator. It also asserts that a repeated key keeps
every value in order, that a field with no `=` is a key with an empty
value, that each limit refuses at the byte it is crossed, and that
`check` answers every failed expectation.

`tests/embedded_probe.nv` is the device claim as a program. It builds a
Cortex-M4 executable against `formscan` alone.

The tests compile today and fail at run, each on the
`not implemented: form-nv.<module>.<fn>` panic that is its body. That is
the expected state of an interface release. They turn green one at a
time as bodies land.

## Implementation status

| Item | Implemented |
| --- | --- |
| `formscan.FormScan` and the other types in every module | the types are declared |
| `formscan.scan`, `.scan_byte`, `.scan_end` | no |
| `formscan.scan_emitted`, `.scan_out`, `.scan_in_key`, `.scan_key_done`, `.scan_field_done` | no |
| `formscan.scan_pos`, `.scan_field_start`, `.scan_fields`, `.scan_has_value` | no |
| `formscan.scan_in_escape`, `.scan_bad_escape` | no |
| `formscan.separator`, `.assigner`, `.plus_means`, `.hex_value`, `.hex_digit`, `.byte_safe`, `.encoded_len` | no |
| `formurl.parse`, `.parse_str`, `.parse_bounded`, `.scan_all` | no |
| `formurl.get`, `.get_all`, `.has`, `.count`, `.keys` | no |
| `formurl.key_str`, `.value_str`, `.value_bytes`, `.span_bytes`, `.decoded_len` | no |
| `formurl.serialise`, `.serialise_into`, `.serialised_len`, `.encode`, `.decode`, `.is_safe` | no |
| `formpart.default_limits`, `.small_form_limits`, `.reader` | no |
| `formpart.boundary_of`, `.boundary_of_type`, `.boundary_ok` | no |
| `formpart.feed`, `.take`, `.drain`, `.finish` | no |
| `formpart.phase_of`, `.part_count`, `.total_bytes`, `.is_complete`, `.pending_bytes` | no |
| `formpart.content_type_or_default`, `.filename_is_safe` | no |
| `formpart.headers_of`, `.header_name`, `.header_value`, `.header` | no |
| `formpart.collect`, `.part_named`, `.parts_named` | no |
| `formfield.get_str`, `.get_int`, `.get_int_between`, `.get_float`, `.get_or`, `.get_str_bounded`, `.get_one_of` | no |
| `formfield.get_bool`, `.checkbox` | no |
| `formfield.get_list`, `.get_list_required`, `.get_int_list` | no |
| `formfield.expect_str`, `.expect_int`, `.expect_int_between`, `.expect_bool`, `.optional` | no |
| `formfield.check`, `.is_valid`, `.unexpected_keys`, `.bracket_names`, `.bracket_base` | no |
| `formerr.error_field`, `.is_limit`, `.status_for`, `.error_at`, `.messages`, `.any_limit` | no |
| `formerr.FormError.message` | no |

## Licence

Apache-2.0. See `LICENSE`.

<!-- docs/writing-a-readme.md is the style guide for this page. -->
