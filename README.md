<p align="center">
  <img src="resources/icons/app_logo.png" alt="Logo de ClearRead" width="120">
</p>

<h1 align="center">ClearRead</h1>

<p align="center">
  <b>Lectura asistida para estudiantes con dislexia.</b><br>
  Convierte PDFs y fotos de apuntes en un texto cómodo de leer, que la app lee en voz alta resaltando cada palabra.
</p>

<p align="center">
  Windows 10/11 · 100% offline · Asistente de IA opcional
</p>

---

## El problema

Leer una guía fotocopiada, un examen o unos apuntes escaneados exige un esfuerzo extra a quien tiene dislexia: letras apretadas, líneas densas en las que es fácil perderse y palabras largas difíciles de descomponer. ClearRead transforma ese material en una superficie de lectura adaptada y añade apoyo auditivo sincronizado.

## Qué hace

| Función | Descripción |
|:---|:---|
| **Abre PDFs y fotos** | PDF (digital o escaneado), JPG, PNG, JFIF, BMP y TIFF. Arrastrar y soltar o elegir archivo. |
| **OCR local con IA** | Reconoce el texto de fotos y escaneos con un modelo de deep learning (RapidOCR sobre ONNX) que funciona sin internet y reconoce la ñ, las tildes y los signos ¿ ¡. Endereza automáticamente páginas inclinadas. |
| **Lectura en voz alta sincronizada** | La voz de Windows lee el texto respetando comas y puntos mientras se resalta la palabra que suena y una regleta marca la línea. Pausar, reanudar y velocidad ajustable. |
| **Tú controlas la voz** | Un clic en una palabra solo marca desde dónde leer, sin sonido; la voz suena únicamente con **Reproducir** o la tecla **Espacio**, y **Pausa** la detiene al instante. Un doble clic selecciona la palabra y abre el menú del asistente. |
| **Páginas** | Los documentos conservan sus páginas: barra con Anterior, número de página y Siguiente, y dos vistas, **Continua** (todo seguido) o **Por páginas**. Con la voz en marcha, la página pasa sola. |
| **Sílabas coloreadas** | Segmentación silábica fonética del español. Se activan y desactivan con el botón **Sílabas** de la barra de lectura (o la tecla `S`) y también desde Ajustes. |
| **Modo foco** | Atenúa todo menos la línea que se está leyendo. |
| **Tipografía adaptable** | Lexend (por defecto), Atkinson Hyperlegible u OpenDyslexic; tamaño, interlineado y espaciado ajustables. |
| **Temas claro y oscuro** | Contraste de texto ≥ 7:1 (WCAG AAA), comprobado con la fórmula oficial del W3C. El texto que seleccionas con el ratón se marca en amarillo y morado (no con el color de Windows). |
| **Asistente de IA (opcional)** | Clic derecho → *Explicar esta palabra* o *Simplificar este párrafo*, en lenguaje sencillo. Solo se envía el texto que eliges. |
| **Mis palabras** | Glosario automático con las palabras que te explicó el asistente, para repasarlas sin conexión. Se ordenan en **temas** (por ejemplo, uno por asignatura). |
| **Continuar leyendo** | Recuerda dónde quedaste en cada documento; los ya procesados abren al instante. |
| **Mi biblioteca** | Hasta 200 documentos, con **carpetas** para ordenarlos (eliges dónde guardar cada documento nuevo en «Guardar en:», o creas la carpeta ahí mismo), búsqueda por nombre y la opción de quitar los que ya no necesitas (tu archivo original nunca se toca). |
| **Español e inglés** | La interfaz se puede usar en los dos idiomas; al cambiar de idioma, ClearRead pide confirmación y se reinicia solo. La voz de lectura cambia al idioma de la interfaz si hay una voz de Windows instalada en ese idioma (el texto de los documentos se sigue tratando como español, así que con voz inglesa se lee con pronunciación inglesa). |
| **Zoom** | `Ctrl` + `+` / `-` cambia el tamaño de la letra y `Ctrl` + `0` lo restablece. |

## Atajos de teclado

| Atajo | Acción |
|:---|:---|
| `Espacio` | Reproducir / pausar |
| `Esc` | Detener la lectura (o cerrar el asistente, el procesado o Ajustes) |
| `F` | Modo foco |
| `S` | Activar / desactivar las sílabas de colores |
| `Av Pág` / `Re Pág` | Bajar / subir una pantalla (en "Por páginas", pasa de página al llegar al borde) |
| `Ctrl` + `←` / `→` | Página anterior / siguiente |
| `Ctrl` + `Inicio` / `Fin` | Primera / última página |
| `Ctrl` + `+` / `-` / `0` | Letra más grande / más pequeña / tamaño por defecto |
| `Ctrl` + `I` | Abrir o cerrar el asistente |
| `Ctrl` + `O` | Elegir archivo (en Inicio) |
| `Ctrl` + `,` | Ajustes |
| `Alt` + `←` | Volver |

## Descarga e instalación

