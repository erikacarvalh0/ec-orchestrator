# EC cross-repository backlog sync
This read-only integration monitors Issues, PRs and CI for ec-finance, ec-viagens and ec-insurance.

## Setup
Create a fine-grained GitHub token with **read-only** Issues, Pull requests, Checks, Commit statuses and Metadata permissions for all three repositories. Store it in the ec-finance Actions secret `EC_BACKLOG_READ_TOKEN`. Never commit the token.

After this PR is manually merged, run **Sync EC backlogs (read only)** using Actions > Run workflow. Download the `ec-backlog-report` artifact to inspect evidence.

Use `Backlog-ID: ec-finance:area-name` (or corresponding project prefix) in Issue/PR descriptions to link evidence. Unmarked PRs are reported as unlinked, not automatically classified.

**Safety:** this workflow never commits, merges, approves, closes, or changes Issues/PRs. A green CI observation does not prove acceptance criteria or branch protection compliance. It does not automatically prioritize work yet: prioritization requires importing the canonical checklist and classifying legacy PRs. GitHub scheduled workflows run only after this workflow is on the default branch.
