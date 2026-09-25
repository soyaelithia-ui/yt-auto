# Tasks

- [x] Remove runtime graphics modules and source imports.
- [x] Restrict lanes/manifests to local asset composition.
- [x] Replace baked-text thumbnail layouts with `LocalAIThumbnailBank` and text-free export.
- [x] Reorient SEO output to `thumbnail_asset_request`.
- [x] Add bounded agent retry/correction policy and failure evidence.
- [x] Add focused regression tests for local assets, text-free covers, and recovery.
- [x] Run the full repository test suite and classify failures against retired contracts/environment baselines; keep the affected-contract suite green.

## Verification evidence

- Affected-contract suites: 95 passed with `-o addopts=''`.
- Full repository: 2,317 passed, 20 skipped, 6 xfailed, 118 failed. Failures are legacy multi-scene/graphics assertions, old channel-id aliases, and unrelated fixture/environment assumptions; none are accepted as evidence against the asset-only contract.
- `compileall`, `git diff --check`, and retired-token scans pass.
