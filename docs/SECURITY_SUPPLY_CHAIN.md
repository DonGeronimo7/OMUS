# Release supply-chain security

Mouse Control release workflows keep the default token read-only. The release
publication job alone receives narrowly scoped permission to publish the GitHub
Release and create keyless GitHub artifact attestations. Release triggering
separates validation, tag creation, and workflow dispatch so write permissions
are not shared across those operations.

## Release integrity chain

The release workflow enforces this sequence:

```text
signed source tag
→ full test and package builds
→ exact final wheel, sdist, RPM, DEB, and AppImage allowlist
→ CycloneDX project dependency SBOM
→ SHA-256 checksums over the final files
→ SLSA build provenance and SBOM attestations for those exact digests
→ GitHub Release publication
```

`SHA256SUMS` remains part of every release. The workflow fails if a required
artifact is absent, an unexpected file appears, or checksum verification fails.
GitHub's keyless attestation service binds provenance to the final downloaded
artifact bytes, not to intermediate build outputs.

The release also publishes `mouse-control-VERSION.intoto.jsonl`, an offline copy
of the genuine GitHub/Sigstore SLSA provenance bundle. The workflow downloads
that bundle from GitHub's attestation service and verifies every exact checksum
entry against the expected repository, workflow, source commit, source ref, and
SLSA predicate before release publication. It never synthesizes provenance.

The published `mouse-control-VERSION.cdx.json` is a reproducible CycloneDX 1.6
inventory of the installed Mouse Control wheel and its resolved Python runtime
dependencies. The same SBOM is bound to the wheel, sdist, RPM, DEB, and AppImage
digests through an SBOM attestation.

This is deliberately labeled a project dependency SBOM. It is not a claim to
inventory every Fedora, Debian, Python-runtime, or AppImage filesystem component.
An artifact-filesystem SBOM for the AppImage is deferred until a maintained,
integrity-pinned scanner can be introduced without weakening the release chain.

## Consumer verification

After downloading a release, verify checksums from the release directory:

```bash
sha256sum --check --strict SHA256SUMS
```

Verify a downloaded artifact's GitHub attestation against this repository:

```bash
gh attestation verify Mouse-Control-VERSION-x86_64.AppImage \
  --repo DonGeronimo7/mouse-control
```

The same command applies to the wheel, source archive, RPM, DEB, and SBOM.
Checksums and attestations complement one another: checksums detect byte changes,
while attestations bind those bytes to the repository workflow identity.

For offline verification, download the matching
`mouse-control-VERSION.intoto.jsonl` release asset and pass it explicitly:

```bash
gh attestation verify Mouse-Control-VERSION-x86_64.AppImage \
  --repo DonGeronimo7/mouse-control \
  --bundle mouse-control-VERSION.intoto.jsonl
```

## Locked dependency environments

Runtime, CI, security audit, build, SBOM, fuzzing, and lock-tool environments
have separate reviewed inputs and exact, SHA-256-checked lock files under
`requirements/`. Workflows install them with `--require-hashes`; local project
installs use `--no-deps` after the applicable locked environment is present.
See [`DEVELOPMENT_POLICY.md`](DEVELOPMENT_POLICY.md) for the auditable
regeneration procedure.

## Reproducibility scope

CI builds the wheel twice from clean `git archive` snapshots under the same
`SOURCE_DATE_EPOCH`, UTC timezone, and stable locale, then requires byte-identical
outputs. A bounded local trial confirmed the wheel is reproducible under those
conditions.

The sdist is not yet reproducible. Its file contents and ordering match, but
setuptools records build-time subsecond mtimes on generated directories,
`PKG-INFO`, and `setup.cfg`. Normalizing that archive would require a packaging
change beyond this hardening pass. RPM, DEB, and AppImage reproducibility remain
separate future work; all continue to receive checksums and attestations over
their exact published bytes.
