import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from k_whisper.batch import queue as queue_module
from k_whisper.batch.job import Job, JobStatus, output_base_name, output_paths
from k_whisper.batch.queue import JobQueue, collect_media
from k_whisper.engine.options import TranscribeOptions, with_mode
from k_whisper.models import catalog
from k_whisper.models.catalog import ModelInfo, describe, format_size, parse_name, parse_tree
from k_whisper.models.manager import Download, ModelManager
from k_whisper.settings import SETTINGS_KEY, AppSettings
from k_whisper.transcript.model import Segment, Transcript


def test_parse_name_and_describe():
    assert parse_name("ggml-large-v3-turbo-q5_0.bin") == ("large-v3-turbo", False, "q5_0")
    assert parse_name("ggml-base.en.bin") == ("base", True, "")
    assert describe("ggml-large-v3-turbo-q5_0.bin") == "Large v3 Turbo, all languages, compressed (Q5)"
    assert describe("ggml-small.en.bin") == "Small, English only, uncompressed"


def test_parse_tree_filters_and_sorts():
    entries = [
        {"type": "file", "path": "README.md", "size": 1},
        {"type": "file", "path": "ggml-small.bin", "size": 3, "lfs": {"oid": "abc"}},
        {"type": "file", "path": "ggml-tiny.bin", "size": 2},
        {"type": "directory", "path": "ggml-x.bin"},
    ]
    models = parse_tree(entries)
    assert [m.filename for m in models] == ["ggml-tiny.bin", "ggml-small.bin"]
    assert models[1].sha256 == "abc"


def test_format_size():
    assert format_size(574_041_195) == "574.0 MB"
    assert format_size(3_095_033_483) == "3.1 GB"


def test_builtin_catalog_has_checksums():
    assert all(len(m.sha256) == 64 for m in catalog.BUILTIN_CATALOG)
    assert len(catalog.VAD_MODEL.sha256) == 64


def test_output_naming(tmp_path):
    src = Path("/media/talk.final.mp4")
    assert output_base_name("{name}", src, "cs", "ggml-base.bin") == "talk.final"
    assert output_base_name("{name}.{lang}", src, "", "ggml-base.bin") == "talk.final.auto"
    assert output_base_name("{name}-{model}", src, "en", "ggml-large-v3-turbo-q5_0.bin") == (
        "talk.final-large-v3-turbo-q5_0"
    )
    assert output_base_name("{bogus}", src, "en", "m") == "talk.final"
    assert output_base_name("{name.lang}", src, "en", "m") == "talk.final"
    assert output_base_name("a/b:{name}", src, "en", "m") == "a_b_talk.final"
    paths = output_paths(src, TranscribeOptions(formats=["srt", "json"]), tmp_path, "{name}", "en")
    assert paths["srt"].name == "talk.final.srt"
    assert paths["json"].name == "talk.final.json"
    taken = frozenset({tmp_path / "talk.final.json", tmp_path / "talk.final-2.srt"})
    paths = output_paths(src, TranscribeOptions(formats=["srt", "json"]), tmp_path, "{name}", "en", taken)
    assert paths["srt"].name == "talk.final-3.srt"


def test_job_roundtrip_resets_running():
    job = Job(source="/a.mp3", options={}, status=JobStatus.RUNNING, progress=0.5)
    restored = Job.from_dict(job.to_dict())
    assert restored.status == JobStatus.PENDING and restored.progress == 0


