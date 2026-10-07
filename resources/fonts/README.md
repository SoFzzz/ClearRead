# Fuentes

Archivos que viajan dentro del `.exe` (§6.3). **El código de la app nunca los descarga**: se descargaron una sola vez como tarea de desarrollo y se versionan aquí. Se cargan con `QFontDatabase.addApplicationFont` (ver `clearread.ui.fonts`).

## OpenDyslexic (fuente de lectura, un solo peso)

| Campo | Valor |
|:---|:---|
| Archivo | `opendyslexic.otf` (233 008 bytes). Familia `OpenDyslexic`; Qt la ve con un único estilo, `Bold` |
| SHA256 | `90933562f30d429c78a867b3e3001abf80e72619127c37c61bdaec6c156f4ee8` |
| Origen | Carpeta `compiled/` de la rama `main` del repositorio oficial https://github.com/antijingoist/opendyslexic (enlazado desde https://opendyslexic.org). Última modificación del archivo: commit `cbd140088db3c8ef3c87f49652dbb2542cb8e065` (2019-11-06); `main` estaba en `1824da5c0e41dc3e13ffc7f3a636dcaf695d61b7` al descargar. URL: `https://raw.githubusercontent.com/antijingoist/opendyslexic/main/compiled/opendyslexic.otf` |
| Licencia | SIL Open Font License 1.1 (`OFL.txt`, del mismo repositorio). Copyright (c) 2019-07-29 Abbie Gonzalez, con el nombre reservado "OpenDyslexic" |
| Descargado | 2026-10-07 |

- Es un recurso, no una dependencia de Python. La OFL permite incrustarla en la app y redistribuirla; no se renombra ni se modifica.
- **Por qué esta variante (decisión de la usuaria, 2026-10-07).** Es la variante oficial `compiled/opendyslexic.otf`, que centra la tilde de la `ó` y de la `é` sobre su vocal; los `OpenDyslexic-Regular.otf` y `-Bold.otf` de la misma carpeta la dejaban algo desplazada. Comparación: `docs/design-system/mockups/real/acentos_variante_opendyslexic_otf.png`.
- **Por qué ya no están Regular ni Bold.** Esta variante es de un solo peso y ya es gruesa. La única negrita que usaba la vista era la de la palabra resaltada, que con esta fuente no aportaba nada (ver README del design system, §11); se quitó, y el resaltado se distingue por el fondo, el color y el subrayado. Si Qt recibiera una negrita de esta fuente la sintetizaría ensanchando el trazo, lo que movería las líneas.
- Cobertura comprobada con `QFontMetrics.inFontUcs4`: `ñ Ñ á é í ó ú ü ¿ ¡ « » — “ ”`. Verificada además a ojo en `docs/design-system/mockups/real/lectura_real_*.png`.
