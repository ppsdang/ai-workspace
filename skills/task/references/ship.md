# Shipping: push, MR/PR per codebase, ticket update

With `git_host.type: none`, skip to [Local only](#local-only) at the end.

Run only after Gate 2 approval, in this order. If a step fails, stop, report which codebases are done
and which aren't, and record that in `state.md`. Re-running is safe: skip steps that are already done.

## 1. Push

For each affected codebase:

```bash
git -C <repo> push -u origin <branch>
```

The plugin's guard hook blocks force-pushes and protected branches. If it blocks you, something is wrong
with the branch: report it and don't try to work around it.

## 2. Open one MR/PR per codebase

Body template (fill it per codebase, in the language of the team's existing MRs if obvious):

```markdown
## <KEY>: <ticket title>

Ticket: <ticket url>

### What changed
- <bullet per logical change in this codebase>

### Related changes
- <other codebase>: <MR/PR url, filled in by step 3>

### Test evidence
- <command>: <result> (from test-results.md)

### Review
Automated review: <APPROVE, and any non-blocking notes worth a human look>

### Notes for reviewers
- <migrations, feature flags, deploy order: e.g. "merge backend first">
```

Write each body to `tasks/<folder-key>/mr-<name>.md` first, then pass the file; never inline body text
in the command line. `git_host.draft: true` in `workspace.yaml` opens drafts.

`<repo>` is the codebase's task checkout (see `checkouts:` in `state.md`) and `<ws>` the absolute path
of the workspace root. Run host CLI commands in a **subshell** `( cd <repo> && ... )` so the shell's working directory
stays at the workspace root for later `git -C` commands. Expect the guard to ask the user to confirm each
push and MR/PR command; that confirmation is intended.

The host comes from `git_host` in `workspace.yaml`: `type` (github | gitlab | other) and, for anything
other than github.com / gitlab.com, `url` (e.g. `https://gitlab.example.com`); `<host>` below is its
hostname. `gh` and `glab` pick the host up from each repository's `origin` remote, which is why they run
inside `<repo>`.

### github (`gh`): github.com and GitHub Enterprise Server

For GitHub Enterprise, `gh` must be logged in to that host: `gh auth login --hostname <host>`.

```bash
( cd <repo> && gh pr create --base <base> --head <branch> --title "<KEY>: <title>" \
    --body-file <ws>/tasks/<folder-key>/mr-<name>.md [--draft] )
```

`gh pr create` prints the PR URL. If a PR for the branch already exists, get it with
`( cd <repo> && gh pr view <branch> --json url -q .url )`.

### gitlab: gitlab.com and self-hosted GitLab

**With `glab`** (preferred: full description, cross-linking, CI status):

```bash
( cd <repo> && glab mr create --source-branch <branch> --target-branch <base> \
    --title "<KEY>: <title>" --description "$(cat <ws>/tasks/<folder-key>/mr-<name>.md)" --yes [--draft] )
```

For self-hosted GitLab, `glab` must be logged in to that host (`glab auth login --hostname <host>`). If an
MR already exists: `( cd <repo> && glab mr view <branch> -F json )`.

**Without `glab`**: GitLab can open the MR during the push itself, using push options (no CLI or
token needed). Do this *instead of* the plain push in step 1:

```bash
git -C <repo> push -u origin <branch> \
  -o merge_request.create -o merge_request.target=<base> \
  -o merge_request.title="<KEY>: <title>" [-o merge_request.draft]
```

GitLab prints the MR URL in the push output; record it. Push options can't carry a multi-line
description, so tell the user the prepared description is in `tasks/<folder-key>/mr-<name>.md` to paste
into the MR (or suggest installing `glab`, which does it automatically). `/ai-workspace:ci` and
`/ai-workspace:respond` need `glab` on GitLab.

### other hosts (Bitbucket, Gitea/Forgejo, Azure DevOps, …)

Push as in step 1. Most hosts print a "create pull request" link in the push output; otherwise build it
from `git_host.url`. Give the user that link together with the prepared title and the description file,
and record the link in `state.md`. MR creation, cross-linking, `/ci` and `/respond` are manual on these
hosts.

## 3. Cross-link

When more than one codebase is affected, update each MR/PR body's "Related changes" with the others' URLs:

Update `tasks/<folder-key>/mr-<name>.md`, then:

- github: `gh pr edit <url> --body-file <ws>/tasks/<folder-key>/mr-<name>.md`
- gitlab: `( cd <repo> && glab mr update <iid> --description "$(cat <ws>/tasks/<folder-key>/mr-<name>.md)" )`
- without a host CLI: list the related MR/PR links in the ticket comment instead (step 4).

## 4. Update the ticket

Skip for `tracker.type: none` or if the user chose "Push and open MRs only".

Comment (via the tracker adapter, see trackers.md):

```text
Implementation ready for review.

MRs/PRs:
- <codebase>: <url>

Tests: <one line per codebase>
Automated review: APPROVE
```

Then transition to `tracker.statuses.review`. If the transition fails, still report success for the MRs
and show the transition error with the available statuses.

## 5. Finish

Set `state.md` phase to `shipped` and list the MR URLs in it. Show the final table:
codebase · branch · MR/PR · tests · review.

## Local only

`git_host.type: none`: nothing leaves the machine. Per codebase, depending on the Gate 2 answer:

- **Keep the branch**: nothing to do; report the branch name and the commits.
- **Merge into my local `<base>`**: fast-forward only, in the main checkout `<clone>`:
  1. `git -C <clone> status --porcelain` must be empty; otherwise stop and ask.
  2. `git -C <clone> switch <base>` (skip if it's already checked out there), then
     `git -C <clone> merge --ff-only <branch>`. Pre-ship already rebased the branch onto `<base>`, so
     this fast-forwards; if it can't, rebase again (Phase 9) rather than creating a merge commit.
  3. With worktrees, remove the task's worktree afterwards (see layout.md); the branch stays.

If a tracker is configured and the user said yes, comment on the ticket (the branch, or "merged locally
into `<base>`", plus test and review results) and move it to `tracker.statuses.review`. Set `phase:
shipped` (kept) or `done` (merged) in `state.md`.
