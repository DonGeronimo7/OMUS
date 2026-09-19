# OpenSSF Best Practices evidence map

This document maps repository evidence to the OpenSSF Best Practices criteria.
It is an audit aid, not a badge claim. The project owner must create and maintain
the external Best Practices project and answer every criterion accurately.

| Area | Repository evidence |
| --- | --- |
| Project identity, source, and license | `README.md`, the public GitHub repository, `LICENSE`, and package metadata in `pyproject.toml` |
| Contribution and change control | `CONTRIBUTING.md`, `docs/DEVELOPMENT_POLICY.md`, pull requests, and required CI checks |
| Bug and feature reporting | Structured forms in `.github/ISSUE_TEMPLATE/` and the public issue tracker |
| Private vulnerability reporting | `SECURITY.md` links directly to GitHub private vulnerability reporting and defines response and disclosure expectations |
| Build and installation | `README.md`, `pyproject.toml`, `packaging/`, and the release workflow |
| Automated tests | `tests/`, the CI workflow, and the mandatory feature/regression-test policy |
| Static analysis | Ruff and CodeQL workflows |
| Dynamic analysis | Bounded ClusterFuzzLite targets for the HID descriptor and offline vendor-capture parsers |
| Dependency management | Reviewed `requirements/*.in`, hash-checked locks, Dependabot, and the scheduled audit workflow |
| Release integrity | Signed tags, exact checksums, SBOMs, SLSA provenance, and `docs/SECURITY_SUPPLY_CHAIN.md` |
| Versioning and release notes | `CHANGELOG.md`, GitHub Releases, and version checks in the release workflow |
| Cryptography | Mouse Control does not implement a custom cryptographic protocol; transport and artifact verification use maintained TLS, GitHub/Sigstore, and package-manager implementations |

## Owner-maintained external evidence

The following cannot be truthfully established by a repository commit alone:

- Create the project at <https://www.bestpractices.dev/> and complete the
  criteria questionnaire from actual project evidence. Add a badge only after
  the service awards one.
- Verify that private vulnerability reporting is enabled in GitHub repository
  settings, not merely documented.
- Protect `main` against force pushes and deletion. Require status checks that
  are stable for this repository. Do not impose a reviewer rule that prevents a
  sole maintainer from merging necessary work.
- Record any organizational security requirements, such as maintainer 2FA, only
  after the owner has verified them.
- Measure statement coverage before claiming the higher-level 80% coverage
  criterion. The current test suite is extensive, but test count is not coverage
  evidence.

## Packaging criterion

GitHub Releases publish native installers, Python distributions, checksums,
SBOMs, and attestations. The public PyPI API did not show a `mouse-control`
project during this hardening pass, so no PyPI publication claim is made and no
unverified publishing workflow was added. Before publishing to PyPI, the owner
must claim or create the project, configure a PyPI Trusted Publisher for this
repository and its release workflow, decide the protected environment policy,
and review the exact wheel and source archive that will be published.
