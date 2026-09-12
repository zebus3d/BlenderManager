# Distribution folder

This folder holds the final packages ready for users. The binaries are **not**
stored in the repository (they are in `.gitignore`); they are produced by
`packaging/build.sh` or by the GitHub Actions workflow.

Expected contents:

| Platform | File                                | How it is built |
|----------|-------------------------------------|-----------------|
| Linux    | `BlenderManager-x86_64.AppImage`    | `packaging/build.sh --appimage` / CI |
| Windows  | `BlenderManager-windows-x86_64.zip` | CI |
| macOS    | `BlenderManager-macos.zip`          | CI |

On CI, the `BlenderManager-linux` artifact contains only the
`BlenderManager-x86_64.AppImage` (no `dist/` folder, no `.tar.gz`).

### Portable mode

After extracting the binary, create an empty file named `portable` next to the
executable and the settings, cache and logs will be stored in that same folder
(handy for a USB stick).

### Notes

- The AppImage may need `libfuse2`; if it is not available, run it with
  `./BlenderManager-x86_64.AppImage --appimage-extract-and-run`.
- Windows and macOS binaries are built on CI and have not been tested on real
  systems yet.
