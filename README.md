# Blender Downloads Manager

A desktop app (built with Kivy) to **discover, download, organize and launch**
[Blender](https://www.blender.org/) builds: LTS, stable and development
(daily/alpha) versions. It is cross-platform (Linux, Windows and macOS) and
designed to be **portable**: once packaged, users don't need to install anything.

![Grid view](https://cdn.jsdelivr.net/gh/zebus3d/BlenderManager@master/docs/img/store_grid.png)

## Features

- **Build store** with cards and icons, channel filters (LTS, Stable, LTS + Stable,
  Daily) and search by version or branch.
- **Grid or list view**, with a **zoom slider** to choose the icon size (Dolphin-style).
- **Automatic detection** of the operating system and architecture.
- **Downloads with progress**, **SHA-256** integrity verification and automatic
  extraction (`.tar.xz` on Linux, `.zip` on Windows). On macOS Blender is only
  published as `.dmg`, which is not extracted: the app downloads it, reveals it
  in Finder and tells you to open it.
- **Configurable destination folder**, **remembered window size** and a list of
  **installed versions** (launch or uninstall them from the app).
- **Filters and search also apply to installed versions**.
- **Blender runs detached**: closing the manager does **not** close the Blender
  instances you launched from it.
- **Visual hints**: installed builds are highlighted, builds still to download
  are dimmed; buttons and cards highlight on hover.
- **Interface in English and Spanish** with automatic language detection.
- **Tooltips** on the controls.
- **Portable mode**: settings live next to the executable.

![List view](https://cdn.jsdelivr.net/gh/zebus3d/BlenderManager@master/docs/img/installed_list.png)

## Running from source

Requirements: **Python 3.12 or newer** and **Kivy**. Nothing else is needed:
downloads, extraction and the Blender API use the standard library.

### 1. Get the code

```bash
git clone https://github.com/zebus3d/BlenderManager.git
cd BlenderManager
```

### 2. Install Kivy

**Arch Linux** (recommended: Kivy compiled for the system Python):

```bash
sudo pacman -S python-kivy
```

**Other Linux distros, Windows or macOS** (virtual environment):

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Launch the app

```bash
python3 src/main.py
```

The build store opens on start. The **first time**, if you already have installed
builds in the destination folder, it opens on the **Installed** tab; otherwise it
opens the **Store**. The default destination is `~/Descargas/Blenders` (change it
in **Settings**).

> If you use a virtual environment, activate it first
> (`source .venv/bin/activate`) and use `python` instead of `python3`.

### Command-line options

```bash
python3 src/main.py                     # open the UI
python3 src/main.py --debug             # UI with verbose logging
python3 src/main.py --smoke             # list builds in the console (no window)
python3 src/main.py --watch             # hot-reload .kv/theme on save (development)
python3 src/main.py --screenshot r.png  # start, save a screenshot and quit
```

## Portable mode

Create an empty file named `portable` next to the executable (or next to
`src/main.py` if you run from source). Settings, cache and logs are then stored in
that same folder instead of the user's config directory.

## Tests

```bash
python3 -m unittest discover -t . -s tests -v
```

## Packaging

Packaging uses **PyInstaller** in *one-folder* mode (faster and easier to debug
than `--onefile`). The spec is cross-platform: `packaging/blendermanager.spec`.

Linux (portable binary and, optionally, an AppImage):

```bash
packaging/build.sh             # produces dist/BlenderManager
packaging/build.sh --appimage  # also produces dist/BlenderManager-x86_64.AppImage
```

### CI (GitHub Actions)

`.github/workflows/build.yml` runs the tests and produces artifacts for **Linux**
(`.AppImage`), **Windows** (`.zip`) and **macOS** (compressed `.app`).

- On every push to `master` it also publishes a **pre-release** with a per-build
  version (e.g. `v1.1.42`), so every compilation is downloadable from Releases.
- `.github/workflows/promote.yml` turns a pre-release into the **stable
  Release** with one click (Actions → *promote* → *Run workflow*). It reuses the
  binaries that were already built and verified, so the version baked into them
  keeps matching the tag.
- Pushing a `vX.Y.Z` tag also publishes a **stable Release**, rebuilding the
  binaries with that version.
- Only stable releases trigger the in-app auto-update, because the app checks
  `.../releases/latest`, which ignores pre-releases.
- When running from source (`python3 src/main.py`), the in-app update runs
  `git pull --ff-only` on a clean checkout and restarts the app instead of
  downloading a binary.

The binaries are **not** committed to the repository; they are downloadable from
the Release (or from the workflow run).

## Linux requirements

Building on `ubuntu-22.04` means the portable binary needs **glibc 2.35 or
higher**. The **AppImage** needs nothing installed, although on systems without
`libfuse2` you have to run it with `--appimage-extract-and-run`. The file to
share is `BlenderManager-x86_64.AppImage`.

## Project structure

```
src/
  main.py            # entry point and arguments
  paths.py           # paths (source vs. packaged)
  i18n.py            # English/Spanish translations
  model/build.py     # data model (Build, InstalledBuild)
  services/
    api.py           # queries and caches Blender's JSON API
    detector.py      # operating system and architecture
    settings.py      # persistent settings and portable mode
    downloader.py    # threaded download with progress and SHA-256
    extractor.py     # safe tar/zip extraction
    installed.py     # scans installed versions
    launcher.py      # launches Blender (detached process)
  ui/
    theme.py         # palette, colors and icon font
    icons.py         # Font Awesome glyphs
    widgets.py       # cards, sidebar and main controller
    tooltip.py       # tooltip / hover system
  views/gui.kv       # declarative UI (Kivy Language)
  assets/            # Blender logo, app icon and icon font
tests/               # unit tests (unittest)
packaging/           # PyInstaller spec, AppImage script and .desktop
dist/                # build output (binaries ignored by git)
```

## Credits

This project finishes two earlier attempts of mine (`BlenderDownloader` in Qt and
`BlenderManager` in Kivy) and is inspired by
[Blender Launcher V2](https://github.com/Victor-IX/Blender-Launcher-V2): the idea
of using Blender's JSON API and the LTS version map comes from it, which avoids
the fragile scraping of the first versions.

The Blender logo is a trademark of the [Blender Foundation](https://www.blender.org/).
Icons are from [Font Awesome Free](https://fontawesome.com/) (SIL OFL 1.1).
