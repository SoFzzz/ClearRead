# Cómo desplegar el backend de ClearRead en Render

Esta guía es para alguien que **nunca usó Render**. El backend es la carpeta `backend/` del repositorio; Render lo ejecuta en internet para que `ClearRead.exe` pueda pedirle ayuda a la IA sin llevar la clave de DeepSeek dentro.

Fuentes oficiales de Render consultadas el **2026-10-07**: https://render.com/docs/blueprint-spec, https://render.com/docs/python-version, https://render.com/docs/free, https://render.com/docs/health-checks.

> [!IMPORTANT]
> Nunca subas `backend/.env` a GitHub ni pegues la clave de DeepSeek en un chat o en un archivo del repositorio. El archivo ya está ignorado por git; el paso 1 te enseña a comprobarlo.

## Qué necesitas antes
- Una cuenta en https://render.com (puedes entrar con tu cuenta de GitHub).
- El archivo `backend/.env` en tu computadora, con `DEEPSEEK_API_KEY` y `CLIENT_TOKEN` ya escritos.

## 1. Subir el repositorio a GitHub
El remoto `origin` ya existe (`SoFzzz/ClearRead`). En PowerShell, dentro de la carpeta del proyecto:

```powershell
git check-ignore backend/.env
git status --short
git add render.yaml docs/deploy.md backend src tests document.md
git commit -m "chore: deploy files"
git push origin main
```

- La primera orden debe imprimir `backend/.env`: eso confirma que git lo ignora. Si no imprime nada, **para** y avisa.
- Ajusta la lista de `git add` a lo que quieras subir; lo importante es que `backend/.env` no aparezca en `git status`.

## 2. Crear el servicio en Render
La forma más fácil es usar el archivo `render.yaml` que ya está en el repositorio (se llama *Blueprint*):

1. Entra a https://dashboard.render.com.
2. Pulsa **New +** → **Blueprint**.
3. Si te lo pide, pulsa **Connect GitHub** y autoriza a Render a leer el repositorio `ClearRead`.
4. Elige el repositorio y la rama `main`. Render lee `render.yaml` y muestra un servicio llamado **clearread-api** (plan **Free**).
5. Render te pedirá los valores de las variables secretas (paso siguiente). Después pulsa **Apply** o **Deploy Blueprint**.

Si prefieres hacerlo a mano en vez de con el Blueprint: **New +** → **Web Service** → tu repositorio, y escribe estos ajustes:

| Ajuste | Valor |
|:---|:---|
| Language | Python 3 |
| Root Directory | `backend` |
| Build Command | `pip install .` |
| Start Command | `uvicorn clearread_backend.main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | Free |
| Health Check Path (en Settings) | `/health` |

## 3. Cargar las variables de entorno
Las variables son los «ajustes secretos» del servicio. Se escriben en el panel de Render, **no** en el repositorio.

Con el Blueprint, Render te muestra los campos al crearlo. A mano: servicio → **Environment** → **Add Environment Variable**.

| Variable | Qué poner |
|:---|:---|
| `DEEPSEEK_API_KEY` | Cópiala de `backend/.env` (línea `DEEPSEEK_API_KEY=`), solo lo que va después del `=` |
| `CLIENT_TOKEN` | Cópialo de `backend/.env` (línea `CLIENT_TOKEN=`), solo lo que va después del `=` |
| `DEEPSEEK_MODEL` | `deepseek-flash` |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` |
| `DAILY_CALL_LIMIT` | `45` |
| `PYTHON_VERSION` | `3.11.9` (el Blueprint ya la trae; si creas el servicio a mano, agrégala) |

Cuida que no queden espacios ni comillas alrededor de los valores.

Guarda también el `CLIENT_TOKEN` para tu computadora: la app lo leerá de la variable de entorno `CLEARREAD_CLIENT_TOKEN` (desarrollo) o del archivo que genere el build del `.exe`.

## 4. Obtener la URL pública
1. Espera a que el estado del servicio diga **Live** (la primera vez tarda unos minutos; puedes ver el avance en la pestaña **Logs**).
2. Arriba, bajo el nombre del servicio, aparece la dirección: `https://clearread-api-xxxx.onrender.com`. Esa es tu URL pública.
3. Comprueba que funciona abriendo `https://<tu-url>/health` en el navegador: debe mostrar `{"status":"ok"}`. También puedes abrir `https://<tu-url>/docs`.
4. Pásale la URL a Claude para poner el valor en `DEFAULT_BACKEND_URL` (`src/clearread/core/config.py`) y hacer la prueba real contra Render (Día 10).

**Plan gratuito:** si nadie lo usa durante 15 minutos, Render *duerme* el servicio y tarda alrededor de 1 minuto en despertar con la siguiente petición. Por eso la app muestra «Despertando el asistente…». Además, el contador diario y la caché viven en memoria y se borran cuando el servicio duerme; el límite de gasto real es el saldo prepagado de DeepSeek.

## 5. Si el build falla
Abre el servicio → **Events** (para ver qué falló) y **Logs** (el texto del error).

| Síntoma en los logs | Qué hacer |
|:---|:---|
| `No such file or directory: 'backend'` o no encuentra `pyproject.toml` | **Root Directory** debe ser exactamente `backend` (sin barra inicial). |
| `Could not find a version that satisfies the requirement` o errores de compilación de paquetes | Comprueba que `PYTHON_VERSION` sea `3.11.9`. Con la versión por defecto de Render (más nueva) algunos paquetes no tienen instalador. |
| `ModuleNotFoundError: clearread_backend` al arrancar | El *Build Command* debe ser `pip install .` y el *Start Command* debe empezar con `uvicorn clearread_backend.main:app`. |
| `Port scan timeout` o el deploy no pasa a *Live* | El *Start Command* debe incluir `--host 0.0.0.0 --port $PORT`. |
| El health check falla | **Health Check Path** debe ser `/health` y debe responder en menos de 5 s. |
| Todas las peticiones de la app dan error 401 | `CLIENT_TOKEN` en Render no coincide con el de `backend/.env` (revisa espacios o comillas). |
| Respuestas 502 `upstream_auth_failed` / `upstream_no_balance` | `DEEPSEEK_API_KEY` incorrecta (401) o saldo de DeepSeek agotado (402). |

Después de corregir un ajuste o una variable, pulsa **Manual Deploy** → **Deploy latest commit** (cambiar una variable de entorno también redespliega por sí solo).
Si sigue fallando, copia las últimas líneas de **Logs** (sin claves) y pásaselas a Claude.
