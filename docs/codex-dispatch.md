# Codex dispatch executor

This workflow is **manual-only** until the first end-to-end run is reviewed. Go to Actions > Codex dispatch executor > Run workflow and supply the open orchestrator dispatch issue number (currently #8).

Required orchestrator repository secrets:
- `OPENAI_API_KEY`: OpenAI API credential for Codex. API usage may incur charges.
- `PRODUCT_REPOS_WRITE_TOKEN`: fine-grained GitHub token with **Contents: read/write** and **Pull requests: read/write** for the three product repositories only. Never grant administration or Actions permissions. Store it only as an Actions secret.

The runner validates the dispatch issue, checks out the product repository, invokes `openai/codex-action@v1` with workspace-only permissions, then creates a product PR from an isolated branch. No product PR is merged. Existing branches or PRs prevent duplicate runs. Sensitive paths are blocked before publishing.

**Limitations:** No automatic retries, continuous scheduling, multi-agent concurrency, or reliable cross-repository test enforcement yet. The agent is instructed to run relevant tests, but the workflow does not independently enforce every repository's test suite. Review all generated changes and CI before merging. Repository-specific branch protection and conventions must be verified. Never put credentials in dispatch issue bodies.
