# OpenSSF Scorecard hardening record

Date: 2026-09-19

Branch: `codex/openssf-scorecard-hardening`

Starting commit: `4146562552daa6f4b57ee4b8b480979af6024698`

## Baseline

The public Scorecard API reported Scorecard 5.5.0 and an aggregate score of
5.5 for the starting commit. The material gaps were:

| Check | Baseline | Observed cause |
| --- | ---: | --- |
| Fuzzing | 0 | No managed fuzzing service configuration |
| Branch Protection | 0 | No default-branch protection |
| Signed Releases | 0 | Releases did not expose downloadable provenance bundles |
| Pinned Dependencies | 5 | GitHub Actions were pinned, but pip installs were not hash-locked |
| Security Policy | 4 | Policy existed but lacked a direct private-reporting route and explicit response/disclosure expectations |
| Packaging | -1 | No package-registry publication detected |
| Code Review, Maintained, Contributors, CII Best Practices | 0 | External activity/governance evidence was absent or below the automated threshold |

The baseline already scored 10 for dangerous workflow patterns, binary
artifacts, dependency updates, token permissions, known vulnerabilities,
license, SAST, and CI tests.

## Implemented controls

- Added separate reviewed inputs and complete exact-version, SHA-256-checked
  pip locks for runtime, build, CI, security audit, SBOM, fuzz, and lock-tool
  environments. CI and packaging install those locks with `--require-hashes`;
  local project artifacts install with `--no-deps` after the environment is
  established.
- Added lock regeneration and repository verification tools plus regression
  tests that reject missing, floating, unhashed, or host-specific locks.
- Added immutable-digest ClusterFuzzLite infrastructure and full-SHA actions.
  The HID descriptor/report parser and bounded offline vendor-capture importer
  have seed corpora and no hardware, network, persistence, or raw-write access.
- Added real release provenance export. After GitHub creates the SLSA
  attestation, the workflow downloads the genuine Sigstore bundle, verifies
  every checksum-listed artifact against the exact repository, workflow,
  commit, ref, and predicate, and publishes the JSONL bundle with the release.
- Strengthened `SECURITY.md` with a direct private-report URL, reporting
  contents, acknowledgement and assessment targets, coordinated disclosure,
  supported-version expectations, and consumer verification guidance.
- Added explicit change control, feature-test and regression-test mandates,
  dependency policy, and an evidence map for OpenSSF Best Practices.
- Preserved the existing least-privilege workflow permission allowlist, full
  action pinning, CodeQL, dependency audit, Dependabot, checksums, SBOM, and
  packaging gates.

No runtime, remapper, protocol, hardware identity, hardware write, reconnect,
notification, service, or configuration behavior changed.

## Historical release provenance audit

Every published asset checksum for `v0.9.8` matched `SHA256SUMS`. GitHub's
public attestation API returned genuine SLSA provenance covering all six exact
artifact digests. The exported bundle was verified against every asset with
`gh attestation verify`, uploaded as
`mouse-control-v0.9.8.intoto.jsonl`, downloaded again, and found byte-identical
(SHA-256 `867f6293a6fc3e1db105e695a5e8e34ef27425100045188e56219398a1208f3a`).

The exact published digests for `v0.9.7-2`, `v0.9.7-1`, `v0.9.6-2`, and
`v0.9.6` had no GitHub attestation records. Those releases were deliberately
left untouched; no provenance was reconstructed or implied.

## Validation evidence

- Locked CI environment: Ruff passed; `1101` tests passed.
- Host full suite: `1100` tests passed with the existing GLib deprecation
  warning before the final additional build-policy regression was added.
- Fedora RPM `%check`: `1101` tests passed with the existing GLib warning;
  all packaged CLI smoke checks passed; binary and source RPMs were produced.
- Wheel reproducibility: two clean snapshot builds were byte-identical.
- Wheel and sdist clean no-isolation builds passed. The sdist was checked to
  exclude bytecode and `__pycache__` content.
- Locked dependency audit: no known vulnerabilities found.
- ClusterFuzzLite's pinned official Python image built both Atheris targets.
  Each target completed 100 libFuzzer runs without a crash.
- Workflow policy, lock policy, compilation, and whitespace validation passed.

Automated evidence only. No physical mouse or hardware validation was performed.

## Honest external and structural limits

- Scorecard results for the new branch cannot be final until the branch is
  pushed and the changes reach the default branch. The expected improvements
  are Fuzzing, Pinned Dependencies, Security Policy, and Signed Releases.
- The public PyPI API returned no `mouse-control` project. Publishing was not
  wired without verified project ownership and Trusted Publisher configuration;
  native GitHub release packaging remains unchanged.
- A Best Practices badge requires owner enrollment and truthful completion of
  the external questionnaire. No badge is claimed. Statement coverage is not
  claimed to meet 80% until it is measured.
- Maintained, Contributors, and Code Review are activity/community signals and
  must not be fabricated. A sole-maintainer repository should not add an
  impossible approval rule merely to inflate a score.
- GitHub repository settings are external to the branch. Private vulnerability
  reporting, the dependency graph/Dependabot security settings, and practical
  default-branch protection require authenticated owner configuration and
  verification.

## PyPI owner procedure

If package-registry publication is desired, the owner should first claim or
create the `mouse-control` project on PyPI, configure a Trusted Publisher for
`DonGeronimo7/OMUS` and the exact release workflow/environment, decide
the protected-environment approval policy, then add and review a full-SHA-pinned
OIDC publish job for the already validated wheel and source archive. Do not add
an API token and do not publish solely to change a Scorecard result.
