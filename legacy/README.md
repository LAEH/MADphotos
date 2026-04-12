# Legacy branches — MADphotos

Archived git bundles of branches that were deleted from `origin` to keep the repo tidy. Each `.bundle` is a self-contained, clone-able copy of the branch's full history — nothing is lost.

## Contents

- `gh-pages.bundle` (3.0M) — see [`gh-pages.md`](gh-pages.md)

## Restoring a branch from a bundle

```bash
# Inspect what a bundle contains
git bundle list-heads legacy/<name>.bundle

# Fetch it back as a local branch
git fetch legacy/<name>.bundle '*:refs/heads/restored-<name>'

# Or clone a fresh copy from just the bundle
git clone legacy/<name>.bundle /tmp/recovered-<name>
```
