# Shipping: push, MR/PR per codebase, ticket update

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

### github (`gh`)

```bash
( cd <repo> && gh pr create --base <base> --head <branch> --title "<KEY>: <title>" \
    --body-file <ws>/tasks/<folder-key>/mr-<name>.md [--draft] )
```

`gh pr create` prints the PR URL. If a PR for the branch already exists, get it with
`( cd <repo> && gh pr view <branch> --json url -q .url )`.

### gitlab (`glab`)

```bash
( cd <repo> && glab mr create --source-branch <branch> --target-branch <base> \
    --title "<KEY>: <title>" --description "$(cat <ws>/tasks/<folder-key>/mr-<name>.md)" --yes [--draft] )
```

For self-hosted GitLab, `glab` must be logged in to that host (`glab auth login --hostname <host>`). If
`glab` is missing, tell the user (`brew install glab`, or see the glab docs) and offer the MR-creation URL
printed by `git push` as a fallback. If an MR already exists: `( cd <repo> && glab mr view <branch> -F json )`.

## 3. Cross-link

When more than one codebase is affected, update each MR/PR body's "Related changes" with the others' URLs:

Update `tasks/<folder-key>/mr-<name>.md`, then:

- github: `gh pr edit <url> --body-file <ws>/tasks/<folder-key>/mr-<name>.md`
- gitlab: `( cd <repo> && glab mr update <iid> --description "$(cat <ws>/tasks/<folder-key>/mr-<name>.md)" )`

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
