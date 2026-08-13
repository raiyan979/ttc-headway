# Security

This is a public, free-tier data pipeline that runs scheduled GitHub Actions
jobs against a public transit endpoint. That is a real attack surface, so the
controls below are implemented as code, not described as intentions.

## Scope

**In scope**
- The collector (`src/ttc_headway/`) and its handling of untrusted input from
  the feed endpoint and, later, the GTFS zip archive.
- The GitHub Actions workflows and their permissions and pinned dependencies.
- Handling of the R2 credential.

**Out of scope / not vulnerabilities here**
- The vehicle position data itself is public and non-personal (see Privacy).
- Ingestion gaps caused by free-tier scheduler delays. These are an expected,
  measured limitation, not a security issue.
- Denial of service against the public TTC endpoint — we are a polite client
  (identifiable User-Agent, bounded rate); the endpoint's availability is not
  ours to defend.

## Controls

**Supply chain**
- Every GitHub Action is pinned to a full commit SHA, never a mutable tag.
- Every workflow declares an explicit least-privilege `permissions:` block,
  defaulting to `contents: read`.
- `pull_request_target` is never used.
- `uv.lock` is committed; Dependabot watches actions and Python deps; CI runs
  `pip-audit` and `gitleaks`.

**Untrusted input**
- The HTTP response is read under a hard byte cap before the protobuf is parsed,
  bounding a memory-exhaustion vector from a hostile or malfunctioning endpoint.
- Connect and read timeouts are enforced; retries are bounded with backoff.
- A malformed feed response fails one poll and is skipped; it never aborts a
  collection cycle or writes corrupt data. (Covered by a committed test fixture.)
- The GTFS zip extraction — added in the transform phase — validates every
  member path and caps uncompressed size (zip-slip / zip-bomb defence).

**Secrets**
- The R2 credential lives only in GitHub Actions encrypted secrets. It is scoped
  to object read/write on a single bucket, with no delete and no account-level
  permissions, so a leak's blast radius is one bucket of public transit data.
- No bucket name, account ID, or endpoint hostname appears in a tracked file —
  they are supplied through environment variables even though they are not
  themselves secret, because the repo is public.
- Rotation on suspected exposure: **revoke the token first, then** rewrite
  history. Rewriting history alone does not revoke anything.

## Privacy

Vehicle position data is public and not personal. But a single vehicle's trace
across a shift approximates one operator's shift, so:

- Vehicle IDs are used only in the raw and intermediate layers, for the headway
  join. They are never surfaced in the published marts, the dashboard, or any
  finding.
- Published outputs are aggregated to route × direction × timepoint × hour.
- The committed raw sample keeps vehicle IDs because it must reproduce the
  pipeline faithfully; it is raw data from a public source, not a published
  analysis of individual traces.

## Reporting

Open a private security advisory on this repository, or open a regular issue for
non-sensitive reports. There is no bounty; this is a portfolio project.
