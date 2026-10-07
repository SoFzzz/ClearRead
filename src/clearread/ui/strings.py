"""User-visible text catalog (I18N-F01). No Qt dependency.

Keys are English dotted names; every key carries both "es" and "en".
Logic modules never contain visible text: they pass keys (or enum names) here.
"""

from enum import Enum


class Language(str, Enum):
    ES = "es"
    EN = "en"


DEFAULT_LANGUAGE = Language.ES


class MissingStringError(KeyError):
    """Raised when a key is not in the catalog."""


CATALOG: dict[str, dict[str, str]] = {
    # --- Shared ---
    "common.cancel": {"es": "Cancelar", "en": "Cancel"},
    "common.understood": {"es": "Entendido", "en": "Got it"},
    "common.not_now": {"es": "Ahora no", "en": "Not now"},
    "common.retry": {"es": "Reintentar", "en": "Try again"},
    # --- Navigation ---
    "nav.settings": {"es": "Ajustes", "en": "Settings"},
    "nav.back_home": {"es": "← Inicio", "en": "← Home"},
    "nav.back": {"es": "← Volver", "en": "← Back"},
    "nav.assistant": {"es": "Asistente", "en": "Assistant"},
    # --- Home ---
    "home.title": {
        "es": "Abre un documento para empezar",
        "en": "Open a document to start",
    },
    "home.drop_title": {
        "es": "Arrastra aquí tu PDF o tu foto",
        "en": "Drag your PDF or photo here",
    },
    "home.choose_file": {"es": "Elegir archivo", "en": "Choose file"},
    "home.recent_title": {"es": "Documentos recientes", "en": "Recent documents"},
    "home.recent_open": {"es": "Abrir", "en": "Open"},
    "home.recent_remove": {"es": "Quitar de recientes", "en": "Remove from recent"},
    "home.formats_hint": {
        "es": "Sirven archivos PDF, JPG, PNG, BMP y TIFF",
        "en": "PDF, JPG, PNG, BMP and TIFF files work",
    },
    "home.file_dialog_title": {
        "es": "Elegir un documento",
        "en": "Choose a document",
    },
    "home.file_filter": {
        "es": "Documentos y fotos ({patterns})",
        "en": "Documents and photos ({patterns})",
    },
    "home.recent_pdf": {
        "es": "PDF · {pages} · {opened}",
        "en": "PDF · {pages} · {opened}",
    },
    "home.recent_photo": {
        "es": "Foto · {pages} · {opened}",
        "en": "Photo · {pages} · {opened}",
    },
    "home.pages_one": {"es": "1 página", "en": "1 page"},
    "home.pages_other": {"es": "{count} páginas", "en": "{count} pages"},
    "home.opened_today": {"es": "Abierto hoy", "en": "Opened today"},
    "home.opened_yesterday": {"es": "Abierto ayer", "en": "Opened yesterday"},
    "home.opened_on": {
        "es": "Abierto el {day} de {month}",
        "en": "Opened on {month} {day}",
    },
    "home.recent_open_named": {"es": "Abrir {name}", "en": "Open {name}"},
    "home.recent_remove_named": {
        "es": "Quitar {name} de recientes",
        "en": "Remove {name} from recent",
    },
    "month.1": {"es": "enero", "en": "January"},
    "month.2": {"es": "febrero", "en": "February"},
    "month.3": {"es": "marzo", "en": "March"},
    "month.4": {"es": "abril", "en": "April"},
    "month.5": {"es": "mayo", "en": "May"},
    "month.6": {"es": "junio", "en": "June"},
    "month.7": {"es": "julio", "en": "July"},
    "month.8": {"es": "agosto", "en": "August"},
    "month.9": {"es": "septiembre", "en": "September"},
    "month.10": {"es": "octubre", "en": "October"},
    "month.11": {"es": "noviembre", "en": "November"},
    "month.12": {"es": "diciembre", "en": "December"},
    # --- Processing ---
    "processing.preparing": {
        "es": "Separando en sílabas y preparando la lectura",
        "en": "Splitting into syllables and preparing the reading",
    },
    "processing.note": {
        "es": "Puede tardar un poco si el documento tiene muchas páginas. "
        "Tu archivo no sale de este equipo.",
        "en": "It can take a while if the document has many pages. "
        "Your file never leaves this computer.",
    },
    "processing.percent": {"es": "{percent} %", "en": "{percent}%"},
    "processing.title": {
        "es": "Preparando tu documento",
        "en": "Getting your document ready",
    },
    "processing.reading_page": {
        "es": "Leyendo la página {current} de {total}",
        "en": "Reading page {current} of {total}",
    },
    # --- Reading ---
    "reading.play": {"es": "Reproducir", "en": "Play"},
    "reading.pause": {"es": "Pausar", "en": "Pause"},
    "reading.resume": {"es": "Reanudar", "en": "Resume"},
    "reading.stop": {"es": "Detener", "en": "Stop"},
    "reading.speed": {"es": "Velocidad", "en": "Speed"},
    "reading.speed_value": {"es": "{wpm} palabras/min", "en": "{wpm} words/min"},
    "reading.word_counter": {
        "es": "Palabra {current} de {total}",
        "en": "Word {current} of {total}",
    },
    "reading.tooltip": {"es": "{action} ({shortcut})", "en": "{action} ({shortcut})"},
    "reading.key_space": {"es": "Espacio", "en": "Space"},
    "reading.key_esc": {"es": "Esc", "en": "Esc"},
    "reading.shortcuts": {
        "es": "Espacio: pausar · Esc: detener",
        "en": "Space: pause · Esc: stop",
    },
    "reading.error.tts_init": {
        "es": "No pudimos iniciar la voz. Revisa que Windows tenga una voz en español instalada.",
        "en": "We could not start the voice. Check that Windows has a Spanish voice installed.",
    },
    "reading.error.tts_playback": {
        "es": "La lectura en voz alta se detuvo. Prueba a reproducir de nuevo.",
        "en": "Reading aloud stopped. Try playing again.",
    },
    # --- Settings ---
    "settings.title": {"es": "Ajustes", "en": "Settings"},
    "settings.autosave_hint": {
        "es": "Los cambios se guardan solos y se ven al momento.",
        "en": "Changes are saved automatically and show up right away.",
    },
    "settings.section.theme": {"es": "Tema", "en": "Theme"},
    "settings.section.text": {"es": "Texto", "en": "Text"},
    "settings.section.voice": {"es": "Voz", "en": "Voice"},
    "settings.section.language": {"es": "Idioma", "en": "Language"},
    "settings.section.advanced": {"es": "Ajustes avanzados", "en": "Advanced settings"},
    "settings.theme.light": {"es": "Claro", "en": "Light"},
    "settings.theme.dark": {"es": "Oscuro", "en": "Dark"},
    "settings.theme.high_contrast": {"es": "Alto contraste", "en": "High contrast"},
    "settings.font_size": {"es": "Tamaño de letra", "en": "Text size"},
    "settings.line_spacing": {"es": "Espacio entre líneas", "en": "Line spacing"},
    "settings.letter_spacing": {"es": "Espacio entre letras", "en": "Letter spacing"},
    "settings.word_spacing": {"es": "Espacio entre palabras", "en": "Word spacing"},
    "settings.syllables": {"es": "Sílabas de colores", "en": "Colored syllables"},
    "settings.voice": {"es": "Voz", "en": "Voice"},
    "settings.preview_title": {"es": "Vista previa", "en": "Preview"},
    "settings.reset": {"es": "Restablecer valores", "en": "Reset to defaults"},
    "settings.language.label": {
        "es": "Idioma de la interfaz",
        "en": "Interface language",
    },
    # Language names are shown in their own language in both catalogs.
    "settings.language.es": {"es": "Español", "en": "Español"},
    "settings.language.en": {"es": "English", "en": "English"},
    "settings.language.restart_title": {
        "es": "Reinicia ClearRead para cambiar el idioma",
        "en": "Restart ClearRead to change the language",
    },
    "settings.language.restart_message": {
        "es": "El nuevo idioma se verá la próxima vez que abras ClearRead. "
        "Tus documentos no cambian.",
        "en": "The new language will show the next time you open ClearRead. "
        "Your documents stay the same.",
    },
    "settings.speed": {"es": "Velocidad de lectura", "en": "Reading speed"},
    "settings.value.points": {"es": "{value} puntos", "en": "{value} points"},
    "settings.value.px": {"es": "{value} px", "en": "{value} px"},
    "settings.on": {"es": "Sí", "en": "Yes"},
    "settings.off": {"es": "No", "en": "No"},
    "settings.no_voices": {
        "es": "No hay voces instaladas",
        "en": "No voices are installed",
    },
    "settings.preview_sample": {
        "es": "La fotosíntesis es el proceso que usan las plantas para vivir.",
        "en": "Photosynthesis is the way that plants make their food.",
    },
    "settings.preview_caption": {
        "es": "Así se verá tu lectura: sílabas de dos colores, la palabra que suena "
        "resaltada y la línea actual marcada.",
        "en": "This is how your reading will look: syllables in two colors, "
        "the word being read highlighted and the current line marked.",
    },
    "settings.save_failed": {
        "es": "No se pudieron guardar los ajustes. Valen hasta que cierres ClearRead.",
        "en": "Your settings could not be saved. They last until you close ClearRead.",
    },
    "settings.backend_url_invalid": {
        "es": "La dirección debe empezar por https",
        "en": "The address must start with https",
    },
    "settings.privacy.title": {"es": "Tu privacidad", "en": "Your privacy"},
    "settings.privacy.assistant": {
        "es": "El asistente solo recibe el texto que seleccionas. "
        "El resto del documento no sale de tu equipo.",
        "en": "The assistant only receives the text you select. "
        "The rest of the document never leaves your computer.",
    },
    "settings.privacy.cache": {
        "es": "Para abrir más rápido tus documentos recientes, ClearRead guarda su "
        "texto en tu equipo, en {path}.",
        "en": "To open your recent documents faster, ClearRead keeps their text on "
        "your computer, in {path}.",
    },
    "settings.clear_recents": {
        "es": "Borrar documentos recientes",
        "en": "Delete recent documents",
    },
    "settings.clear_confirm.title": {
        "es": "¿Borrar los documentos recientes?",
        "en": "Delete your recent documents?",
    },
    "settings.clear_confirm.message": {
        "es": "Se borrará el texto guardado de todos tus documentos recientes. "
        "Tus archivos originales no cambian.",
        "en": "The saved text of all your recent documents will be deleted. "
        "Your original files stay the same.",
    },
    "settings.clear_confirm.yes": {"es": "Sí, borrar", "en": "Yes, delete"},
    "settings.recents_cleared": {
        "es": "Documentos recientes borrados.",
        "en": "Recent documents deleted.",
    },
    "settings.backend_url": {
        "es": "Dirección del asistente",
        "en": "Assistant address",
    },
    "settings.backend_url_reset": {
        "es": "Usar la dirección original",
        "en": "Use the original address",
    },
    "settings.backend_url_help": {
        "es": "Solo cámbiala si te lo pide quien mantiene ClearRead.",
        "en": "Only change it if the person who maintains ClearRead asks you to.",
    },
    # --- Error dialog ---
    "dialog.window_title": {"es": "ClearRead", "en": "ClearRead"},
    "dialog.what_you_can_do": {"es": "Qué puedes hacer", "en": "What you can do"},
    "dialog.choose_other": {"es": "Elegir otro archivo", "en": "Choose another file"},
    # --- Ingestion errors (title / message / what you can do) ---
    "error.password.title": {
        "es": "No pudimos abrir este documento",
        "en": "We couldn't open this document",
    },
    "error.password.message": {
        "es": "El PDF tiene contraseña y ClearRead no puede leerlo así.",
        "en": "This PDF has a password, so ClearRead can't read it as it is.",
    },
    "error.password.action": {
        "es": "Guarda una copia del PDF sin contraseña y ábrela otra vez.",
        "en": "Save a copy of the PDF without a password and open it again.",
    },
    "error.unsupported_format.title": {
        "es": "Este archivo no sirve",
        "en": "This file doesn't work",
    },
    "error.unsupported_format.message": {
        "es": "ClearRead abre documentos PDF y fotos JPG, PNG, BMP o TIFF.",
        "en": "ClearRead opens PDF documents and JPG, PNG, BMP or TIFF photos.",
    },
    "error.unsupported_format.action": {
        "es": "Elige un archivo de uno de esos tipos.",
        "en": "Choose a file of one of those types.",
    },
    "error.file_not_found.title": {
        "es": "No encontramos el archivo",
        "en": "We couldn't find the file",
    },
    "error.file_not_found.message": {
        "es": "Puede que lo hayan movido o borrado.",
        "en": "It may have been moved or deleted.",
    },
    "error.file_not_found.action": {
        "es": "Elige el archivo otra vez desde su carpeta.",
        "en": "Choose the file again from its folder.",
    },
    "error.no_text.title": {
        "es": "No encontramos palabras",
        "en": "We couldn't find any words",
    },
    "error.no_text.message": {
        "es": "No logramos leer texto en este documento.",
        "en": "We couldn't read any text in this document.",
    },
    "error.no_text.action": {
        "es": "Prueba con una foto más nítida, con buena luz y sin sombras.",
        "en": "Try a sharper photo, with good light and no shadows.",
    },
    "error.unreadable.title": {
        "es": "No pudimos abrir el archivo",
        "en": "We couldn't open the file",
    },
    "error.unreadable.message": {
        "es": "Puede estar dañado o abierto en otro programa.",
        "en": "It may be damaged or open in another program.",
    },
    "error.unreadable.action": {
        "es": "Cierra el otro programa o prueba con otra copia del archivo.",
        "en": "Close the other program or try another copy of the file.",
    },
    # --- AI assistant panel ---
    "ai.explain_word": {"es": "Explicar palabra", "en": "Explain word"},
    "ai.simplify_paragraph": {"es": "Simplificar párrafo", "en": "Simplify paragraph"},
    "ai.menu_explain": {"es": "Explicar esta palabra", "en": "Explain this word"},
    "ai.menu_simplify": {
        "es": "Simplificar este párrafo",
        "en": "Simplify this paragraph",
    },
    "ai.loading": {
        "es": "Buscando una explicación…",
        "en": "Looking for an explanation…",
    },
    "ai.loading_hint": {
        "es": "Suele tardar unos segundos.",
        "en": "This usually takes a few seconds.",
    },
    "ai.waking.title": {
        "es": "Despertando el asistente…",
        "en": "Waking up the assistant…",
    },
    "ai.waking.detail": {
        "es": "Estaba descansando porque nadie lo usó en un rato. Puede tardar hasta un "
        "minuto; puedes seguir leyendo mientras tanto.",
        "en": "It was resting because nobody used it for a while. It can take up to a "
        "minute; you can keep reading in the meantime.",
    },
    "ai.answer_footer": {
        "es": "Respuesta creada con IA. Puede tener errores.",
        "en": "Answer created with AI. It may contain mistakes.",
    },
    "ai.session_counter": {
        "es": "Consultas en esta sesión: {used} de {limit}",
        "en": "Questions this session: {used} of {limit}",
    },
    "ai.offline_tooltip": {
        "es": "El asistente necesita internet. Lo demás funciona igual.",
        "en": "The assistant needs internet. Everything else works the same.",
    },
    "ai.offline_badge": {"es": "Sin internet", "en": "No internet"},
    # --- AIErrorKind -> message (key: ai.error.<kind name in lowercase>) ---
    "ai.error.no_network": {
        "es": "No pudimos conectar con el asistente. Verifica tu conexión a internet.",
        "en": "We couldn't reach the assistant. Check your internet connection.",
    },
    "ai.error.server_waking": {
        "es": "El asistente está tardando en despertar. Inténtalo de nuevo en un minuto.",
        "en": "The assistant is taking a while to wake up. Try again in a minute.",
    },
    "ai.error.timeout": {
        "es": "El asistente tardó demasiado en responder. Inténtalo de nuevo.",
        "en": "The assistant took too long to answer. Try again.",
    },
    "ai.error.session_limit": {
        "es": "Alcanzaste el máximo de consultas de IA para esta sesión.",
        "en": "You reached the maximum number of AI questions for this session.",
    },
    "ai.error.daily_limit": {
        "es": "El asistente alcanzó su límite de hoy. Vuelve a intentarlo mañana.",
        "en": "The assistant reached its limit for today. Try again tomorrow.",
    },
    "ai.error.input_too_long": {
        "es": "El texto seleccionado es demasiado largo. Selecciona un fragmento más corto.",
        "en": "The selected text is too long. Select a shorter piece.",
    },
    "ai.error.service_unavailable": {
        "es": "El asistente no está disponible en este momento.",
        "en": "The assistant is not available right now.",
    },
    "ai.error.bad_response": {
        "es": "No pudimos entender la respuesta del asistente.",
        "en": "We couldn't understand the assistant's answer.",
    },
    "ai.hint.no_network": {
        "es": "Lo demás de ClearRead sigue funcionando sin internet.",
        "en": "Everything else in ClearRead keeps working without internet.",
    },
    "ai.hint.session_limit": {
        "es": "Cierra y vuelve a abrir ClearRead para empezar una sesión nueva.",
        "en": "Close and reopen ClearRead to start a new session.",
    },
    "ai.hint.service_unavailable": {
        "es": "Inténtalo más tarde.",
        "en": "Try again later.",
    },
    "ai.hint.bad_response": {"es": "Inténtalo de nuevo.", "en": "Try again."},
    "ai.hint.input_too_long": {
        "es": "Elige un párrafo más corto o selecciona solo una parte.",
        "en": "Choose a shorter paragraph or select just a part of it.",
    },
    "ai.empty.title": {
        "es": "Pregúntale al asistente",
        "en": "Ask the assistant",
    },
    "ai.empty.body": {
        "es": "Haz clic derecho sobre una palabra para que te la explique, o sobre un "
        "párrafo para que lo simplifique.",
        "en": "Right-click a word to get it explained, or a paragraph to get it "
        "simplified.",
    },
    "ai.empty.shortcut": {
        "es": "Ctrl+I abre y cierra este panel.",
        "en": "Ctrl+I opens and closes this panel.",
    },
    "ai.chosen": {"es": "Elegiste", "en": "You chose"},
    "ai.answer_title_word": {"es": "Qué significa", "en": "What it means"},
    "ai.answer_title_paragraph": {
        "es": "El párrafo, más simple",
        "en": "The paragraph, simpler",
    },
    "ai.listen": {"es": "Escuchar respuesta", "en": "Listen to the answer"},
    "ai.listen_stop": {"es": "Dejar de escuchar", "en": "Stop listening"},
    "ai.close": {"es": "Cerrar el asistente", "en": "Close the assistant"},
    "ai.toggle_tooltip": {
        "es": "Asistente (Ctrl+I)",
        "en": "Assistant (Ctrl+I)",
    },
    "ai.offline_title": {
        "es": "El asistente está apagado",
        "en": "The assistant is off",
    },
    # --- Privacy notice (NFR-SEC01) ---
    "privacy.title": {
        "es": "Antes de usar el asistente",
        "en": "Before you use the assistant",
    },
    "privacy.body": {
        "es": "Para ayudarte, enviamos por internet la palabra o el párrafo que elijas. "
        "El resto de tu documento se queda en tu equipo.",
        "en": "To help you, we send the word or paragraph you choose over the internet. "
        "The rest of your document stays on your computer.",
    },
    "privacy.destination": {
        "es": "El texto viaja al servidor de ClearRead, que lo pasa a DeepSeek, un "
        "servicio de inteligencia artificial. Puede equivocarse.",
        "en": "The text travels to the ClearRead server, which passes it to DeepSeek, "
        "an artificial intelligence service. It can make mistakes.",
    },
    "privacy.footer": {
        "es": "Solo enviamos a internet la palabra o el párrafo que elegiste. "
        "El resto del documento no sale de tu equipo.",
        "en": "We only send the word or paragraph you chose over the internet. "
        "The rest of the document never leaves your computer.",
    },
}


def tr(key: str, lang: Language | str, **params: object) -> str:
    """Return the text for ``key`` in ``lang``, filling ``{params}``."""
    entry = CATALOG.get(key)
    if entry is None:
        raise MissingStringError(f"Unknown string key: {key!r}")
    return entry[Language(lang).value].format(**params)
