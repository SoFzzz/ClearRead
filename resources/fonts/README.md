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

## Lexend (fuente de lectura por defecto)

| Campo | Valor |
|:---|:---|
| Archivo | `Lexend-Regular.ttf` (100 264 bytes). Familia `Lexend`, estilo `Regular` |
| SHA256 | `e2082c28389e9871d5d77ae9163d5c0c1c259fe39bdac91f73d56a600b61f60f` |
| Origen | Repositorio oficial https://github.com/googlefonts/lexend, rama `main` (en `7894f02b2e7eabc48595f1d4eff3b17b48c6e651` al descargar; el archivo cambió por última vez en `cd26b9c2538d758138c20c3d2f10362ed613854b`, 2022-09-22). URL: `https://raw.githubusercontent.com/googlefonts/lexend/main/fonts/lexend/ttf/Lexend-Regular.ttf` |
| Licencia | SIL Open Font License 1.1 (`Lexend-OFL.txt`, del mismo repositorio). Copyright 2018 The Lexend Project Authors, con el nombre reservado "RevReading Lexend" |
| Descargado | 2026-10-07 (tarea de desarrollo, a petición de la usuaria) |

## Atkinson Hyperlegible (opción de lectura)

| Campo | Valor |
|:---|:---|
| Archivo | `AtkinsonHyperlegible-Regular.ttf` (54 348 bytes). Familia `Atkinson Hyperlegible`, estilo `Regular` |
| SHA256 | `7fb917c89019896d0b52ee84b7cbb3304c18cb90b19a62f5e32712bd23e97669` |
| Origen | Repositorio https://github.com/googlefonts/atkinson-hyperlegible, rama `main` (en `1cb311624b2ddf88e9e37873999d165a8cd28b46` al descargar). URL: `https://raw.githubusercontent.com/googlefonts/atkinson-hyperlegible/main/fonts/ttf/AtkinsonHyperlegible-Regular.ttf` |
| Licencia | SIL Open Font License 1.1 (`Atkinson-OFL.txt`, del mismo repositorio). Copyright 2020 Braille Institute of America, Inc. |
| Descargado | 2026-10-07 |

- Las tres fuentes de lectura (Lexend, Atkinson Hyperlegible y OpenDyslexic) se eligen en Ajustes; Lexend es la de por defecto (`AppConfig.reading_font`).
- Solo se empaqueta el peso **Regular** de las dos nuevas: la lectura no usa negrita (la palabra resaltada se distingue por el fondo, el color y el subrayado). Si Qt recibiera una negrita de una fuente sin ese peso, la sintetizaría ensanchando el trazo y moviendo las líneas.
- Cobertura comprobada con `QFontMetricsF.inFontUcs4` para `ñ Ñ á é í ó ú ü ¿ ¡ « » — “ ”` en las tres (hay un test: `tests/test_redesign.py`).
- **No se ha encontrado ni citado ningún estudio revisado por pares sobre Lexend ni sobre Atkinson Hyperlegible**; se eligieron por forma, licencia y cobertura (ver `docs/design-system/README.md` §1.4).
- Son recursos, no dependencias de Python. La OFL permite incrustarlas y redistribuirlas; no se renombran ni se modifican.
