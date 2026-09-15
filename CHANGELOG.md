# Changelog

All notable changes to form-nv are recorded here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
package follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the pre-1.0 rule that a breaking change bumps the MINOR number.

## 0.0.2 — 2026-09-15

README rewritten to the package README style guide (docs/writing-a-readme.md); no change to the interface.

## 0.0.1 — 2026-09-11

The **interface**: every signature and every effect row, and no bodies.
`stability = "draft"`, and the release is recorded `implemented = false`.

### Added

- `formscan` — `FormScan` as four integers of `@value` state, decoding
  as part of the walk, and the byte arithmetic a device sizing its own
  buffer uses.
- `formurl` — `FormPair` as spans, `parse` that cannot fail because the
  standard has no error case, `parse_bounded` that can, the ordered
  lookup, and the WHATWG serialiser.
- `formpart` — `FormEvent`, the feed-and-drain reader, `FormLimits`
  with six bounds, `boundary_of` and `boundary_of_type`, and `collect`
  with no unbounded variant.
- `formfield` — `get_int` / `get_bool` / `get_list` and their
  neighbours, `checkbox` as the one call where absence means false, and
  `check` over a list of expectations.
- `formerr` — twenty-one refusals, `error_field`, and `status_for`.

### Known

- **`FormEvent` is the load-bearing interface**, and the argument is a
  security one: a body chunk is a RANGE into the chunk the caller just
  fed, so an upload endpoint's memory is never the client's decision.
  `pending_bytes` is published so a test can assert it.
- **The limits refuse rather than grow**, each at the byte the bound
  was crossed, and `collect` has no variant without them.
- **Every field refusal names the field**, and `check` answers all of
  them; `status_for` publishes the status mapping because two handlers
  making it separately will disagree.
- **A boolean's spellings are the web's**, and `checkbox` is the one
  call where an absent field means false.
- **The device claim is BUILT** and covers `formscan` alone —
  `tests/embedded_probe.nv` links for `--target=nrf52-qemu` and says in
  its own header which half is not claimed.
- **One dependency, mime-nv**, for the boundary out of a parsed
  `Content-Type`; url-nv is absent, and the README's table lists the
  four places the WHATWG parser and urllib's disagree.
- **No effect-polymorphic signature**, unlike this lane's other three:
  this package writes nothing, and the README says so rather than
  leaving the absence to be noticed.
- The scaffold's `src/form.nv` was dropped for five prefixed modules.

### Design notes

No signature in this package is effect-polymorphic, unlike its
siblings, because the package writes nothing: the urlencoded serialiser
answers a string or fills the caller's buffer, and the multipart half
is a reader. A handler streaming a part to a sink passes its own
`Write` implementation to its own function.

The named first consumer is `compiler/stdlib/http_server.nv`, which has
both halves by hand: `http_server_query_get` walks `&`-separated fields
with `str.split` and answers only the first match, so a repeated key
loses every value but one, and `http_server_url_decode` is a 25-line
percent-decoder beside it. `formurl.get_all`, `formurl.decode` and
`formscan.hex_value` replace them. The standard library has no
multipart support at all.

The scaffold's `src/form.nv` was dropped for five prefixed modules.
