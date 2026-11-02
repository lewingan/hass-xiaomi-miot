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