def test_collect_media(tmp_path):
    (tmp_path / "sub").mkdir()
    for name in ("a.mp3", "sub/b.MKV", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    found = {p.name for p in collect_media([tmp_path])}
    assert found == {"a.mp3", "b.MKV"}
    assert collect_media([tmp_path / "a.mp3", tmp_path / "notes.txt"]) == [tmp_path / "a.mp3"]


def test_queue_persistence(qtbot, tmp_path):
    (tmp_path / "a.wav").write_bytes(b"x")
    models = ModelManager(tmp_path / "models")
    state = tmp_path / "queue.json"
    queue = JobQueue(AppSettings(), models, state_file=state)
    assert queue.add_paths([tmp_path / "a.wav"], TranscribeOptions(language="cs")) == 1
    queue.save()

    other = JobQueue(AppSettings(), models, state_file=state)
    other.load()
    assert len(other.jobs) == 1
    assert other.jobs[0].opts.language == "cs"


def test_queue_fails_job_without_model(qtbot, tmp_path):
    (tmp_path / "a.wav").write_bytes(b"x")
    settings = AppSettings(whisper_cli_path=__file__)  # any existing file passes the lookup
    queue = JobQueue(settings, ModelManager(tmp_path / "models"), state_file=tmp_path / "q.json")
    queue.add_paths([tmp_path / "a.wav"], TranscribeOptions(model="ggml-missing.bin"))
    with qtbot.waitSignal(queue.all_done, timeout=3000):
        queue.start()
    assert queue.jobs[0].status == JobStatus.FAILED
    assert "not downloaded" in queue.jobs[0].error


def make_queue(tmp_path, *names: str) -> JobQueue:
    for name in names:
        (tmp_path / name).write_bytes(b"x")
    queue = JobQueue(AppSettings(), ModelManager(tmp_path / "models"), state_file=tmp_path / "q.json")
    queue.add_paths([tmp_path / n for n in names], with_mode(TranscribeOptions(), "both"))
    return queue


def test_queue_does_not_add_waiting_recordings_twice(qtbot, tmp_path):
    queue = make_queue(tmp_path, "a.wav")
    assert queue.add_paths([tmp_path / "a.wav"], TranscribeOptions()) == 0
    queue.jobs[0].status = JobStatus.DONE
    assert queue.add_paths([tmp_path / "a.wav"], TranscribeOptions()) == 1


def test_recordings_with_the_same_name_keep_their_own_files(qtbot, tmp_path):
    queue = make_queue(tmp_path, "talk.mp4", "talk.wav")
    first, second = queue.jobs
    first.status, first.outputs = JobStatus.DONE, [str(tmp_path / "talk.srt"), str(tmp_path / "talk.txt")]
    assert queue._outputs_for(second, "en")["srt"] == tmp_path / "talk-2.srt"
    assert queue._outputs_for(first, "en")["srt"] == tmp_path / "talk.srt", "transcribing again overwrites"


def test_existing_files_get_a_number_unless_replacing(qtbot, tmp_path):
    queue = make_queue(tmp_path, "talk.wav")
    job = queue.jobs[0]
    (tmp_path / "talk.srt").write_text("old", encoding="utf-8")
    assert queue.existing_outputs([job], job.opts) == {job.id: [tmp_path / "talk.srt"]}
    assert queue.existing_outputs([job], job.opts.updated(formats=["txt"])) == {}

    transcript = Transcript(segments=[Segment(0, 2, "Hello.")], language="en")
    queue._write_outputs(job, transcript)
    assert (tmp_path / "talk.srt").read_text(encoding="utf-8") == "old", "never overwritten without being asked"
    assert job.outputs == [str(tmp_path / "talk-2.srt"), str(tmp_path / "talk-2.txt")]

    queue.on_existing = "replace"
    queue._write_outputs(job, transcript)
    assert "Hello." in (tmp_path / "talk.srt").read_text(encoding="utf-8")


def test_skipping_leaves_recordings_with_existing_files(qtbot, tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "ggml-tiny.bin").write_bytes(b"x")
    (tmp_path / "talk.wav").write_bytes(b"x")
    (tmp_path / "talk.srt").write_text("old", encoding="utf-8")
    settings = AppSettings(whisper_cli_path=__file__)  # any existing file passes the lookup
    queue = JobQueue(settings, ModelManager(models), state_file=tmp_path / "q.json")
    queue.add_paths([tmp_path / "talk.wav"], TranscribeOptions(model="ggml-tiny.bin", language="en"))
    queue.on_existing = "skip"
    with qtbot.waitSignal(queue.all_done, timeout=3000):
        queue.start()
    assert queue.jobs[0].status == JobStatus.SKIPPED
    assert queue.jobs[0].outputs == [str(tmp_path / "talk.srt")]


def test_old_skip_setting_carries_over(qtbot):
    QSettings().setValue(SETTINGS_KEY, json.dumps({"skip_existing": True}))
    try:
        assert AppSettings.load().existing_files == "skip"
    finally:
        QSettings().remove(SETTINGS_KEY)


def test_plain_text_keeps_whisper_segments(qtbot, tmp_path):
    queue = make_queue(tmp_path, "talk.wav")
    text = "This is a long sentence that will certainly not fit into one subtitle of forty two characters."
    queue._write_outputs(queue.jobs[0], Transcript(segments=[Segment(0, 8, text)], language="en"))
    assert (tmp_path / "talk.txt").read_text(encoding="utf-8") == text + "\n"
    assert "\n2\n" in (tmp_path / "talk.srt").read_text(encoding="utf-8")


def test_failure_while_saving_does_not_stop_the_queue(qtbot, tmp_path, monkeypatch):
    def broken_export(*_args):
        raise ValueError("broken")

    monkeypatch.setattr(queue_module, "export", broken_export)
    queue = make_queue(tmp_path, "a.wav")
    job = queue.jobs[0]
    job.status, queue.current, queue.running = JobStatus.RUNNING, job, True
    with qtbot.waitSignal(queue.all_done, timeout=3000):
        queue._on_task_finished(job, Transcript(segments=[Segment(0, 1, "hi")]), "")
    assert job.status == JobStatus.FAILED and "broken" in job.error
    assert not queue.running


MODEL = bytes(range(256)) * 1000


class ModelServer(BaseHTTPRequestHandler):
    """Serves MODEL with Range support; ``fail`` makes the next request an error page."""

    fail = False

    def log_message(self, format, *args) -> None:  # noqa: A002 - http.server API
        pass

    def reply(self, code: int, body: bytes, headers: dict | None = None) -> None:
        self.send_response(code)
        for key, value in {**(headers or {}), "Content-Length": str(len(body))}.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if ModelServer.fail:
            ModelServer.fail = False
            return self.reply(503, b"Service unavailable")
        start = int(self.headers.get("Range", "bytes=0-").split("=")[1].rstrip("-"))
        if start >= len(MODEL):
            return self.reply(416, b"<Error><Code>InvalidRange</Code></Error>")
        headers = {"Content-Range": f"bytes {start}-{len(MODEL) - 1}/{len(MODEL)}"} if start else {}
        self.reply(206 if start else 200, MODEL[start:], headers)


@pytest.fixture
def model_server(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), ModelServer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(catalog, "download_url", lambda _repo, name: f"http://127.0.0.1:{server.server_port}/{name}")
    yield ModelServer
    server.shutdown()


def download(qtbot, manager: ModelManager, info: ModelInfo) -> str:
    with qtbot.waitSignal(manager.download_finished, timeout=10_000) as blocker:
        manager.download(info)
    return blocker.args[1]


def test_error_page_does_not_end_up_in_the_model(qtbot, tmp_path, model_server):
    manager = ModelManager(tmp_path)
    info = ModelInfo("ggml-test.bin", len(MODEL))
    model_server.fail = True
    assert "Download failed" in download(qtbot, manager, info)
    assert download(qtbot, manager, info) == ""
    assert (tmp_path / "ggml-test.bin").read_bytes() == MODEL


def test_complete_part_file_is_kept_when_the_server_says_416(qtbot, tmp_path, model_server):
    manager = ModelManager(tmp_path)
    (tmp_path / "ggml-test.bin.part").write_bytes(MODEL)
    assert download(qtbot, manager, ModelInfo("ggml-test.bin", len(MODEL))) == ""
    assert (tmp_path / "ggml-test.bin").read_bytes() == MODEL


def test_damaged_download_is_deleted(qtbot, tmp_path, model_server):
    manager = ModelManager(tmp_path)
    assert "damaged" in download(qtbot, manager, ModelInfo("ggml-test.bin", len(MODEL), sha256="0" * 64))
    assert not (tmp_path / "ggml-test.bin").exists() and not (tmp_path / "ggml-test.bin.part").exists()


def test_progress_of_models_over_2_gb(qtbot, tmp_path):
    manager = ModelManager(tmp_path)
    large = ModelInfo("ggml-large-v3.bin", 3_095_033_483)
    dl = Download(manager._nam, large, tmp_path / large.filename)
    with qtbot.waitSignal(dl.progress) as blocker:
        dl._on_progress(2_500_000_000, -1)
    assert blocker.args == [2_500_000_000, 3_095_033_483]
    with qtbot.waitSignal(manager.download_progress) as blocker:
        manager.download_progress.emit(large.filename, 2_500_000_000, large.size)
    assert blocker.args == [large.filename, 2_500_000_000, 3_095_033_483]


def test_import_names_the_model_like_the_models_folder_lists_it(qtbot, tmp_path):
    (tmp_path / "custom.ggml").write_bytes(b"model")
    manager = ModelManager(tmp_path / "models")
    with qtbot.waitSignal(manager.download_finished, timeout=3000):
        manager.import_model(tmp_path / "custom.ggml")
    assert manager.installed() == ["ggml-custom.bin"]
