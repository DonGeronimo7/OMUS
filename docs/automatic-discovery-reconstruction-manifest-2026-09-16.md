# Automatic Discovery reconstruction manifest — 2026-09-16

These guarded installers reconstruct the post-`5369106` experimental chronology used during the G305 Automatic Discovery work. Exact copies plus the full handoff are preserved in the user's ChatGPT Library as `mouse-control-discovery-final-handoff-2026-09-16.zip`.

SHA-256:

- `f4101dd18e6f810d2fe794a8bad53061e3a543ad6078a7fafe01005ae3a7cab0`  `01-install-write-trace.py` (13739 bytes)
- `534a23aba9450f501b8acd4a651f75a0adad715b7bc9b4870aebf58574049ef2`  `02-install-write-discovery-pipeline.py` (96501 bytes)
- `405ac60268a90178280784b341838dbfa2c3e7dd8e2415f2767c73d5d64d7864`  `03-fix-discovery-adapter-dpi-contract.py` (1331 bytes)
- `ae6c6e0cd327845afd9edf7cece07a827273186faf1d7f2a0a58a398b8d3b9cb`  `04-update-promotion-persistent-session-test.py` (15026 bytes)
- `1ee4f19fec4c9ed033e039ec4f1988e67e76fba05ae6ef91019fec3a734562fb`  `05-install-proven-learned-runtime.py` (10595 bytes)
- `4a0b10c86af555871bb5f9f11ce2031189909a552417c6ca7f292905d645eed7`  `06-install-next-capability-tests.py` (29985 bytes)
- `1a050042d079c571bab64c49d350b3a6e2a86db51458f7b5a1169b827aeba008`  `07-install-polling-verifier-stability.py` (30164 bytes)
- `00c52118aeda3a01419a61c38fe2ad4cd081edf49fbef39b0eb678ce332b7e67`  `08-fix-setup-hardware-apply-gating.py` (4376 bytes)
- `95371572b817a05a91bc4bd34c20c05ffa3d6411848bd28128b852baaf5b0dd2`  `09-install-generic-polling-replay-lab.py` (39755 bytes)
- `0b4143fba785748c130f919c6e64941565bdec15b92a205e122e11fd68f3ce6b`  `10-install-polling-host-state-lab.py` (16380 bytes)
- `6027e77b5ff454f8f44b9aacb849c52c4443587acb4ae28db720b22b8c09b046`  `11-install-polling-chained-state-machine-lab.py` (24494 bytes)

Important: these installers preserve the experimental lineage, but the user's current local `~/Mouse-control` working tree is the authoritative source tree for the next session. Begin by checking `git status --short` and running the full pytest suite before any production integration.