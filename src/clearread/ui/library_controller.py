"""Handlers for the library, folders, topics and saved words, with their dialogs."""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtWidgets import QMessageBox, QWidget

from clearread.services.document_library import DocumentLibrary
from clearread.services.glossary import GlossaryStore
from clearread.services.groups import GroupNameError, GroupNameProblem, GroupStore
from clearread.ui.dialogs import NamePromptDialog, make_confirm_box
from clearread.ui.strings import Language, tr
from clearread.ui.views.words_view import WordsView


@dataclass(frozen=True)
class _GroupKeys:
    """String keys of one kind of group, kept literal so they stay greppable."""

    rename_title: str
    name_label: str
    delete_title: str
    delete_message: str
    delete: str


FOLDER_KEYS = _GroupKeys(
    "folder.rename_title",
    "folder.name_label",
    "folder.delete_title",
    "folder.delete_message",
    "folder.delete",
)
TOPIC_KEYS = _GroupKeys(
    "topic.rename_title",
    "topic.name_label",
    "topic.delete_title",
    "topic.delete_message",
    "topic.delete",
)


class LibraryController:
    def __init__(
        self,
        parent: QWidget,
        language: Language,
        library: DocumentLibrary,
        folders: GroupStore,
        topics: GroupStore,
        glossary: GlossaryStore,
        words_view: WordsView,
        refresh_home: Callable[[], None],
    ) -> None:
        self._parent = parent
        self._language = language
        self._library = library
        self._folders = folders
        self._topics = topics
        self._glossary = glossary
        self._words_view = words_view
        self._refresh_home = refresh_home
        self.confirm_box: QMessageBox | None = None
        self.prompt_dialog: NamePromptDialog | None = None

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    def refresh_words(self) -> None:
        self._words_view.set_entries(self._glossary.entries(), self._topics.groups())

    def ask_delete_word(self, word: str) -> None:
        self._confirm(
            self._t("words.delete_title", word=word),
            self._t("words.delete_message"),
            "words.delete",
            lambda: self.delete_word(word),
        )

    def delete_word(self, word: str) -> None:
        self._glossary.remove(word)
        self.refresh_words()

    def set_word_topic(self, word: str, topic_id: str) -> None:
        self._glossary.set_topic(word, topic_id)
        self.refresh_words()

    def create_topic(self) -> None:
        self._prompt_name(
            "topic.new_title",
            "topic.name_label",
            "",
            "common.create",
            self._topics.create,
            self.refresh_words,
        )

    def rename_topic(self, topic_id: str) -> None:
        self._rename(self._topics, topic_id, TOPIC_KEYS, self.refresh_words)

    def ask_delete_topic(self, topic_id: str) -> None:
        self._ask_delete(self._topics, topic_id, TOPIC_KEYS, self.delete_topic)

    def delete_topic(self, topic_id: str) -> None:
        self._glossary.clear_topic(topic_id)
        self._topics.delete(topic_id)
        self.refresh_words()

    def ask_remove_document(self, key: str) -> None:
        recent = self._library.recent(key)
        if recent is not None:
            self._confirm(
                self._t("home.remove_title", name=recent.name),
                self._t("home.remove_message"),
                "home.remove_confirm",
                lambda: self.remove_recent(key),
            )

    def remove_recent(self, key: str) -> None:
        self._library.remove(key)
        self._refresh_home()

    def move_document(self, key: str, folder_id: str) -> None:
        self._library.set_folder(key, folder_id)
        self._refresh_home()

    def create_folder(self) -> None:
        self._prompt_name(
            "folder.new_title",
            "folder.name_label",
            "",
            "common.create",
            self._folders.create,
            self._refresh_home,
        )

    def rename_folder(self, folder_id: str) -> None:
        self._rename(self._folders, folder_id, FOLDER_KEYS, self._refresh_home)

    def ask_delete_folder(self, folder_id: str) -> None:
        self._ask_delete(self._folders, folder_id, FOLDER_KEYS, self.delete_folder)

    def delete_folder(self, folder_id: str) -> None:
        self._library.clear_folder(folder_id)
        self._folders.delete(folder_id)
        self._refresh_home()

    def _rename(
        self,
        store: GroupStore,
        group_id: str,
        keys: _GroupKeys,
        after: Callable[[], None],
    ) -> None:
        group = store.get(group_id)
        if group is None:
            return
        self._prompt_name(
            keys.rename_title,
            keys.name_label,
            group.name,
            "common.save",
            lambda name: store.rename(group_id, name),
            after,
        )

    def _ask_delete(
        self,
        store: GroupStore,
        group_id: str,
        keys: _GroupKeys,
        delete: Callable[[str], None],
    ) -> None:
        group = store.get(group_id)
        if group is not None:
            self._confirm(
                self._t(keys.delete_title, name=group.name),
                self._t(keys.delete_message),
                keys.delete,
                lambda: delete(group_id),
            )

    def _confirm(
        self, question: str, detail: str, confirm_key: str, on_yes: Callable[[], None]
    ) -> None:
        box, confirm = make_confirm_box(
            self._parent, question, detail, self._t(confirm_key), self._language
        )
        box.buttonClicked.connect(
            lambda clicked: on_yes() if clicked is confirm else None
        )
        box.finished.connect(lambda: self._forget_confirm(box))
        self.confirm_box = box
        box.open()

    def _forget_confirm(self, box: QMessageBox) -> None:
        box.deleteLater()
        if self.confirm_box is box:
            self.confirm_box = None

    def _prompt_name(
        self,
        title_key: str,
        label_key: str,
        initial: str,
        confirm_key: str,
        action: Callable[[str], object],
        after: Callable[[], None],
    ) -> None:
        def apply(name: str) -> GroupNameProblem | None:
            try:
                action(name)
            except GroupNameError as error:
                return error.problem
            return None

        dialog = NamePromptDialog(
            self._parent,
            self._t(title_key),
            self._t(label_key),
            initial,
            self._t(confirm_key),
            apply,
            self._language,
        )
        dialog.accepted.connect(after)
        dialog.finished.connect(lambda: self._forget_prompt(dialog))
        self.prompt_dialog = dialog
        dialog.open()

    def _forget_prompt(self, dialog: NamePromptDialog) -> None:
        dialog.deleteLater()
        if self.prompt_dialog is dialog:
            self.prompt_dialog = None
