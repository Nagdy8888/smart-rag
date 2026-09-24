# P8 - Ship: green checks, merge to main, delete the branch

## Goal

Land `fix/ka50-accuracy-repair` on `main` with every GitHub check green,
then remove the branch locally and remotely, and confirm the post-merge
`Main` and `PR fast` runs on `main` are green too. This packet writes no
code. It runs only `git` and `gh`.

## Preconditions

- P7 committed and pushed; its evidence doc is on the branch.
- The user has read the P7 acceptance table and said "ship" (or the
  table meets every target). If `strict_pass < 32` and the user has not
  explicitly accepted the shortfall, stop and ask; do not merge.
- `main` has no branch protection (verified 2026-09-22), so nothing on
  GitHub blocks a red merge. This packet is the gate.

## Read first

- `00-rules-and-commands.md`, section **Git workflow**.
- `.github/workflows/pr-fast.yml` (jobs that must be green on the PR).
- `.github/workflows/main.yml` (jobs that run after the merge).

## Steps

1. Make sure the local branch is what is on GitHub:

   ```powershell
   git checkout fix/ka50-accuracy-repair
   git status --short
   git fetch origin
   git status -sb
   ```

   `git status --short` must be empty (ignore untracked `.private-eval/`
   noise). `git status -sb` must not say `ahead` or `behind`. If it says
   `ahead`, `git push`. If it says `behind`, `git pull --ff-only`.

2. Bring the branch up to date with `main` so the checks run on the
   exact tree that will be merged:

   ```powershell
   git fetch origin main
   git merge --no-edit origin/main
   ```

   If this prints `Already up to date.` continue. If it merges cleanly,
   `git push`. If there are conflicts, resolve them file by file (keep
   both sides' intent, re-run the affected unit tests), `git add` the
   resolved files, `git commit --no-edit`, `git push`.

3. Take the PR out of draft and wait for the checks:

   ```powershell
   gh pr ready
   gh pr checks --watch --fail-fast
   ```

   Exit 0 means all `PR fast` jobs (`preflight`, `format-lint`, `types`,
   `unit`, `contract`, `docs-frontend`, `openapi-migrations`) passed on
   the current head. Non-zero: `gh pr checks` lists the failing job;
   `gh run view <run-id> --log-failed` shows why. Fix on this branch,
   commit `fix(ci): <what>`, `git push`, and repeat this step. Do not
   proceed on red.

4. Confirm the PR is mergeable and shows all-green from GitHub's side,
   not only from the watch loop:

   ```powershell
   gh pr view --json number,state,isDraft,mergeable,mergeStateStatus,statusCheckRollup
   ```

   Required: `"isDraft": false`, `"mergeable": "MERGEABLE"`, every entry
   in `statusCheckRollup` has `"conclusion": "SUCCESS"` (or is a skipped
   job that the workflow file marks conditional). Anything else: stop and
   report.

5. Merge with a merge commit (matches PR #16 and the existing `main`
   history) and delete the branch on both sides:

   ```powershell
   gh pr merge --merge --delete-branch --subject "Merge pull request: KA50 accuracy repair (P0-P8)"
   ```

   `gh` switches you to `main`, deletes the local branch, and deletes
   `origin/fix/ka50-accuracy-repair`. If local deletion fails because you
   were still on the branch, run `git checkout main` then
   `git branch -D fix/ka50-accuracy-repair`.

6. Sync local `main` and confirm the branch is gone:

   ```powershell
   git checkout main
   git pull --ff-only origin main
   git branch --list fix/ka50-accuracy-repair
   git ls-remote --heads origin fix/ka50-accuracy-repair
   ```

   Both list commands must print nothing.

7. Wait for the post-merge workflows on `main` (`PR fast` and `Main` both
   trigger on push to `main`):

   ```powershell
   gh run list --branch main --limit 2
   ```

   Take the two run ids from the first column of the two newest rows
   (their commit title is the merge commit) and watch each:

   ```powershell
   gh run watch <run-id-1> --exit-status
   gh run watch <run-id-2> --exit-status
   ```

   Both must exit 0. If `Main` fails (it adds the `compose` job), open
   `gh run view <run-id> --log-failed`, fix on a new short branch
   `fix/ka50-post-merge-<what>`, open a PR, get it green, merge it the
   same way. Never push directly to `main`.

8. Rebuild the local `api` image from `main` so the laptop stack runs
   the merged code, and re-run the probe from `00-rules-and-commands.md`
   (all six lines `present`):

   ```powershell
   docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --build --wait api frontend
   ```

## Done when

- [ ] Branch merged into `main` with all `PR fast` checks `SUCCESS` on
      the merged head.
- [ ] `fix/ka50-accuracy-repair` no longer exists locally or on
      `origin`.
- [ ] Post-merge `PR fast` and `Main` runs on `main` both `success`.
- [ ] Local `api` (and `frontend`) images rebuilt from `main`; probe shows
      P0-P5 `present`.
- [ ] Report lists: PR number and URL, merge commit sha, the two `main`
      run ids with conclusions.

## Do not

- Do not use `gh pr merge --admin`, `--squash`, or `--rebase`.
- Do not `git push --force` anywhere.
- Do not merge on red or on `mergeStateStatus` other than `CLEAN`
  (`UNSTABLE`/`BLOCKED`/`DIRTY` mean stop and report).
- Do not delete any branch other than `fix/ka50-accuracy-repair`.
- Do not edit code in this packet; a CI fix is the only exception and it
  is committed as `fix(ci): ...` on the same PR branch before merging.
