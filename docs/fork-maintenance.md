# Maintaining the 6 Pro fork

This fork retains the `xiaomi_miot` integration domain. Its `main` branch includes
the 6 Pro changes and the HACS settings needed to download source directly from
the branch. No release ZIP is required.

The `add-xiaomi-airp-va6` branch contains the upstream contribution. Keep
fork-specific HACS settings on `main` so they do not enter the upstream PR.

## HACS tracking

Use `lewingan/hass-xiaomi-miot` as the installed HACS repository and select `main`.
Only one installed HACS repository should manage `custom_components/xiaomi_miot`.
The official repository and this fork use that same directory.

HACS metadata refreshes do not replace installed files. A download, redownload,
or `update.install` call replaces them with files from the tracked repository.
Tracking this fork therefore makes future downloads retain the patch.

## Incorporating upstream changes

The **Sync upstream** GitHub Actions workflow runs daily at **03:17 Singapore
time** (19:17 UTC), subject to GitHub scheduling delays. It can also be started
from the Actions tab using **Run workflow** on `main`.

It prepares a normal merge from upstream `master`, then tests the exact candidate
with current and minimum supported Home Assistant, hassfest and HA configuration
checks. Local guards check the candidate's HACS settings and integration domain.
The HACS action separately checks the published fork's eligibility; it reads
GitHub rather than the local candidate checkout. The publishing job receives the original
candidate bundle only after validation succeeds; it does not execute candidate
code. It checks that `main` has not changed during testing and pushes without
forcing. Purifier regression coverage and the fork's HACS settings are required.

Conflicts, failed checks and changes to `.github/workflows` stop the sync and
leave `main` unchanged. Review workflow changes manually; the automation uses
only GitHub's built-in token and does not have workflow-edit permissions. Failed
runs and their logs appear in Actions; email/web notifications follow your
GitHub notification settings. Scheduled runs skip validation when upstream is
already included; manual runs validate even when no merge is needed.

This updates the fork only. It does not download anything to Home Assistant or
restart it, and it holds no Home Assistant credentials. After a tested update,
redownload `main` through HACS and restart HA, retaining a component backup.
The source is upstream `master`, so updates may include unreleased changes.

GitHub can disable scheduled workflows after 60 days without repository
activity. Re-enable the workflow in Actions if necessary. Once an official
release includes verified support for this purifier, disable **Sync upstream**
in Actions and switch HACS back to that official release. The upstream support
PR still needs to be submitted; a model-name match alone is not proof that all
controls and sensors work.

### Manual recovery

The local remotes are:

- `origin`: `https://github.com/lewingan/hass-xiaomi-miot.git`
- `upstream`: `https://github.com/al-one/hass-xiaomi-miot.git`

```sh
git switch main
git fetch upstream
git merge upstream/master
python -m pytest -q
git push origin main
```

Resolve any conflicts while retaining the 6 Pro support and this fork's HACS
download settings. Update the upstream contribution branch separately when
preparing its PR. HACS downloads the resulting branch; it does not merge upstream
changes or reapply local patches.

After a tested commit is pushed, redownload this fork's `main` branch in HACS and
restart Home Assistant. Retain a component backup before each deployment.

Once support is merged and included in an official release, switch HACS back to
the official repository and install that release. The integration domain remains
the same, so switching source does not require recreating device configuration.

Physical-device validation remains pending; see [the model notes](xiaomi.airp.va6.md).
