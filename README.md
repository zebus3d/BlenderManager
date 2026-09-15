# Blender Downloads Manager

A desktop app (built with **Python + PySide6/Qt**) to **discover, download,
organize and launch** [Blender](https://www.blender.org/) builds: stable, LTS,
daily and the official experimental branches. It is cross-platform (Linux,
Windows and macOS) and designed to be **portable**: once packaged, users don't
need to install anything.

![Grid view](https://cdn.jsdelivr.net/gh/zebus3d/BlenderManager@master/docs/img/store_grid.png)

## Features

- **Build store** with cards and icons, channel filters (LTS, Stable, Daily,
  Experimental) and search by version or branch.
- **Grid or list view**, with a **zoom slider** to choose the icon size
  (Dolphin-style). `Ctrl +` / `Ctrl -` change it from the keyboard and `Ctrl 0`
  (or `Ctrl` + click on the slider) goes back to the default size.
- **Automatic detection** of your operating system and architecture.
- **Download for another platform or architecture**: pick Windows, macOS or ARM64
  in the filter bar to grab a build for a friend or a USB stick, not just for the
  machine you are running on. Your choice is remembered for next time.
- **Downloads with progress**, **SHA-256** integrity verification and automatic
  extraction (`.tar.xz` on Linux, `.zip` on Windows). On macOS Blender is only
  published as `.dmg`, which is not extracted: the app downloads it, reveals it
  in Finder and tells you to open it.
- **Installed versions**: launch or uninstall them from the app. The filters and
  search apply to them too, and they are highlighted in the store so you can tell
  at a glance what you already have.
- **Blender runs detached**: closing the manager does **not** close the Blender
  instances you launched from it.
- **Release notes one click away**: every build card has a small blue **i** that
  opens that series' release notes (e.g.
  `developer.blender.org/docs/release_notes/5.2/`) in your browser, so you can
  check what changed before downloading.
- **Self-updating**: packaged builds (Linux AppImage, Windows) replace themselves
  and restart; a source checkout runs `git pull` and restarts instead.
- **Interface in English and Spanish** with automatic language detection, plus
  **tooltips** and a **portable mode** (settings live next to the executable).

![Installed build list](https://cdn.jsdelivr.net/gh/zebus3d/BlenderManager@master/docs/img/installed_list.png)

![Update dialog](https://cdn.jsdelivr.net/gh/zebus3d/BlenderManager@master/docs/img/update_dialog.png)

## A small, readable codebase

Beyond being a useful tool, this project is meant to be **read and learned
from**. It is a complete desktop application in about 4,000 lines of Python,
split into clear layers:

- **`model/`** — plain data classes (`Build`, `InstalledBuild`).
- **`services/`** — the real work (API, downloads, extraction, settings...).
  They know nothing about Qt, so they can be tested without a window.
- **`ui/`** — the interface. `ui/qss.py` is a single Qt stylesheet that holds the
  whole look; `ui/widgets/` holds the behaviour.

If you are learning Python or Qt, start with the guides in
[`doc/`](doc/README.md) (in Spanish): they walk through the architecture, the Qt
concepts used, the design system and a full worked example of adding a new
feature. The code comments are in Spanish (Spain) and explain not just *what*
each part does, but *why* the decisions were made.

## How is it different from Blender Launcher V2?

[Blender Launcher V2](https://github.com/Victor-IX/Blender-Launcher-V2) is the
de-facto tool for this job and the reason this project exists: it proved that
Blender's official JSON API is all you need to manage builds reliably. It is
also **more complete** than Blender Manager, especially on Windows — forks
(Bforartists, UPBGE), favorites, templates, a tray icon, a running-instance
counter and `.blend` association.

Blender Manager deliberately does **less**: find a build, download it, launch it.
The bet is that most people only need the official builds and want that one flow
to have as little friction as possible, particularly on Linux.

| | **Blender Manager** | **Blender Launcher V2** |
|---|---|---|
| UI toolkit | Qt Widgets (PySide6) | Qt-based |
| Focus | Official builds only | Official builds, forks and experimental branches |
| Views | Grid **and** list, with a zoom slider | Library / downloads pages |
| Languages | English and Spanish | English |
| Linux download | One AppImage (~70 MB) | Two Linux zips (~95-107 MB), pick the right one |
| Running from source | Python + PySide6 | Python + PySide/Qt dependencies |

> A note on **experimental branches**: both apps use the same endpoint
> (`builder.blender.org/download/experimental/`). Blender has barely published
> branch builds since ~2021, so that tab is usually empty. The app keeps it
> implemented and lights it up automatically if a branch appears.

### Why it may suit you better on Linux

- **One file, no install.** `BlenderManager-x86_64.AppImage` (~70 MB) is the
  whole app. Blender Launcher V2 ships two different Linux zips (`Linux_x64` and
  `Ubuntu_x64`, ~95-107 MB) and you have to know which one matches your system.
- **Nothing to fight with on the graphics side.** Qt Widgets paints with its
  **raster engine (CPU)**, so the app does not touch OpenGL: no Mesa version to
  match, no `No matching FB config found` on a modern Wayland session, and the
  same AppImage works on Arch and on an older Ubuntu.
- **Runs from source with a virtualenv.** `./run.sh` creates it and launches the
  app; the only dependency is PySide6. Downloads, extraction and the Blender API
  use the standard library.
- **Updates the way you installed it.** The AppImage replaces itself and
  restarts; a git checkout runs `git pull --ff-only` and restarts. Either way you
  never go back to the browser to update.
- **It speaks Spanish**, detected automatically from your locale.

## Running from source

Requirements: **Python 3.12 or newer**. The only dependency is **PySide6**, which
is installed for you by the launcher script:

```bash
git clone https://github.com/zebus3d/BlenderManager.git
cd BlenderManager
./run.sh
```

`run.sh` creates `.venv` on first run and installs `requirements.txt`
(PySide6-Essentials) into it. To do it by hand:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

The build store opens on start. The **first time**, if you already have installed
builds in the destination folder, it opens on the **Installed** tab; otherwise it
opens the **Store**. The default destination is `~/Descargas/Blenders` (change it
in **Settings**).

### Command-line options

```bash
python src/main.py                     # open the UI
python src/main.py --debug             # UI with verbose logging
python src/main.py --smoke             # list builds in the console (no window)
python src/main.py --screenshot r.png  # start, save a screenshot and quit
```

## Portable mode

Create an empty file named `portable` next to the executable (or next to
`src/main.py` if you run from source). Settings, cache and logs are then stored
in that same folder instead of the user's config directory.

## Tests

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -t . -s tests
```

The UI tests run with Qt's **offscreen** plugin, so they need no display (that is
what CI uses too). They cover the data model, the services (API filtering, safe
extraction, settings, updates) and the window logic that can be checked without a
screen: filters, grid columns, zoom and the dialogs.

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

- **Every push to `master` updates a single rolling pre-release** (e.g.
  `v1.3.0`): the workflow rebuilds the three binaries, moves the tag to the new
  commit and replaces the assets. There is never more than one pre-release.
- **Promoting** it (Actions → *promote*) turns it into the final release without
  rebuilding: the pre-release already carries the version of the release it aims
  to be, so promoting only removes the pre-release flag and marks it *latest*.
  The next push then starts the following cycle (`v1.4.0`).
- The in-app auto-update only looks at the *latest* release, which **ignores
  pre-releases**: while a cycle is being iterated on, nobody is notified.
- Pushing a `vX.Y.Z` tag publishes a final release with that exact version
  directly. Never re-tag binaries that were built for another version: the
  version is baked into the executable, so the app would update itself in a loop.
- **Running from source never prompts for an update**: a checkout is ahead of the
  last tag by definition, so comparing it with the latest release would offer to
  "update" to a binary that may be older than the code you are running. The title
  shows the real state of the checkout (`1.3.0-19-g24a0b43`), and
  **Settings → Check for updates now** runs `git pull --ff-only` and restarts.

The binaries are **not** committed to the repository; they are downloadable from
the Release (or from the workflow run).

#### Why the Linux build is a plain Ubuntu 22.04 job

Earlier versions of this app used **Kivy**, which renders through OpenGL via
SDL2. Its bundled SDL2 asked Xwayland for a framebuffer config with `STENCIL=8`
and got zero results on **Mesa 25/26** (Linux Mint 22, Arch/CachyOS), so the
window never opened:

```
Window: Provider: sdl2
No matching FB config found
```

Building against Arch's system SDL2 2.32 worked around it, but PyInstaller then
bundled the whole graphics stack and the AppImage grew to ~170 MB.

The UI now runs on **Qt Widgets**, which paints with the **raster engine (CPU)**
by default: no OpenGL, no Mesa version to match, nothing to bundle. So the job is
a plain `ubuntu-22.04` runner, with no container and no SDL2 step.

The one thing that still has to be right is the Qt `xcb` platform plugin: Qt
loads it even when it renders on the CPU, and its dependencies must be installed
**on the runner** so PyInstaller bundles them. If they are missing, the AppImage
dies on the user's machine with:

```
qt.qpa.plugin: Could not load the Qt platform plugin "xcb"
```

The job installs `libxcb-icccm4`, `libxcb-image0`, `libxcb-keysyms1`,
`libxcb-randr0`, `libxcb-render-util0`, `libxcb-shape0`, `libxcb-xinerama0`,
`libxcb-xkb1`, `libxkbcommon-x11-0` and `libxcb-cursor0` (the last one is
required since Qt 6.5).

If you change the CI Linux job:

1. Build the AppImage locally and verify it runs on a recent KDE Plasma / GNOME
   Wayland session before pushing.
2. Check that `ldd dist/BlenderManager/_internal/PySide6/Qt/plugins/platforms/libqxcb.so
   | grep "not found"` prints nothing.
3. Check the AppImage is around 70 MB (much smaller means a plugin dependency was
   left out; much bigger means something unnecessary got bundled).
4. Make sure `packaging/inject_version.py` was called **before** PyInstaller with
   the same version the release tag carries — otherwise auto-update will detect a
   mismatch and loop. The CI workflow does this in the "Inyectar version" step.

The full reasoning, with the reproducible `podman` validation recipe, is in
`AGENTS.md`.

## Linux requirements

Building on `ubuntu-22.04` means the portable binary needs **glibc 2.35 or
higher** (Ubuntu 22.04+, Debian 12+, Mint 21/22, Fedora 36+, Arch). PySide6
itself only asks for glibc 2.34, so the floor is set by the embedded Python.

The **AppImage** needs nothing installed, although on systems without `libfuse2`
you have to run it with `--appimage-extract-and-run` (on Arch: `sudo pacman -S
fuse2`).

## Project structure

```
src/
  main.py            # entry point and arguments
  paths.py           # paths (source vs. packaged)
  version.py         # __version__ (the CI rewrites it from the tag)
  i18n.py            # English/Spanish translations
  model/build.py     # data model (Build, InstalledBuild)
  services/          # UI-independent (imports no Qt):
    api.py           # queries and caches Blender's JSON API
    detector.py      # operating system and architecture
    settings.py      # persistent settings and portable mode
    downloader.py    # threaded download with progress and SHA-256
    extractor.py     # safe tar/zip extraction
    installed.py     # scans installed versions
    launcher.py      # launches Blender (detached process)
    updater.py       # checks and applies updates (binary or git pull)
  ui/
    qss.py           # the whole look: one Qt stylesheet
    theme.py         # colour tokens (measured WCAG contrast)
    icons.py         # Font Awesome glyphs
    fonts.py         # icon font loading / glyph_icon()
    widgets/         # buttons, cards, dialogs and the main window
  assets/            # Blender logo, app icon and icon font
doc/                 # architecture guide in Spanish (start at doc/README.md)
tests/               # unit tests (unittest, UI with Qt's offscreen plugin)
packaging/           # PyInstaller spec, AppImage script and .desktop
run.sh               # development launcher (creates .venv if missing)
dist/                # build output (binaries ignored by git)
```

## Credits

This project finishes earlier attempts of mine (`BlenderDownloader` in Qt and
`BlenderManager` in Kivy) and is inspired by
[Blender Launcher V2](https://github.com/Victor-IX/Blender-Launcher-V2): the idea
of using Blender's JSON API and the LTS version map comes from it, which avoids
the fragile scraping of the first versions.

The Kivy version worked, but its OpenGL/SDL2 requirement meant a different
combination of Mesa and SDL2 for every distro; the UI was ported to Qt Widgets
for that reason alone (see "Why the Linux build is a plain Ubuntu 22.04 job").

The Blender logo is a trademark of the [Blender Foundation](https://www.blender.org/).
Icons are from [Font Awesome Free](https://fontawesome.com/) (SIL OFL 1.1).