1. Ve a [**Releases**](https://github.com/SoFzzz/ClearRead/releases) y descarga `ClearRead-Setup-1.5.0.exe`.
2. Ábrelo y sigue el asistente: elige la carpeta de instalación y deja marcada la casilla del **icono en el Escritorio** si lo quieres.
3. Si Windows muestra *"Windows protegió su PC"*: **Más información → Ejecutar de todas formas**. Aparece porque el instalador no está firmado digitalmente.
4. Abre ClearRead desde el Escritorio o el menú Inicio. Para quitarlo: *Configuración → Aplicaciones*. Tus documentos y palabras (`%APPDATA%\ClearRead`) no se borran.

Alternativa sin instalar: si el Release incluye el `.zip` portable, descomprímelo y abre `ClearRead\ClearRead.exe`.

No necesita Python ni internet. El asistente de IA es la única función que requiere conexión; sin ella, el resto de la app funciona igual.

## Privacidad

- Tus documentos **nunca salen de tu equipo**: el OCR, la voz y el formato son locales.
- El asistente de IA solo envía **la palabra o el párrafo que eliges**, y la primera vez te pide permiso.
- Tu biblioteca (documentos procesados, carpetas), tus palabras y las estadísticas se guardan solo en tu equipo (`%APPDATA%\ClearRead`); los documentos se pueden quitar uno a uno o borrar todos desde Ajustes.

## Arquitectura

```
ClearRead.exe (escritorio, núcleo offline)  ──HTTPS──►  Backend FastAPI (Render)  ──►  DeepSeek
  OCR · voz · formato · temas                           guarda la clave de la IA
                                                        limita el uso diario
```

- **App de escritorio:** Python 3.11 + PySide6 (Qt). El OCR y la voz corren en hilos propios para que la interfaz nunca se congele.
- **Backend propio:** FastAPI desplegado en Render. La clave de DeepSeek vive solo en el servidor, nunca en el `.exe`.
- La especificación completa está en [`document.md`](document.md) y el sistema de diseño (Anexo A), el despliegue del backend y la publicación de una versión (§6.6) en el mismo archivo.

### Tecnologías

| Capa | Tecnología |
|:---|:---|
| Interfaz | PySide6 (Qt 6) |
| PDF | pypdfium2 |
| OCR | RapidOCR + ONNX Runtime, modelo de reconocimiento latino PP-OCRv5 |
| Imagen | OpenCV, Pillow |
| Voz | SAPI5 de Windows vía pyttsx3 |
| Sílabas | silabeador |
| Backend | FastAPI, uvicorn, httpx |
| IA | DeepSeek |
| Empaquetado | PyInstaller (`--onedir`) + instalador Inno Setup |

## Para desarrolladores

Requisitos: Windows, **Python 3.11 x64**.

```powershell
# App
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m clearread          # ejecutar
.\.venv\Scripts\python -m pytest tests/ -v   # tests

# Backend
py -3.11 -m venv backend\.venv
.\backend\.venv\Scripts\python -m pip install -e ".\backend[dev]"
.\backend\.venv\Scripts\python -m pytest backend/tests -v

# Compilar el .exe (requiere resources/client_token.local.json, no versionado)
.\.venv\Scripts\python -m PyInstaller clearread.spec --clean --noconfirm

# Instalador (requiere Inno Setup 6)
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\clearread.iss
```

Guías (en [`document.md`](document.md) §6.6): despliegue del backend en Render y publicación de una versión con la prueba en máquina limpia.

### Estructura

```
src/clearread/      app de escritorio (core, services, workers, ui)
backend/            API FastAPI (proyecto independiente)
resources/          fuentes, modelos ONNX, iconos y documento de ejemplo
tests/              pruebas automáticas y scripts de prueba manual
document.md         especificación técnica y requisitos
```

## Limitaciones conocidas

- Solo Windows (la voz usa SAPI5).
- El OCR tarda unos segundos por página en documentos densos; las fórmulas químicas o matemáticas no se reconocen bien.
- La primera consulta al asistente puede tardar hasta un minuto si el servidor gratuito estaba en reposo.
- El reconocimiento con fotos de móvil reales aún no se ha calibrado con un set propio de fotos.
- La tipografía y el modo foco no se han probado todavía con lectores con dislexia.
- Las funciones nuevas (biblioteca y «Guardar en:», páginas, reinicio por cambio de idioma, voz por idioma, botón de sílabas y color de selección) se probaron con tests automáticos y con la app real en pantalla virtual, pero aún no con ratón físico, arrastrando un archivo desde el Explorador ni en el `.exe` recompilado.
- El selector «Guardar en:» se ve sin la flecha del desplegable (pendiente de arreglar).

## Créditos

- Fuentes: [Lexend](https://github.com/googlefonts/lexend), [Atkinson Hyperlegible](https://github.com/googlefonts/atkinson-hyperlegible) y [OpenDyslexic](https://github.com/antijingoist/opendyslexic), bajo licencia SIL Open Font License.
- Modelos OCR: PaddleOCR PP-OCR, distribuidos en ONNX por RapidOCR, bajo licencia Apache 2.0.
- Detalles de origen y licencias en [`resources/fonts/README.md`](resources/fonts/README.md) y [`resources/models/README.md`](resources/models/README.md).

---

Proyecto académico de la Universidad Cooperativa de Colombia (UCC), curso de Diseño.
