import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtNetwork import QSslSocket
from PySide6.QtWidgets import QMessageBox

from k_whisper.app import parse_args, use_system_tls
from k_whisper.batch.job import Job, JobStatus
from k_whisper.batch.queue import JobQueue
from k_whisper.engine.options import TranscribeOptions, with_mode
from k_whisper.models.manager import ModelManager
from k_whisper.settings import AppSettings
from k_whisper.ui.advanced_dialog import AdvancedDialog
from k_whisper.ui.main_window import MainWindow
from k_whisper.ui.queue_view import job_status, row_actions
from k_whisper.ui.theme import install
from k_whisper.ui.widgets import confirm


def make_window(qtbot, tmp_path, model="ggml-tiny.bin", installed=None, **options) -> MainWindow:
    """``installed``: model files and their contents; by default tiny and the chosen model."""
    install("light")
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    for name, data in (installed or {"ggml-tiny.bin": b"x", model: b"x"}).items():
        (models_dir / name).write_bytes(data)
    settings = AppSettings(models_dir=str(models_dir))
    settings.options = TranscribeOptions(model=model, **options).to_dict()
    queue = JobQueue(settings, ModelManager(models_dir), state_file=tmp_path / "queue.json")
    window = MainWindow(settings, queue.models, queue)
    qtbot.addWidget(window)
    return window


