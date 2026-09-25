# A10 - Ship: green checks, merge to main, delete the branch

## Goal

Land `fix/answer-loss-repair` on `main` with every GitHub check green.
Remove the branch locally and on `origin`, confirm that the post-merge
`PR fast` and `Main` runs on `main` are green, and rebuild the local
images from `main`. This packet writes no code. It runs `git`, `gh`, and
the 00-rules Docker commands.

## Depends on

- A9 committed and pushed. Its evidence doc
  `docs/evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md` is on the branch
  and its verdict line reads `**Pass.**`.
- The user has explicitly said "ship" after reading the A9 acceptance
  table. Without that word from the user, do not start.
- If the verdict is `**Fail.**`, stop, even if the user said "ship",
  unless the user's message names the failed acceptance rows and says to
  ship anyway. Record that message verbatim under **Deviations** in the
  report.
- `main` has no branch protection (verified 2026-09-22), so nothing on
  GitHub blocks a red merge. This packet is the gate.

## Read first

- `00-rules-and-commands.md`, sections **Git workflow** (including "Once,
  at the start of A0" for the stacked case) and **Docker rebuild before
  any live run**.
- `.github/workflows/pr-fast.yml`: workflow `PR fast`, triggered by
  `pull_request` and by `push` to `main`. Jobs: `preflight`,
  `format-lint`, `types`, `unit`, `contract`, `docs-frontend`,
  `openapi-migrations`. None has an `if:` condition.
- `.github/workflows/main.yml`: workflow `Main`, triggered by `push` to
  `main` (and manual dispatch). Jobs: `unit`, `contract`, `compose`.

## Facts verified for this packet (2026-09-24, read-only)

- Merges into `main` use a merge commit with GitHub's default subject
  `Merge pull request #<n> from Nagdy8888/<branch>` (PRs #10 to #16).
  So this packet does not pass `--subject`.
- No other workflow runs on a push to `main`. `Staging deploy`, `Staging
  migrate`, and `Production migrate` are manual (`workflow_dispatch`), and
  `Nightly` is on a schedule. Do not trigger any of them.
- The `api`, `worker`, and `frontend` images build from
  `apps/backend/Dockerfile`, `apps/worker/Dockerfile`, and
  `apps/frontend/Dockerfile` (context `.`) in `docker-compose.yml`. On
  2026-09-24 the `worker` container was not running.
- PR #17 (`fix/ka50-accuracy-repair`) was `OPEN` on 2026-09-24. If A0
  stacked this branch on it, this PR's base is `fix/ka50-accuracy-repair`
  until PR #17 is merged.

## Step 1 - Local branch equals GitHub, and A9 is in

```powershell
git checkout fix/answer-loss-repair
git status --short
git fetch origin
git status -sb
git log --oneline -3
Select-String -Path docs/evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md -Pattern '^\*\*(Pass|Fail)\.\*\*'
```

Required:

- `git status --short` lists nothing (A0 committed both plans).
- `git status -sb` says neither `ahead` nor `behind`. If `ahead`, run
  `git push`. If `behind`, run `git pull --ff-only`.
- `git log` shows the A9 commit, whose subject starts with
  `docs(eval): answer-loss repair evidence -` and ends with `(A9)`.
- `Select-String` prints the verdict line. Apply the **Depends on** rule
  to it.

## Step 2 - Find the PR and fix its base

```powershell
gh pr view fix/answer-loss-repair --json number,url,state,isDraft,baseRefName,headRefName
```

Set `$pr` to the `number` value (`$pr = <number>`). `state` must be `OPEN`
and `headRefName` must be `fix/answer-loss-repair`. Then act on
`baseRefName`:

- `main`: go to Step 3.
- `fix/ka50-accuracy-repair` (the stacked case): check PR #17.

  ```powershell
  gh pr view 17 --json state,mergedAt,baseRefName
  ```

  - If PR #17's `state` is not `MERGED`, stop and ask the user to ship
    PR #17 first (the KA50 plan's P8 packet does that). This packet never
    merges into `fix/ka50-accuracy-repair` and never merges PR #17.
  - If PR #17 is `MERGED` into `main`, retarget this PR and confirm:

    ```powershell
    gh pr edit $pr --base main
    gh pr view $pr --json number,baseRefName
    ```

    `baseRefName` must now be `main`. (GitHub can retarget it on its own
    when PR #17's branch is deleted; then the first view already shows
    `main` and you skip `gh pr edit`.)
- Any other base: stop and report.

## Step 3 - Bring the branch up to date with main

The checks must run on the exact tree that will be merged. Merging
`main` must not bring in product code that A9 did not measure.

```powershell
$before = git rev-parse HEAD
git fetch origin main
git merge --no-edit origin/main
git diff --stat $before HEAD -- packages apps scripts
```

- `Already up to date.`: continue to Step 4.
- A clean merge with an empty `git diff --stat`: run `git push`, then
  continue. This is the normal stacked case, because PR #17's commits were
  already in this branch.
- A clean merge whose `git diff --stat` lists files: `main` changed product
  code after A9 measured this branch. Push nothing. Run
  `git reset --hard $before`, then stop and ask the user whether to rerun
  A9 on the merged tree or ship anyway.
- Conflicts: list them with `git diff --name-only --diff-filter=U`, run
  `git merge --abort`, then stop and report the list. Do not resolve
  conflicts in this packet.

## Step 4 - Out of draft, wait for green

```powershell
gh pr ready $pr
gh pr checks $pr --watch --fail-fast
```

If `gh pr ready` says the PR is already ready for review, continue. Exit 0
from `gh pr checks` means all seven `PR fast` jobs passed on the current
head. On a non-zero exit, `gh pr checks $pr` lists the failing job and
`gh run view <run-id> --log-failed` shows why.

- A failure from a test that passed on the A9 head and involves no file
  this merge changed is likely flaky (for example a network timeout). Run
  `gh run rerun <run-id> --failed` once, then repeat this step.
- A failure caused by the docs or the merge (for example a markdown lint
  rule or a link): fix it on this branch, commit it as `fix(ci): <what>`
  (add the paths one by one), `git push`, and repeat this step.
- Anything else, or a second failure of the same job: stop and report. Do
  not proceed on red.

## Step 5 - Confirm mergeability from GitHub's side

```powershell
git rev-parse HEAD
gh pr view $pr --json number,state,isDraft,baseRefName,headRefOid,mergeable,mergeStateStatus,statusCheckRollup
```

All of these are required:

- `"state": "OPEN"`, `"isDraft": false`, `"baseRefName": "main"`
- `"headRefOid"` equals the `git rev-parse HEAD` output
- `"mergeable": "MERGEABLE"` and `"mergeStateStatus": "CLEAN"`
- Every `statusCheckRollup` entry has `"conclusion": "SUCCESS"` (a status
  context shows `"state": "SUCCESS"` instead). No `PR fast` job is
  conditional, so `SKIPPED` is not acceptable.

If any is missing, stop and report. `UNKNOWN` mergeability can mean
GitHub is still computing: wait one minute and run the view again, at
most three times.

## Step 6 - Merge and delete the branch

```powershell
gh pr merge $pr --merge --delete-branch
```

This creates a merge commit with the default subject
`Merge pull request #<n> from Nagdy8888/fix/answer-loss-repair`, switches
you to `main`, deletes the local branch, and deletes
`origin/fix/answer-loss-repair`.

## Step 7 - Sync main and confirm the branch is gone

```powershell
git checkout main
git pull --ff-only origin main
git log -1 --format="%H %s" origin/main
git branch --list fix/answer-loss-repair
git ls-remote --heads origin fix/answer-loss-repair
```

- The `git log` subject is the merge subject above, with this PR's number.
- Both list commands print nothing. If the local branch is still listed,
  run `git branch -d fix/answer-loss-repair` (lowercase `-d`: it deletes
  only a merged branch). If the remote branch is still listed, run
  `git push origin --delete fix/answer-loss-repair`. Delete no other
  branch.

## Step 8 - Watch the post-merge runs on main

```powershell
$sha = git rev-parse origin/main
gh run list --branch main --commit $sha --json databaseId,workflowName,status,conclusion
```

You need two rows: `workflowName` `PR fast` and `workflowName` `Main`. If
fewer appear, wait one minute and run the list again (at most five
times). Then watch each by its `databaseId`:

```powershell
gh run watch <PR fast databaseId> --exit-status
gh run watch <Main databaseId> --exit-status
```

Both must exit 0. If one fails:

1. `gh run view <databaseId> --log-failed` and note the failing job and
   step.
2. If the same job passed on the PR head and the log shows a transient
   cause (network, registry, runner), run
   `gh run rerun <databaseId> --failed` once and watch it again.
3. Otherwise, or if it fails again: stop and report to the user. A fix
   goes on a new short branch `fix/answer-loss-post-merge-<what>` cut
   from `main`, through its own PR, and only after the user agrees.
   Never push to `main` directly.

## Step 9 - Rebuild the local images from main

Run the 00-rules **Docker rebuild before any live run** commands
unchanged, on `main`:

```powershell
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --build --wait api
Invoke-RestMethod http://127.0.0.1:8000/health/ready | ConvertTo-Json -Compress
```

`health/ready` must contain `"query_ready": true`. Then run the 00-rules
probe one-liner unchanged. All seven lines (A1 to A7) must print
`present`.

Rebuild `worker` and `frontend` only if they are running, so no running
container keeps pre-merge code:

```powershell
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml ps --services --status running
```

- If the list contains `worker`:
  `docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --build --wait worker`
- If the list contains `frontend`:
  `docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --build --wait frontend`
- Do not start a service that was not running.

Finally, confirm the book version was not touched (read-only):

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe .private-eval/a9_metrics.py version
```

It must end with `version_check=pass`, with the same `book_version_id`
as the A9 report.

## Step 10 - Report

Paste the 00-rules **Reporting template** with `Packet: A10` and
`Files changed: none` (or the `fix(ci)` paths, if Step 4 needed one). Add:

```text
PR: #<n> <url> (base main; stacked on #17: yes|no; retargeted: yes|no)
Merge commit: <sha> "Merge pull request #<n> from Nagdy8888/fix/answer-loss-repair"
PR checks on merged head: 7/7 SUCCESS, mergeStateStatus CLEAN
Branch deleted: local yes, origin yes
Post-merge on main: PR fast <databaseId> <conclusion>; Main <databaseId> <conclusion>
Local images: api rebuilt (probe A1..A7 present, query_ready true); worker <rebuilt|not running>; frontend <rebuilt|not running>
Book version: version_check=pass <book_version_id>
```

## Done when

- [ ] The A9 verdict was `**Pass.**` (or the user named the failed rows
      and said to ship anyway, recorded verbatim), and the user said
      "ship".
- [ ] In the stacked case, PR #17 was `MERGED` before this PR was
      retargeted to `main`.
- [ ] `gh pr checks $pr --watch --fail-fast` exited 0, and
      `gh pr view` showed `MERGEABLE`, `CLEAN`, and every check
      `SUCCESS` on the head that was merged.
- [ ] The PR was merged with `gh pr merge $pr --merge --delete-branch`,
      and `origin/main` ends in the default merge subject for this PR.
- [ ] `fix/answer-loss-repair` no longer exists locally or on `origin`.
- [ ] The post-merge `PR fast` and `Main` runs on the merge commit both
      concluded `success`.
- [ ] The local `api` image was rebuilt from `main` with the 00-rules
      command, `query_ready` is true, and the probe printed `present` for
      A1 to A7. Running `worker` and `frontend` containers were rebuilt
      too.
- [ ] `a9_metrics.py version` printed `version_check=pass`.
- [ ] The report lists the PR number and URL, the merge commit sha, and
      both `main` run ids with conclusions.

## Do not

- Do not start without the user's explicit "ship".
- Do not use `gh pr merge --admin`, `--squash`, `--rebase`, or `--subject`.
- Do not `git push --force` anywhere, and never push to `main` directly.
- Do not merge on red, on a draft, or on a `mergeStateStatus` other than
  `CLEAN` (`UNSTABLE`, `BLOCKED`, `DIRTY`, `BEHIND`, `UNKNOWN` mean stop
  and report).
- Do not merge or retarget onto `fix/ka50-accuracy-repair`, and do not
  merge PR #17 from this packet.
- Do not delete any branch other than `fix/answer-loss-repair`.
- Do not resolve merge conflicts or bring untested `main` product changes
  into the branch in this packet; stop and ask instead.
- Do not edit code. The only exception is a `fix(ci): ...` commit on the
  PR branch before the merge, for a failure caused by the docs or the
  merge itself.
- Do not trigger `Staging deploy`, `Staging migrate`, `Production
  migrate`, or `Nightly`, and do not run live evals or re-ingest anything.
