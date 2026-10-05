# Modelos OCR locales

Modelos ONNX que viajan dentro del `.exe` (§2.2, §6.3). **El código de la app nunca los descarga**: se descargan una sola vez como tarea de desarrollo y se versionan aquí.

## latin_PP-OCRv5_rec_mobile (reconocimiento, alfabeto latino)

| Campo | Valor |
|:---|:---|
| Archivo | `latin_PP-OCRv5_rec_mobile.onnx` (7 904 513 bytes) |
| SHA256 | `b20bd37c168a570f583afbc8cd7925603890efbcdc000a59e22c269d160b5f5a` |
| Origen | https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv5/rec/latin_PP-OCRv5_rec_mobile.onnx |
| Diccionario | `ppocrv5_latin_dict.txt` (1 634 bytes, 502 caracteres) |
| Origen del diccionario | https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/paddle/PP-OCRv5/rec/latin_PP-OCRv5_rec_mobile/ppocrv5_latin_dict.txt |
| Modelo original | PaddlePaddle `latin_PP-OCRv5_mobile_rec` — https://huggingface.co/PaddlePaddle/latin_PP-OCRv5_mobile_rec (licencia `apache-2.0`) |
| Licencia | Apache License 2.0 (repositorio de modelos RapidAI/RapidOCR en ModelScope y modelo original de PaddlePaddle) |
| Descargado | 2026-10-01; SHA256 verificado contra el registro `default_models.yaml` de `rapidocr` 3.9.2 |

- El mismo diccionario va **embebido** en los metadatos del `.onnx` (clave `character`) y es idéntico al `.txt`. La salida del modelo tiene 504 clases: 502 caracteres + *blank* + espacio.
- Contiene `ñ Ñ ¿ ¡ á é í ó ú ü` (comprobado leyendo el diccionario).
- Compatible con `rapidocr-onnxruntime` 1.4.4: `RapidOCR(rec_model_path=...)`. La detección y la clasificación de ángulo siguen siendo las del paquete (`ch_PP-OCRv4_det`, `ch_ppocr_mobile_v2.0_cls`).

## Evaluados y descartados

| Modelo | Motivo |
|:---|:---|
| `ch_PP-OCRv4_rec` (incluido en `rapidocr-onnxruntime`) | A su diccionario le faltan `ñ Ñ ¿ ¡`; 1/21 caracteres especiales en la muestra sintética |
| `latin_PP-OCRv3_rec_mobile` (mismo repositorio, SHA256 `e9d7a336…71cf`) | A su diccionario le falta `Ñ`; 8/21 (300 DPI) y 9/21 (200 DPI) caracteres especiales |

Medición: `tests/spike_ocr_latin.py`.
