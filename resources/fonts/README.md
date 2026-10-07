# Fuentes

Archivos que viajan dentro del `.exe` (§6.3). **El código de la app nunca los descarga**: se descargaron una sola vez como tarea de desarrollo y se versionan aquí. Se cargan con `QFontDatabase.addApplicationFont` (ver `clearread.ui.fonts`).

## OpenDyslexic (fuente de lectura, Regular y Bold)

| Campo | Valor |
|:---|:---|
| Archivos | `OpenDyslexic-Regular.otf` (175 872 bytes), `OpenDyslexic-Bold.otf` (184 472 bytes) |
| SHA256 Regular | `32f5840fb2bf844bdabafe372591ddfb9286e98117f5b21950aaf54ea856919a` |
| SHA256 Bold | `5d690ea4c87ccb0d5d5d81487826a395e9b20a6c1d606f1f262c060d2bef4f03` |
| Origen | Carpeta `compiled/` de la rama `main` del repositorio oficial https://github.com/antijingoist/opendyslexic (enlazado desde https://opendyslexic.org). Última modificación de ambos archivos: commit `77bda89f3f2069c78d81d33de43b461c2de6c48e` (2025-04-10, "Disabled auto-generating ligatures for fi, etc."); `main` estaba en `1824da5c0e41dc3e13ffc7f3a636dcaf695d61b7` al descargar. URL: `https://raw.githubusercontent.com/antijingoist/opendyslexic/main/compiled/OpenDyslexic-Regular.otf` (y `-Bold.otf`) |
| Licencia | SIL Open Font License 1.1 (`OFL.txt`, del mismo repositorio). Copyright (c) 2019-07-29 Abbie Gonzalez, con el nombre reservado "OpenDyslexic" |
| Descargado | 2026-10-07 |

- Es un recurso, no una dependencia de Python. La OFL permite incrustarla en la app y redistribuirla; no se renombra ni se modifica.
- Solo se incluyen Regular y Bold (las que usa el design system, §1.4).
- **Por qué `main` y no la última release (v0.91.12, 2019-10-17).** Se probaron tres versiones renderizando `leyó canción ó á é í ú ñ ü ¿¡` con Qt: la v0.91.12 dibuja el acento de la `ó` desplazado a la derecha (parece un apóstrofo: `leyo´`), y la v0.91.2 dibuja los acentos como puntos *debajo* de la vocal. Los archivos de `main` dibujan todas las tildes encima de su vocal. Comparación (de arriba abajo: `main`, v0.91.2, v0.91.12): `docs/design-system/mockups/real/fuente_comparacion_acentos.png`.
- Cobertura comprobada con `QFontMetrics.inFontUcs4`: `ñ Ñ á é í ó ú ü ¿ ¡ « » — “ ”`.