def test_waiting_recordings_follow_the_run_bar(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    (tmp_path / "a.wav").write_bytes(b"x")
    window.add_paths([tmp_path / "a.wav"])
    job = window.queue.jobs[0]
    assert job.opts.formats == ["srt"]

    window.run_bar.mode.group.buttons()[1].click()  # Transcript
    assert job.opts.formats == ["txt"] and not job.opts.resegment

    job.status = JobStatus.DONE
    window.run_bar.mode.group.buttons()[2].click()  # Both
    assert job.opts.formats == ["txt"], "finished recordings keep the settings they were made with"


def test_finished_recordings_can_be_transcribed_again(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    for name in ("a.wav", "b.wav"):
        (tmp_path / name).write_bytes(b"x")
    window.add_paths([tmp_path / "a.wav", tmp_path / "b.wav"])
    for job in window.queue.jobs:
        job.status = JobStatus.DONE
    window._update_state()
    start = window.run_bar.start_btn
    assert start.isEnabled() and start.text().strip() == "Transcribe 2 again"

    window.queue_view.setCurrentIndex(window.job_model.index(0))
    assert start.text().strip() == "Transcribe 1 selected again"
    assert window._again_targets() == ([window.queue.jobs[0].id], True)

    window.settings.existing_files = "replace"
    assert window._existing_files_policy(window.queue.jobs) == "replace"
    window.settings.existing_files = "ask"
    assert window._existing_files_policy(window.queue.jobs) == "number", "nothing to ask about yet"


def test_model_choice_lists_models_by_size_with_their_size(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    (tmp_path / "models" / "ggml-base.bin").write_bytes(b"xx")  # larger than the 1-byte tiny
    window._refresh_model_list()
    combo = window.run_bar.model
    items = [combo.itemText(i) for i in range(combo.count()) if combo.itemData(i)]
    assert items[:2] == ["tiny (1 B)", "base (2 B)"]


def test_models_are_listed_smallest_first(qtbot, tmp_path):
    page = make_window(qtbot, tmp_path).models_page
    for show_all in (False, True):
        page.show_all.setChecked(show_all)
        sizes = [page.manager.size_of(m.filename) for m in page._models()]
        assert sizes == sorted(sizes)


def test_language_list_can_be_searched(qtbot, tmp_path):
    language = make_window(qtbot, tmp_path).run_bar.language
    language.showPopup()
    qtbot.keyClicks(language.search, "CZE")
    assert language.proxy.rowCount() == 1
    qtbot.keyClick(language.search, Qt.Key.Key_Return)
    assert language.currentData() == "cs"
    assert not language.popup.isVisible()

    language.showPopup()
    assert language.search.text() == "", "every opening starts with the whole list"
    qtbot.keyClick(language.search, Qt.Key.Key_Escape)
    assert not language.popup.isVisible() and language.currentData() == "cs"


def test_destructive_questions_default_to_cancel(qtbot, monkeypatch):
    install("light")
    seen = {}

    def fake_exec(box):
        seen["cancel is default"] = box.defaultButton() is box.button(QMessageBox.StandardButton.Cancel)
        seen["icon"] = box.icon()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    assert not confirm(None, "Delete model", "Delete tiny?", "", "Delete", destructive=True)
    assert seen == {"cancel is default": True, "icon": QMessageBox.Icon.NoIcon}


def test_row_buttons_offer_the_next_step():
    done = Job(source="/a.wav", options={}, status=JobStatus.DONE, outputs=["/a.srt", "/a.txt"])
    assert row_actions(done)[:2] == [("open:0", "Open SRT"), ("open:1", "Open TXT")]
    assert row_actions(done)[2][0] == "reveal"
    failed = Job(source="/a.wav", options={}, status=JobStatus.FAILED)
    assert [key for key, _text in row_actions(failed)] == ["log", "retry"]
    assert row_actions(Job(source="/a.wav", options={})) == []
    assert row_actions(Job(source="/a.wav", options={}, status=JobStatus.RUNNING)) == [("stop", "Stop")]


def test_english_only_model_locks_language(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path, model="ggml-base.en.bin")
    bar = window.run_bar
    assert bar.options().language == "en"
    assert not bar.language.isEnabled()
    assert not bar.translate.isEnabled()


def test_without_a_model_the_queue_points_to_the_models_page(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    bar = window.run_bar
    assert bar.model_slot.currentWidget() is bar.model
    assert not window.empty.models_btn.isVisibleTo(window.empty)
    window.models.delete("ggml-tiny.bin")
    assert bar.model_slot.currentWidget() is bar.get_model_btn
    assert window.empty.models_btn.isVisibleTo(window.empty)
    bar.get_model_btn.click()
    assert window.pages.currentIndex() == 1, "the button opens the Models page"
    (tmp_path / "a.wav").write_bytes(b"x")
    window.add_paths([tmp_path / "a.wav"])
    assert not window.run_bar.start_btn.isEnabled() and not window.act_start.isEnabled()


def test_a_missing_chosen_model_gives_way_to_the_biggest_downloaded(qtbot, tmp_path):
    installed = {"ggml-tiny.bin": b"x", "ggml-base.bin": b"xx"}
    window = make_window(qtbot, tmp_path, model="ggml-large-v3.bin", installed=installed)
    assert window.run_bar.options().model == "ggml-base.bin"
    assert window.models_page.current_model == "ggml-base.bin"
    combo = window.run_bar.model
    assert not any("not downloaded" in combo.itemText(i) for i in range(combo.count()))


def test_turbo_model_cannot_translate(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path, model="ggml-large-v3-turbo-q5_0.bin", language="cs", translate=True)
    bar = window.run_bar
    assert not bar.options().translate
    assert not bar.translate.isEnabled() and not bar.translate.isChecked()


def test_reset_keeps_the_main_window_choices(qtbot):
    install("light")
    chosen = with_mode(TranscribeOptions(model="ggml-tiny.bin", language="cs"), "transcript")
    dialog = AdvancedDialog(chosen.updated(vad=False, beam_size=1), {})
    qtbot.addWidget(dialog)
    dialog.set_options(dialog._defaults())
    assert dialog.options() == chosen


def test_waiting_row_shows_the_silence_model_download():
    job = Job(source="/a.wav", options={}, stage="Downloading silence model")
    assert job_status(job) == ("Waiting", "Downloading silence model")


def test_files_on_the_command_line():
    assert parse_args(["/x/talk.mp4"]).files == [Path("/x/talk.mp4")]


@pytest.mark.skipif(sys.platform != "win32", reason="Qt uses OpenSSL only on Windows")
def test_https_uses_schannel_on_windows(qapp):
    use_system_tls()
    assert QSslSocket.activeBackend() == "schannel"
