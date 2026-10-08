# Cómo publicar ClearRead v1.0.0 y probarlo en una máquina limpia

Esta guía es para ti. El `.exe` se prueba primero en una **máquina limpia** (sin Python) y después se publica como *Release* en GitHub.

## 0. Antes de compilar: el token del backend
`clearread.spec` **se detiene con un mensaje claro** si no existe `resources/client_token.local.json`. Créalo (está ignorado por git) con el valor de `CLIENT_TOKEN` que pusiste en Render:

```json
{"client_token": "PEGA_AQUI_TU_CLIENT_TOKEN"}
```

Luego compila y empaqueta (PowerShell, en la carpeta del proyecto):

```powershell
.\.venv\Scripts\python -m PyInstaller clearread.spec --clean --noconfirm
Compress-Archive -Path dist\ClearRead -DestinationPath dist\ClearRead-v1.0.0-win64.zip -Force
(Get-FileHash dist\ClearRead-v1.0.0-win64.zip -Algorithm SHA256).Hash
```

Guarda el SHA256 que imprime: va en las notas del Release. Comprueba que el zip contiene la carpeta `ClearRead` completa, no solo el `.exe`.

## 1. Checklist en máquina limpia
Anota antes: marca/modelo del equipo, versión de Windows y fecha.

**Preparación**
- [ ] `python --version` y `py --version` fallan (no hay Python).
- [ ] Copia el `.zip` al equipo y extráelo entero.
- [ ] WiFi y Ethernet desactivados (o modo avión).

**Sin red**
- [ ] Al abrir `ClearRead.exe` aparece la ventana, con el icono correcto en la barra de tareas. Anota el tiempo con cronómetro.
- [ ] "Probar con un ejemplo" abre el texto de ejemplo.
- [ ] Una ficha privada en PDF digital se abre al instante (sin OCR).
- [ ] `sample_page_scanned.pdf` (escaneado) pasa por OCR y muestra texto.
- [ ] Una **foto JPG girada** se muestra con el texto derecho.
- [ ] Un **PDF con contraseña** muestra un mensaje claro y la app sigue abierta.
- [ ] Reproducir: se oye la voz y se resalta cada palabra.
- [ ] Pausar y reanudar continúa desde la palabra donde se pausó.
- [ ] Clic en una palabra: la lectura salta a esa palabra.
- [ ] Modo foco funciona.
- [ ] Cambiar de tema (Claro/Oscuro), de fuente (Lexend, Atkinson, OpenDyslexic) y de idioma (se aplica al reiniciar).
- [ ] El botón de IA aparece como "sin red" y no da errores; todo lo demás sigue funcionando.
- [ ] En Inicio, el documento reciente muestra "Seguir desde donde lo dejaste" y vuelve a su posición.

**Con red**
- [ ] Activa la red: el botón de IA se habilita.
- [ ] Si el backend llevaba ≥ 15 min sin uso, aparece "Despertando el asistente…" y luego la respuesta. Anota el tiempo.
- [ ] Explicar una palabra responde en español y la palabra aparece en "Mis palabras".
- [ ] Repetir la misma palabra responde al instante (caché local).

| Paso | OK / FALLO | Nota (qué pasó, tiempo medido) |
|:---|:---:|:---|
| | | |

## 2. Aviso de Windows SmartScreen
Al abrir el `.exe` por primera vez Windows puede mostrar **"Windows protegió su PC"**. Pasa porque el `.exe` **no está firmado** con un certificado de pago; no significa que tenga un virus. Para abrirlo:

1. Pulsa **Más información**.
2. Pulsa **Ejecutar de todas formas**.

Solo se pregunta la primera vez. Menciona esto en las notas del Release. Cualquiera puede comprobar que el zip es el tuyo comparando el SHA256.

## 3. Crear el Release v1.0.0 en GitHub
Antes: haz tú el *commit* de los cambios y `git push origin main`.

### Desde la web
1. Abre https://github.com/SoFzzz/ClearRead/releases y pulsa **Draft a new release**.
2. En **Choose a tag** escribe `v1.0.0` y elige **Create new tag on publish**.
3. Título: `ClearRead v1.0.0`. En la descripción pon qué hace la app, el aviso de SmartScreen y el SHA256.
4. Arrastra `dist\ClearRead-v1.0.0-win64.zip` a la zona **Attach binaries**.
5. Pulsa **Publish release**.

### Con `gh`
```powershell
gh auth status
gh release create v1.0.0 dist\ClearRead-v1.0.0-win64.zip --title "ClearRead v1.0.0" --notes "Windows 10/11 x64. Descomprime y abre ClearRead.exe. Si SmartScreen avisa: Más información, Ejecutar de todas formas (el .exe no está firmado). SHA256: PEGA_AQUI_EL_HASH"
```
Si `gh auth status` falla, ejecuta `gh auth login` primero.
