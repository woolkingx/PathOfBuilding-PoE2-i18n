# Release Notes for the i18n Fork

This repository is a forked localization release, not the upstream Path of
Building Community release pipeline. Do not use the upstream maintainer release
workflow here.

## Release Shape

```text
dev      -> upstream clone baseline b8048682
release  -> cleaned i18n release branch
```

The release branch should contain only the files needed to inspect, build, and
run the i18n fork. Agent planning files, scratch work, logs, local settings, and
temporary audit outputs must not be published.

## Source Preparation

Before syncing or publishing release:

1. Update `README.md` for this i18n fork.
2. Add a top-level i18n entry to `CHANGELOG.md`.
3. Keep `locale/zh_TW/LC_MESSAGES/*.po` as the canonical translation source.
4. Regenerate `src/Data/Lang/zh_TW/*.lua` from PO catalogs.
5. Keep extraction/audit scripts that are needed to verify the i18n boundary.
6. Remove agent-only planning files and local workflow files.
7. Confirm no `zh_CN` files are changed by the release cleanup.

## Verification

Run the i18n gates before creating a release snapshot:

```bash
python3 scripts/compile-lang.py --check locale/zh_TW/LC_MESSAGES/pob.po src/Data/Lang/zh_TW/pob.lua
python3 scripts/compile-lang.py --check locale/zh_TW/LC_MESSAGES/items.po src/Data/Lang/zh_TW/items.lua
python3 scripts/compile-lang.py --check locale/zh_TW/LC_MESSAGES/skills.po src/Data/Lang/zh_TW/skills.lua
python3 scripts/compile-lang.py --check locale/zh_TW/LC_MESSAGES/passives.po src/Data/Lang/zh_TW/passives.lua
python3 scripts/compile-lang.py --check locale/zh_TW/LC_MESSAGES/stats.po src/Data/Lang/zh_TW/stats.lua
python3 scripts/audit-zh-tw-display-closure.py --root . --format json --fail-on-open
python3 scripts/audit-display-identity-i18n.py --root . --format json --output work/pob/display-identity-audit.json --fail-on-open
python3 scripts/analyze-i18n-display-graph.py --root . --format md --output work/pob/dropdown-i18n-graph.md --fail-on-high
python3 scripts/audit-ui-message-i18n.py --root . --domain ui --format json --output work/pob/ui-message-audit-ui.json --fail-on-open
luac -p src/Modules/Lang.lua src/Data/Lang/zh_TW/pob.lua src/Data/Lang/zh_TW/items.lua src/Data/Lang/zh_TW/skills.lua src/Data/Lang/zh_TW/passives.lua src/Data/Lang/zh_TW/stats.lua
if git diff --name-only | rg '(^|/)zh_CN(/|$)'; then exit 1; else echo 'zh_CN untouched'; fi
git diff --check
```

## Publish

After the source tree is clean and release-ready:

1. Sync the cleaned source to the release worktree.
2. Build or stage release artifacts from the release worktree.
3. Commit the release worktree.
4. Push only the fork's public release branch.
5. Open an upstream issue with the compare link and a short maintainer-facing
   summary.
