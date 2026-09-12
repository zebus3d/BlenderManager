# Carpeta de distribución

Aquí se colocan los paquetes finales listos para el usuario. Los binarios no se
guardan en el repositorio (están en `.gitignore`); esta carpeta se genera al
compilar con `packaging/build.sh` o la descarga el flujo de GitHub Actions.

Contenido esperado:

| Plataforma | Archivo                             | Cómo se genera |
|------------|-------------------------------------|----------------|
| Linux      | `BlenderManager-x86_64.AppImage`    | `packaging/build.sh --appimage` / CI |
| Windows    | `BlenderManager-windows-x86_64.zip` | CI |
| macOS      | `BlenderManager-macos.zip`          | CI |

En CI, el artefacto `BlenderManager-linux` contiene únicamente el
`BlenderManager-x86_64.AppImage` (sin carpeta `dist/` ni `.tar.gz`).

### Modo portable

Al descomprimir el binario, crea un archivo vacío llamado `portable` junto al
ejecutable y los ajustes, el caché y los registros se guardarán en esa misma
carpeta (ideal para llevar en un pendrive).

### Notas

- El AppImage puede necesitar `libfuse2`; si no está, se ejecuta con
  `./BlenderManager-x86_64.AppImage --appimage-extract-and-run`.
- Los binarios de Windows y macOS se compilan en CI y todavía no se han podido
  probar en su sistema real.
