# Packaging

## Debian / Ubuntu (skeleton)

```bash
# From repo root, with packaging tools installed:
#   sudo apt install debhelper dh-python python3-setuptools
cd packaging
# Link or copy debian/ next to a build tree — simplest local recipe:
cd ..
ln -sfn packaging/debian debian
dpkg-buildpackage -us -uc -b
```

The package installs:

| Path | Purpose |
|------|---------|
| `/usr/lib/netmedic/netmedic/` | Helper modules |
| `/usr/libexec/netmedic/helper` | pkexec entry |
| `/usr/share/polkit-1/actions/com.kayab.netmedic.policy` | Polkit actions |

GUI/console entry still comes from `pip install` / setuptools until full pybuild wiring is finished.

Until then prefer:

```bash
./install.sh
./scripts/install-polkit-policy.sh
netmedic --status
```
