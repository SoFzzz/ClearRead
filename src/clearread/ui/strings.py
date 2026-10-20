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
    "nav.my_words": {"es": "Mis palabras", "en": "My words"},
    # --- Home ---
    "home.dashboard_title": {
        "es": "Tu espacio de lectura",
        "en": "Your reading space",
    },
    "home.continue_title": {"es": "Continuar leyendo", "en": "Continue reading"},
    "home.continue_button": {"es": "Continuar", "en": "Continue"},
    "home.progress": {"es": "{percent} % leído", "en": "{percent}% read"},
    "home.try_sample": {"es": "Probar con un ejemplo", "en": "Try an example"},
    "home.sample_title": {
        "es": "Ejemplo: la fotosíntesis",
        "en": "Example: photosynthesis",
    },
    "home.stats.words": {"es": "Palabras leídas", "en": "Words read"},
    "home.stats.time": {"es": "Tiempo de lectura", "en": "Reading time"},
    "home.stats.documents": {"es": "Documentos", "en": "Documents"},
    "home.stats.minutes": {"es": "{minutes} min", "en": "{minutes} min"},
    "home.stats.hours": {
        "es": "{hours} h {minutes} min",
        "en": "{hours} h {minutes} min",
    },
    "home.stats.hint": {
        "es": "Estas cifras se calculan en tu equipo y no se envían a ningún sitio.",
        "en": "These numbers are worked out on your computer and never sent anywhere.",
    },
    "home.empty.title": {
        "es": "Te damos la bienvenida a ClearRead",
        "en": "Welcome to ClearRead",
    },
    "home.empty.body": {
        "es": "Arrastra un PDF o una foto, o prueba primero con un ejemplo. "
        "Todo se queda en tu equipo.",
        "en": "Drag in a PDF or a photo, or start with an example. "
        "Everything stays on your computer.",
    },
    "home.drop_title": {
        "es": "Arrastra aquí tu PDF o tu foto",
        "en": "Drag your PDF or photo here",
    },
    "home.choose_file": {"es": "Elegir archivo", "en": "Choose file"},
    "home.library_title": {"es": "Mi biblioteca", "en": "My library"},
    "home.recent_open": {"es": "Abrir", "en": "Open"},
    "home.recent_remove": {
        "es": "Quitar de la biblioteca",
        "en": "Remove from library",
    },
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
    "home.recent_text": {
        "es": "Texto · {pages} · {opened}",
        "en": "Text · {pages} · {opened}",
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
        "es": "Quitar {name} de la biblioteca",
        "en": "Remove {name} from the library",
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
    "reading.key_f": {"es": "F", "en": "F"},
    "reading.focus": {"es": "Modo foco", "en": "Focus mode"},
    "reading.key_s": {"es": "S", "en": "S"},
    "reading.syllables": {"es": "Sílabas", "en": "Syllables"},
    "reading.resume_title": {
        "es": "Seguir desde donde lo dejaste",
        "en": "Pick up where you left off",
    },
    "reading.resume_detail": {
        "es": "Estabas en la palabra {current} de {total}.",
        "en": "You were at word {current} of {total}.",
    },
    "reading.resume_continue": {"es": "Seguir", "en": "Continue"},
    "reading.resume_restart": {"es": "Empezar de nuevo", "en": "Start over"},
    "reading.prev_short": {"es": "Anterior", "en": "Previous"},
    "reading.next_short": {"es": "Siguiente", "en": "Next"},
    "reading.page_label": {"es": "Página {number}", "en": "Page {number}"},
    "reading.page_of": {"es": "de {total}", "en": "of {total}"},
    "reading.page_field": {"es": "Número de página", "en": "Page number"},
    "reading.page_prev": {"es": "Página anterior", "en": "Previous page"},
    "reading.page_next": {"es": "Página siguiente", "en": "Next page"},
    "reading.key_page_prev": {"es": "Ctrl+Izquierda", "en": "Ctrl+Left"},
    "reading.key_page_next": {"es": "Ctrl+Derecha", "en": "Ctrl+Right"},
    "reading.mode_continuous": {"es": "Continua", "en": "Continuous"},
    "reading.mode_paged": {"es": "Por páginas", "en": "By page"},
    "reading.mode_tooltip": {
        "es": "Ver todo el documento seguido o una página a la vez",
        "en": "See the whole document in a row or one page at a time",
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
    "settings.theme.light": {"es": "Claro", "en": "Light"},
    "settings.theme.dark": {"es": "Oscuro", "en": "Dark"},
    "settings.font": {"es": "Fuente de lectura", "en": "Reading font"},
    "settings.font.lexend": {
        "es": "Lexend (recomendada)",
        "en": "Lexend (recommended)",
    },
    "settings.font.atkinson": {
        "es": "Atkinson Hyperlegible",
        "en": "Atkinson Hyperlegible",
    },
    "settings.font.opendyslexic": {"es": "OpenDyslexic", "en": "OpenDyslexic"},
    "settings.font_note": {
        "es": "Ninguna fuente funciona igual para todas las personas: "
        "elige la que te resulte más cómoda.",
        "en": "No font works the same for everyone: choose the one that feels "
        "most comfortable.",
    },
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
    "settings.language.confirm_title": {
        "es": "¿Cambiar el idioma?",
        "en": "Change the language?",
    },
    "settings.language.confirm_message": {
        "es": "ClearRead se reiniciará para usar el nuevo idioma. "
        "Tu lugar en la lectura se guarda y tus documentos no cambian.",
        "en": "ClearRead will restart to use the new language. "
        "Your place in the reading is saved and your documents stay the same.",
    },
    "settings.language.confirm_restart": {
        "es": "Reiniciar ahora",
        "en": "Restart now",
    },
    "settings.speed": {"es": "Velocidad de lectura", "en": "Reading speed"},
    "settings.value.points": {"es": "{value} puntos", "en": "{value} points"},
    "settings.value.em": {"es": "{value} em", "en": "{value} em"},
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
    # --- My words (glossary) ---
    "words.title": {"es": "Mis palabras", "en": "My words"},
    "words.search_placeholder": {
        "es": "Buscar una palabra",
        "en": "Search for a word",
    },
    "words.count_one": {"es": "1 palabra guardada", "en": "1 saved word"},
    "words.count_other": {
        "es": "{count} palabras guardadas",
        "en": "{count} saved words",
    },
    "words.listen": {"es": "Escuchar", "en": "Listen"},
    "words.listen_named": {"es": "Escuchar {word}", "en": "Listen to {word}"},
    "words.delete": {"es": "Borrar", "en": "Delete"},
    "words.delete_named": {"es": "Borrar {word}", "en": "Delete {word}"},
    "words.empty_title": {
        "es": "Aún no hay palabras guardadas",
        "en": "No saved words yet",
    },
    "words.empty_body": {
        "es": "Cuando el asistente te explique una palabra, la guardamos aquí para "
        "que puedas repasarla. Todo queda en tu equipo.",
        "en": "When the assistant explains a word to you, we keep it here so you can "
        "go over it again. Everything stays on your computer.",
    },
    "words.no_results": {
        "es": "No encontramos esa palabra.",
        "en": "We couldn't find that word.",
    },
    "words.date": {"es": "{day} de {month}", "en": "{month} {day}"},
    "words.meta": {"es": "{document} · {date}", "en": "{document} · {date}"},
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
    "ai.saved_to_words": {
        "es": "Guardada en Mis palabras.",
        "en": "Saved in My words.",
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
    # --- Library folders and glossary topics ---
    "group.chip": {"es": "{name} ({count})", "en": "{name} ({count})"},
    "group.name_hint": {
        "es": "Escribe un nombre corto",
        "en": "Type a short name",
    },
    "group.error.empty": {
        "es": "Escribe un nombre.",
        "en": "Please type a name.",
    },
    "group.error.duplicate": {
        "es": "Ya existe uno con ese nombre. Prueba con otro.",
        "en": "That name is already used. Try another one.",
    },
    "group.error.too_many": {
        "es": "Ya tienes muchos. Borra alguno para crear uno nuevo.",
        "en": "You already have a lot. Delete one to make a new one.",
    },
    "common.create": {"es": "Crear", "en": "Create"},
    "common.save": {"es": "Guardar", "en": "Save"},
    "folder.label": {"es": "Carpetas", "en": "Folders"},
    "folder.all": {"es": "Todos", "en": "All"},
    "folder.none": {"es": "Sin carpeta", "en": "No folder"},
    "folder.add": {"es": "+ Nueva carpeta", "en": "+ New folder"},
    "folder.rename": {"es": "Renombrar carpeta", "en": "Rename folder"},
    "folder.delete": {"es": "Borrar carpeta", "en": "Delete folder"},
    "folder.new_title": {"es": "Nueva carpeta", "en": "New folder"},
    "folder.rename_title": {"es": "Renombrar carpeta", "en": "Rename folder"},
    "folder.name_label": {"es": "Nombre de la carpeta", "en": "Folder name"},
    "folder.delete_title": {
        "es": "¿Borrar la carpeta «{name}»?",
        "en": 'Delete the folder "{name}"?',
    },
    "folder.delete_message": {
        "es": "Tus documentos no se borran: pasan a «Sin carpeta».",
        "en": 'Your documents are not deleted: they move to "No folder".',
    },
    "topic.label": {"es": "Temas", "en": "Topics"},
    "topic.all": {"es": "Todas", "en": "All"},
    "topic.none": {"es": "Sin tema", "en": "No topic"},
    "topic.add": {"es": "+ Nuevo tema", "en": "+ New topic"},
    "topic.rename": {"es": "Renombrar tema", "en": "Rename topic"},
    "topic.delete": {"es": "Borrar tema", "en": "Delete topic"},
    "topic.new_title": {"es": "Nuevo tema", "en": "New topic"},
    "topic.rename_title": {"es": "Renombrar tema", "en": "Rename topic"},
    "topic.name_label": {"es": "Nombre del tema", "en": "Topic name"},
    "topic.delete_title": {
        "es": "¿Borrar el tema «{name}»?",
        "en": 'Delete the topic "{name}"?',
    },
    "topic.delete_message": {
        "es": "Tus palabras no se borran: pasan a «Sin tema».",
        "en": 'Your words are not deleted: they move to "No topic".',
    },
    "home.search_placeholder": {
        "es": "Buscar un documento",
        "en": "Search for a document",
    },
    "home.search_no_results": {
        "es": "No encontramos documentos con ese nombre.",
        "en": "We couldn't find a document with that name.",
    },
    "home.folder_empty": {
        "es": "Aquí no hay documentos todavía. Elige o arrastra uno y se guardará aquí.",
        "en": "There are no documents here yet. Choose or drop one and it will be "
        "saved here.",
    },
    "home.save_to": {"es": "Guardar en:", "en": "Save in:"},
    "home.save_to_accessible": {
        "es": "Carpeta donde se guardará el documento",
        "en": "Folder where the document will be saved",
    },
    "home.save_to_tooltip": {
        "es": "Elige la carpeta de los documentos nuevos o crea una carpeta.",
        "en": "Choose the folder for new documents or create a new one.",
    },
    "home.drop_release_in": {
        "es": "Suelta para guardar en «{folder}»",
        "en": 'Drop to save in "{folder}"',
    },
    "home.drop_release_none": {
        "es": "Suelta para guardar sin carpeta",
        "en": "Drop to save without a folder",
    },
    "home.saved_status": {"es": "Estado del guardado", "en": "Save status"},
    "home.saved_in": {
        "es": "Guardado en «{folder}»",
        "en": 'Saved in "{folder}"',
    },
    "home.already_in": {
        "es": "Ya estaba en tu biblioteca, en «{folder}»",
        "en": 'Already in your library, in "{folder}"',
    },
    "home.meta_in_folder": {
        "es": "{meta} · {folder}",
        "en": "{meta} · {folder}",
    },
    "home.move_tooltip": {"es": "Mover a una carpeta", "en": "Move to a folder"},
    "home.move_named": {
        "es": "Mover {name} a una carpeta",
        "en": "Move {name} to a folder",
    },
    "home.remove_title": {
        "es": "¿Quitar «{name}» de la biblioteca?",
        "en": 'Remove "{name}" from the library?',
    },
    "home.remove_message": {
        "es": "Se borra la copia guardada en ClearRead. Tu archivo original no se toca.",
        "en": "The copy saved in ClearRead is deleted. Your original file is not "
        "touched.",
    },
    "home.remove_confirm": {"es": "Quitar", "en": "Remove"},
    "dialog.remove_from_library": {
        "es": "Quitar de la biblioteca",
        "en": "Remove from library",
    },
    "error.library_file_missing.title": {
        "es": "No encontramos el archivo",
        "en": "We can't find the file",
    },
    "error.library_file_missing.message": {
        "es": "El archivo original ya no está en su sitio y la copia guardada "
        "es de una versión anterior.",
        "en": "The original file is no longer where it was, and the saved copy "
        "is from an older version.",
    },
    "error.library_file_missing.action": {
        "es": "Si lo moviste, vuelve a abrirlo desde su nueva ubicación. "
        "O quítalo de la biblioteca.",
        "en": "If you moved it, open it again from its new place. "
        "Or remove it from the library.",
    },
    "words.topic_button": {"es": "Tema: {topic}", "en": "Topic: {topic}"},
    "words.topic_tooltip": {"es": "Cambiar el tema", "en": "Change the topic"},
    "words.topic_named": {
        "es": "Cambiar el tema de {word}",
        "en": "Change the topic of {word}",
    },
    "words.topic_empty": {
        "es": "No hay palabras en este tema.",
        "en": "There are no words in this topic.",
    },
    "words.delete_title": {
        "es": "¿Borrar la palabra «{word}»?",
        "en": 'Delete the word "{word}"?',
    },
    "words.delete_message": {
        "es": "Se quita de Mis palabras. Podrás guardarla otra vez pidiendo "
        "otra explicación.",
        "en": "It is removed from My words. You can save it again by asking for "
        "another explanation.",
    },
    # --- Accounts and synced profile (v1.6, §4.14.10) ---
    "auth.sign_in_title": {
        "es": "Entra a tu cuenta",
        "en": "Sign in to your account",
    },
    "auth.sign_in_intro": {
        "es": "Tu perfil guarda tus ajustes y tus palabras. Después de entrar, la app funciona también sin internet.",
        "en": "Your profile keeps your settings and your words. After you sign in, the app also works without internet.",
    },
    "auth.email_label": {
        "es": "Correo",
        "en": "Email",
    },
    "auth.password_label": {
        "es": "Contraseña",
        "en": "Password",
    },
    "auth.show_password": {
        "es": "Mostrar",
        "en": "Show",
    },
    "auth.hide_password": {
        "es": "Ocultar",
        "en": "Hide",
    },
    "auth.show_password_a11y": {
        "es": "Mostrar la contraseña",
        "en": "Show the password",
    },
    "auth.hide_password_a11y": {
        "es": "Ocultar la contraseña",
        "en": "Hide the password",
    },
    "auth.forgot_link": {
        "es": "¿Olvidaste tu contraseña?",
        "en": "Forgot your password?",
    },
    "auth.sign_in_button": {
        "es": "Entrar",
        "en": "Sign in",
    },
    "auth.signing_in": {
        "es": "Entrando…",
        "en": "Signing you in…",
    },
    "auth.no_account": {
        "es": "¿Todavía no tienes cuenta?",
        "en": "Don't have an account yet?",
    },
    "auth.create_account_link": {
        "es": "Crear cuenta",
        "en": "Create account",
    },
    "auth.need_internet": {
        "es": "Para entrar por primera vez en este equipo necesitas internet.",
        "en": "To sign in for the first time on this computer you need internet.",
    },
    "auth.waking": {
        "es": "Despertando el servidor. Puede tardar cerca de un minuto.",
        "en": "Waking up the server. It can take about a minute.",
    },
    "auth.register_title": {
        "es": "Crear cuenta",
        "en": "Create account",
    },
    "auth.name_label": {
        "es": "Nombre",
        "en": "Name",
    },
    "auth.password_count": {
        "es": "Usa al menos 8 caracteres. Llevas {count}.",
        "en": "Use at least 8 characters. You have {count}.",
    },
    "auth.privacy_consent": {
        "es": "He leído el aviso de privacidad: ClearRead guarda mi nombre, mi correo, mis ajustes y mis palabras. Mis documentos se quedan en este equipo.",
        "en": "I have read the privacy notice: ClearRead saves my name, my email, my settings and my words. My documents stay on this computer.",
    },
    "auth.privacy_link": {
        "es": "Leer el aviso de privacidad",
        "en": "Read the privacy notice",
    },
    "auth.register_button": {
        "es": "Crear cuenta",
        "en": "Create account",
    },
    "auth.creating": {
        "es": "Creando tu cuenta…",
        "en": "Creating your account…",
    },
    "auth.register_disabled_tip": {
        "es": "Acepta el aviso de privacidad para continuar",
        "en": "Accept the privacy notice to continue",
    },
    "auth.verify_note": {
        "es": "Te enviaremos un correo para confirmar que es tuyo. No hace falta confirmarlo para empezar.",
        "en": "We will send you an email to confirm it is yours. You do not need to confirm it to start.",
    },
    "auth.privacy_title": {
        "es": "Aviso de privacidad",
        "en": "Privacy notice",
    },
    "auth.privacy_body": {
        "es": "**Borrador, pendiente de revisión legal (§8).** ClearRead guarda en tu cuenta tu nombre, tu correo, tus ajustes y tus palabras guardadas, para que las tengas en cualquier equipo. Estos datos se guardan en servicios de Google (Firebase). Tus documentos, tu biblioteca y tus estadísticas se quedan solo en este equipo. Si usas el asistente, el texto que seleccionas se envía a nuestro servidor y a DeepSeek. Puedes borrar tu cuenta cuando quieras desde Ajustes.",
        "en": "**Draft, pending legal review (§8).** ClearRead saves your name, your email, your settings and your saved words in your account, so you have them on any computer. This data is stored in Google services (Firebase). Your documents, your library and your statistics stay only on this computer. If you use the assistant, the text you select is sent to our server and to DeepSeek. You can delete your account at any time from Settings.",
    },
    "auth.reset_title": {
        "es": "Recuperar contraseña",
        "en": "Reset password",
    },
    "auth.reset_step": {
        "es": "Paso {current} de {total}",
        "en": "Step {current} of {total}",
    },
    "auth.reset_heading": {
        "es": "¿Olvidaste tu contraseña?",
        "en": "Forgot your password?",
    },
    "auth.reset_intro": {
        "es": "Escribe tu correo. Te enviaremos un enlace para crear una contraseña nueva.",
        "en": "Type your email. We will send you a link to create a new password.",
    },
    "auth.reset_send": {
        "es": "Enviar enlace",
        "en": "Send link",
    },
    "auth.sending": {
        "es": "Enviando…",
        "en": "Sending…",
    },
    "auth.reset_done_title": {
        "es": "Revisa tu correo",
        "en": "Check your email",
    },
    "auth.reset_done_body": {
        "es": "Si {email} tiene una cuenta, te llegará un enlace en unos minutos.",
        "en": "If {email} has an account, a link will arrive in a few minutes.",
    },
    "auth.reset_step_1": {
        "es": "Abre el correo de ClearRead.",
        "en": "Open the email from ClearRead.",
    },
    "auth.reset_step_2": {
        "es": "Pulsa el enlace y escribe tu contraseña nueva.",
        "en": "Click the link and type your new password.",
    },
    "auth.reset_step_3": {
        "es": "Vuelve aquí y entra.",
        "en": "Come back here and sign in.",
    },
    "auth.reset_spam": {
        "es": "¿No llega? Mira en la carpeta de correo no deseado.",
        "en": "Not arriving? Check your spam folder.",
    },
    "auth.reset_resend": {
        "es": "Enviar otra vez",
        "en": "Send again",
    },
    "auth.reset_back": {
        "es": "Volver a entrar",
        "en": "Back to sign in",
    },
    "auth.validation.email_invalid": {
        "es": "Escribe un correo válido, por ejemplo nombre@correo.com.",
        "en": "Type a valid email, for example name@mail.com.",
    },
    "auth.validation.name_required": {
        "es": "Escribe tu nombre (hasta 40 caracteres).",
        "en": "Type your name (up to 40 characters).",
    },
    "auth.validation.password_too_long": {
        "es": "La contraseña puede tener hasta 128 caracteres.",
        "en": "The password can have up to 128 characters.",
    },
    "auth.error.no_network": {
        "es": "No pudimos conectar. Revisa tu internet e inténtalo otra vez.",
        "en": "We couldn't connect. Check your internet and try again.",
    },
    "auth.error.server_waking": {
        "es": "El servidor está tardando en despertar. Inténtalo de nuevo en un minuto.",
        "en": "The server is taking a while to wake up. Try again in a minute.",
    },
    "auth.error.timeout": {
        "es": "La respuesta tardó demasiado. Inténtalo de nuevo.",
        "en": "The reply took too long. Try again.",
    },
    "auth.error.invalid_credentials": {
        "es": "El correo o la contraseña no coinciden. Revísalos e inténtalo otra vez.",
        "en": "The email or the password does not match. Check them and try again.",
    },
    "auth.error.email_exists": {
        "es": "Ese correo ya tiene una cuenta. Prueba a entrar o recupera tu contraseña.",
        "en": "That email already has an account. Try signing in or reset your password.",
    },
    "auth.error.password_too_short": {
        "es": "La contraseña necesita al menos 8 caracteres.",
        "en": "The password needs at least 8 characters.",
    },
    "auth.error.invalid_request": {
        "es": "Revisa lo que escribiste e inténtalo otra vez.",
        "en": "Check what you typed and try again.",
    },
    "auth.error.too_many_attempts": {
        "es": "Hubo demasiados intentos. Espera unos minutos e inténtalo otra vez.",
        "en": "There were too many attempts. Wait a few minutes and try again.",
    },
    "auth.error.session_revoked": {
        "es": "Tu sesión terminó. Entra otra vez.",
        "en": "Your session ended. Please sign in again.",
    },
    "auth.error.profile_too_large": {
        "es": "Tu perfil es demasiado grande para guardarse en la cuenta. Borra algunas palabras guardadas.",
        "en": "Your profile is too big to be saved in your account. Delete some saved words.",
    },
    "auth.error.service_unavailable": {
        "es": "El servicio de cuentas no está disponible ahora. Inténtalo más tarde.",
        "en": "The accounts service is not available right now. Try again later.",
    },
    "auth.error.unexpected": {
        "es": "No pudimos entender la respuesta. Inténtalo de nuevo.",
        "en": "We couldn't understand the reply. Try again.",
    },
    "ai.error.sign_in_required": {
        "es": "Tu sesión terminó. Entra otra vez para usar el asistente.",
        "en": "Your session ended. Sign in again to use the assistant.",
    },
    "ai.error.user_daily_limit": {
        "es": "Llegaste a tu límite de consultas de hoy. Vuelve mañana.",
        "en": "You reached your limit of questions for today. Come back tomorrow.",
    },
    "account.title": {
        "es": "Cuenta",
        "en": "Account",
    },
    "account.verified": {
        "es": "Correo confirmado",
        "en": "Email confirmed",
    },
    "account.not_verified": {
        "es": "Correo sin confirmar",
        "en": "Email not confirmed",
    },
    "account.sync_ok": {
        "es": "Guardado en tu cuenta",
        "en": "Saved to your account",
    },
    "account.sync_pending": {
        "es": "Se guardará en tu cuenta cuando haya internet",
        "en": "Will be saved to your account when you are online",
    },
    "account.sync_failed": {
        "es": "No pudimos guardar en tu cuenta. Lo intentaremos otra vez.",
        "en": "We couldn't save to your account. We will try again.",
    },
    "account.offline_note": {
        "es": "Sin internet, tu sesión sigue abierta. Tus cambios se guardan en tu cuenta cuando vuelva la conexión.",
        "en": "Without internet, your session stays open. Your changes are saved to your account when the connection comes back.",
    },
    "account.local_note": {
        "es": "Tus documentos, tu biblioteca y tus estadísticas se quedan solo en este equipo. Tus ajustes y tus palabras se guardan en tu cuenta.",
        "en": "Your documents, your library and your statistics stay only on this computer. Your settings and your words are saved in your account.",
    },
    "account.sign_out": {
        "es": "Cerrar sesión",
        "en": "Sign out",
    },
    "account.delete": {
        "es": "Borrar mi cuenta",
        "en": "Delete my account",
    },
    "account.sign_out_title": {
        "es": "¿Cerrar sesión?",
        "en": "Sign out?",
    },
    "account.sign_out_body": {
        "es": "Tus documentos de este equipo se quedan guardados. Para volver a leer tendrás que entrar otra vez, con internet.",
        "en": "Your documents on this computer stay saved. To read again you will need to sign in again, with internet.",
    },
    "account.sign_out_pending": {
        "es": "Tienes cambios que aún no se guardaron en tu cuenta. Se guardarán cuando entres otra vez con internet.",
        "en": "You have changes that are not saved to your account yet. They will be saved when you sign in again with internet.",
    },
    "account.delete_title": {
        "es": "¿Borrar tu cuenta?",
        "en": "Delete your account?",
    },
    "account.delete_body": {
        "es": "Se borran tu cuenta y tus datos en línea (ajustes y palabras) y también los datos de este perfil en este equipo. Tus archivos originales no se tocan. Esto no se puede deshacer.",
        "en": "Your account and your online data (settings and words) are deleted, and so is the data of this profile on this computer. Your original files are not touched. This cannot be undone.",
    },
    "account.delete_confirm": {
        "es": "Borrar mi cuenta",
        "en": "Delete my account",
    },
    "account.deleting": {
        "es": "Borrando tu cuenta…",
        "en": "Deleting your account…",
    },
    "account.deleted": {
        "es": "Tu cuenta se borró.",
        "en": "Your account was deleted.",
    },
    "profile.migrated": {
        "es": "Tus documentos y ajustes de antes ahora son de tu perfil.",
        "en": "Your earlier documents and settings now belong to your profile.",
    },
    "profile.language_pending": {
        "es": "El idioma de tu cuenta se aplicará la próxima vez que abras ClearRead.",
        "en": "The language of your account will apply the next time you open ClearRead.",
    },
    "auth.error.invalid_session": {
        "es": "Tu sesión terminó. Entra otra vez.",
        "en": "Your session ended. Please sign in again.",
    },
    "account.avatar_a11y": {
        "es": "Cuenta de {name}",
        "en": "Account of {name}",
    },
    "auth.google_sign_in": {"es": "Entrar con Google", "en": "Sign in with Google"},
    "auth.or_with_email": {"es": "o con tu correo", "en": "or with your email"},
    "account.google_link": {"es": "Vincular con Google", "en": "Link with Google"},
    "account.google_linked": {"es": "Google vinculado", "en": "Google linked"},
    "google.waiting_title": {
        "es": "Esperando a Google…",
        "en": "Waiting for Google…",
    },
    "google.waiting_body": {
        "es": (
            "Se abrió tu navegador. Elige tu cuenta de Google y, cuando termines, "
            "vuelve aquí."
        ),
        "en": (
            "Your browser opened. Choose your Google account and, when you finish, "
            "come back here."
        ),
    },
    "google.waiting_cancel": {"es": "Cancelar", "en": "Cancel"},
    "auth.error.google_cancelled": {
        "es": "Cancelaste el acceso con Google. Puedes intentarlo otra vez cuando quieras.",
        "en": "You cancelled Google. You can try again whenever you want.",
    },
    "auth.error.google_already_linked": {
        "es": (
            "Esa cuenta de Google ya está vinculada a otro perfil de ClearRead. "
            "Prueba con otra cuenta de Google."
        ),
        "en": (
            "That Google account is already linked to another ClearRead profile. "
            "Try another Google account."
        ),
    },
    "auth.error.google_not_linked": {
        "es": (
            "Esa cuenta de Google todavía no está vinculada. Primero crea tu cuenta "
            "con tu correo y después vincula Google en Ajustes."
        ),
        "en": (
            "That Google account is not linked yet. First create your account with "
            "your email, then link Google in Settings."
        ),
    },
    "auth.error.google_attempt_not_found": {
        "es": "Se perdió el intento con Google. Inténtalo otra vez.",
        "en": "The Google attempt was lost. Try again.",
    },
    "auth.error.google_attempt_expired": {
        "es": "Pasó demasiado tiempo esperando a Google. Inténtalo otra vez.",
        "en": "It took too long to hear from Google. Try again.",
    },
    "auth.error.google_not_configured": {
        "es": (
            "Entrar con Google no está disponible ahora. Usa tu correo o inténtalo "
            "más tarde."
        ),
        "en": (
            "Google sign-in is not available right now. Use your email or try again "
            "later."
        ),
    },
    "auth.error.browser_unavailable": {
        "es": "No pudimos abrir tu navegador. Ábrelo tú y vuelve a intentarlo.",
        "en": "We couldn't open your browser. Open it yourself and try again.",
    },
}


def tr(key: str, lang: Language | str, **params: object) -> str:
    """Return the text for ``key`` in ``lang``, filling ``{params}``."""
    entry = CATALOG.get(key)
    if entry is None:
        raise MissingStringError(f"Unknown string key: {key!r}")
    return entry[Language(lang).value].format(**params)
