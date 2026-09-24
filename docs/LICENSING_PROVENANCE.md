# Licensing and provenance map

This record describes the repository at the licensing transition whose parent
is commit `2bf8760e2ca6050513621b6462583eb509b22bb9`. That parent is the final
pre-AGPL engineering baseline. The single transition commit immediately after
that parent begins the current `AGPL-3.0-or-later` development state. Earlier
releases and commits remain governed by the licenses applicable when they were
distributed.

This is a repository audit record, not legal advice or a forensic guarantee.
Unknown provenance is recorded as unknown rather than inferred.

## Rights and contributors

Git history through the transition parent contains one identified human
contributor/rightsholder represented by the author identities Marc-Anthony
Geronimo and DonGeronimo7 (including the repository's GitHub noreply and local
email variants). The package metadata names Marc-A. Geronimo. No evidence of a
different human code contributor or copyright assignment was found.

Dependabot commits change dependency inputs, generated lock files, and pinned
workflow revisions. Several historical commits use the `github-actions[bot]`
author identity for repository automation that produced OMUS implementation
changes; that bot identity is not treated as a separate natural-person rights
holder. One commit records Marc-Anthony Geronimo as co-author. The maintainer
should preserve the underlying automation records and review any newly
identified human contribution before commercial relicensing.

The repository has no CLA, copyright-assignment agreement, or DCO policy that
grants the project additional relicensing rights. `CONTRIBUTING.md` therefore
gates future outside code contributions intended for separately commercially
licensed builds pending a legally reviewed agreement.

## Classification

| Category | Exact repository scope | Licensing/provenance treatment |
| --- | --- | --- |
| First-party OMUS code | `src/mouse_control/**/*.py`, `scripts/*.py`, `scripts/*.sh`, `fuzz/*.py`, `benchmarks/*.py`, and first-party tests under `tests/*.py` | Current versions are `AGPL-3.0-or-later`. Python files carry SPDX identifiers. Protocol implementation code remains subject to the source cautions in `CREDITS.md`. |
| First-party project and packaging material | Root Markdown/configuration files, `.github/`, `.clusterfuzzlite/`, `packaging/`, `debian/`, `omus.spec`, `PKGBUILD`, and `.SRCINFO`, except the exclusions below | Covered by the current project license where copyright applies. Format-specific license fields identify `AGPL-3.0-or-later`. AppStream metadata separately declares `CC0-1.0` for that metadata document and declares the project license as AGPL. |
| Generated first-party output | `requirements/*.lock.txt`, `.SRCINFO`, generated icon sizes, build metadata, SBOMs, checksums, and provenance emitted by repository tooling | Retains generator/input provenance. Generated files are not used to claim new ownership in third-party dependency data. Build outputs are not committed. |
| External factual/research material | Protocol facts cited in `CREDITS.md`, including OpenRazer, libratbag, rivalcfg, OpenSharkX11, OpenMouse, AJAZZ, LAMZU, Solaar, Linux/HID standards, and hardware observations | Facts and observations remain attributed. Citation does not convert upstream expression into first-party code or grant write authority. No blanket OMUS SPDX header is applied to external evidence records. |
| Generated upstream evidence corpus | `docs/discovery-corpus/*.evidence.json` | Machine-readable facts extracted from pinned Linux v6.12 source commit `adc218676eef25575469234709c2d87185ca223a`, with per-source hashes and line URLs. Excluded from blanket AGPL headers; Linux source provenance remains intact. |
| Fixtures and captures | `fuzz/corpus/**`, `tests/fixtures/**`, plus any future imported vendor/community captures | Current committed examples are synthetic or repository test fixtures as documented in place. External captures must preserve source/provenance fields and are not automatically relicensed. |
| Assets | `assets/**/*.png` | OMUS application artwork is present in Git history, but the checkout contains no separate author/source instrument beyond repository history. Excluded from blanket SPDX conversion and recorded for administrative provenance follow-up. |
| Third-party dependencies | Packages named in `pyproject.toml` and `requirements/**` | Referenced/downloaded dependencies are not vendored source. Their own licenses remain controlling. Lock files and SBOMs must not relabel dependency licenses. |
| Third-party binaries or firmware | None found in the tracked tree | Firmware inspection code and metadata do not bundle firmware. Any future binary requires an explicit redistribution and license review. |
| Submodules or vendored trees | None found | A future addition requires its own license files, notices, and compatibility review. |

## Protocol Genome and research corpus

The loaders, schemas, compilers, inference engines, evidence structures,
Discovery orchestration, and other OMUS-authored software in
`src/mouse_control` are first-party implementation and use the current project
license. Declarative protocol records and generated Genome structures do not
erase the origin of their underlying facts. Source URLs, revisions, evidence
categories, hashes, and ancestry must remain intact.

The `bitmouse-72` record is identified only as a “source-derived semantic
fixture”; its original source, author, and license are unknown in this checkout.
It remains write-disabled and is excluded from any claim that its underlying
research is first-party. This is an administrative provenance issue and must be
resolved before the record is promoted, expanded, or represented as owned OMUS
data. The current transition does not grant it hardware authority.

No firmware blob, packet-capture archive, vendor bundle, WebHID implementation,
or foreign source file was found in the tracked tree. `CREDITS.md` records the
known public/vendor research sources used as factual inputs and the remaining
expression-level review cautions.

## Exclusions from blanket SPDX conversion

The following intentionally do not receive OMUS AGPL file headers:

- canonical license texts;
- `docs/discovery-corpus/*.evidence.json` and other provenance-bearing evidence;
- `fuzz/corpus/**` and `tests/fixtures/**` data;
- dependency inputs/locks and generated supply-chain documents;
- PNG assets and other binary/generated artwork;
- AppStream metadata, whose metadata license is explicitly `CC0-1.0`;
- historical release notes, changelogs, and status/handoff records where GPL
  references accurately describe an earlier release or state.

No third-party file was intentionally given an OMUS AGPL header during this
transition. `CREDITS.md` is the third-party notice and protocol-source ledger
distributed with release formats.

## Transition maintenance rules

1. Preserve historical license statements when they describe historical
   releases; current project/package metadata must say `AGPL-3.0-or-later`.
2. Do not accept outside code for separately commercially licensed builds until
   an appropriate contributor agreement has received legal review.
3. Do not treat a DCO alone as a grant of commercial relicensing rights.
4. Record the source, revision, license, and required notices before importing
   third-party expression, assets, captures, tables, or binaries.
5. Preserve Protocol Genome and research-evidence attribution through every
   transformation.
6. Run `python3 scripts/check_license_consistency.py` with the release gates.
