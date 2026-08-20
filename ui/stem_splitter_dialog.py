"""Stem Splitter: load an audio file, split it into stems (vocals/drums/
bass/other) via Demucs, preview each stem, then mix all-or-a-selection of
them into an ESX sample slot. See audio/stem_separator.py for the Demucs
wrapper itself; this module is just the Qt UI + threading around it."""

import os
import tempfile

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QCheckBox, QSpinBox, QGroupBox, QProgressDialog, QWidget,
    QDialogButtonBox, QPlainTextEdit, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings

from audio import stem_separator, stem_deps
from audio.audio_player import AudioPlayer
from esx.constants import NUM_SAMPLES_MONO, NUM_SAMPLES
from esx.sample import Sample
from ui.waveform_widget import WaveformWidget
from ui.error_log import report_error
from ui.i18n import tr
from ui import icons
from ui.theme import TEXT_DIM

CONSENT_KEY = "stem_splitter/model_consent"
SUPPORTED_AUDIO_EXTS = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif")

# Coarse upper bound on how many separation-progress callback invocations to
# expect per model in the bag, used only to turn Demucs's raw progress
# callback (which reports discrete (model, segment) steps, not a percentage
# - see demucs/apply.py) into a "good enough" progress bar. If the real
# count is lower the bar simply reaches ~95% early and jumps to 100% at
# completion; if higher it just creeps rather than stalls. There is no
# official API to know the true segment count in advance.
_ASSUMED_STEPS_PER_MODEL = 20


def _make_busy_dialog(parent, text: str) -> QProgressDialog:
    progress = QProgressDialog(text, None, 0, 0, parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setCancelButton(None)
    progress.show()
    return progress


def _ask_consent(parent) -> bool:
    reply = QMessageBox.question(
        parent, tr("stem_splitter.consent_title"), tr("stem_splitter.consent_body"),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    if reply == QMessageBox.StandardButton.Yes:
        QSettings().setValue(CONSENT_KEY, "granted")
        return True
    QSettings().setValue(CONSENT_KEY, "declined")
    return False


class InstallProgressDialog(QDialog):
    """Shown while stem_deps.run_install() downloads/installs torch+demucs
    into the AppData folder - there's no percentage available (pip doesn't
    expose one over a plain pipe), so this shows pip's own output live
    instead of a fake number, which is at least an honest sense of
    progress."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("stem_splitter.title"))
        self.setModal(True)
        self.resize(600, 380)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("stem_splitter.installing_packages")))
        bar = QProgressBar()
        bar.setRange(0, 0)
        layout.addWidget(bar)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(2000)
        self._log.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        layout.addWidget(self._log, 1)

    def append_log(self, line: str):
        self._log.appendPlainText(line)


class InstallThread(QThread):
    log_line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def run(self):
        try:
            success, error = stem_deps.run_install(on_line=self.log_line.emit)
            self.finished.emit(success, error)
        except Exception as e:
            report_error("stem_deps_install", e)
            self.finished.emit(False, str(e))


class ModelLoadThread(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def run(self):
        try:
            separator = stem_separator.load_separator()
            self.finished.emit(separator)
        except Exception as e:
            report_error("stem_model_load", e)
            self.error.emit(str(e))


class SeparationThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict, int)
    error = pyqtSignal(str)

    def __init__(self, separator, path: str):
        super().__init__()
        self._separator = separator
        self._path = path

    def run(self):
        try:
            seen = set()

            def on_progress(data):
                try:
                    models = max(1, int(data.get("models", 1) or 1))
                    model_idx = int(data.get("model_idx_in_bag", 0) or 0)
                    segment_offset = data.get("segment_offset", 0)
                    seen.add((model_idx, segment_offset))
                    total_estimate = max(models * _ASSUMED_STEPS_PER_MODEL, len(seen))
                    pct = min(95, int(100 * len(seen) / total_estimate))
                    self.progress.emit(pct)
                except Exception:
                    pass

            self._separator.callback = on_progress
            stems, sample_rate = stem_separator.separate_file(self._separator, self._path)
            self.progress.emit(100)
            self.finished.emit(stems, sample_rate)
        except Exception as e:
            report_error("stem_separation", e)
            self.error.emit(str(e))


def ensure_stem_separation_ready(parent, on_ready, on_error):
    """Consent -> install torch/demucs if not already present (streamed
    live into an InstallProgressDialog) -> load the Demucs model, then calls
    on_ready(separator) or on_error(message). on_error("") means "aborted
    without needing to show anything further" (e.g. consent declined, which
    already showed its own message) - callers should only surface a message
    box for a non-empty error. Shared by the dialog's "Split into Stems"
    button and the Help menu's standalone preload action, so both go through
    the exact same install/consent logic."""
    consent = QSettings().value(CONSENT_KEY, None, type=str)
    if consent != "granted":
        if not _ask_consent(parent):
            QMessageBox.information(parent, tr("stem_splitter.title"), tr("stem_splitter.consent_declined_body"))
            on_error("")
            return

    if stem_deps.is_installed():
        _load_model(parent, on_ready, on_error)
        return

    install_dialog = InstallProgressDialog(parent)
    thread = InstallThread()
    thread.log_line.connect(install_dialog.append_log)

    def on_install_finished(success, error):
        install_dialog.close()
        if not success:
            on_error(error or tr("stem_splitter.install_failed"))
            return
        _load_model(parent, on_ready, on_error)

    thread.finished.connect(on_install_finished)
    install_dialog.show()
    thread.start()
    # Kept alive on the parent - a QThread with no other owner would
    # otherwise be garbage-collected mid-run.
    parent._stem_install_thread = thread


def _load_model(parent, on_ready, on_error):
    progress = _make_busy_dialog(parent, tr("stem_splitter.loading_model"))
    thread = ModelLoadThread()

    def on_finished(separator):
        progress.close()
        on_ready(separator)

    def on_thread_error(error):
        progress.close()
        on_error(tr("stem_splitter.model_load_failed", error=error))

    thread.finished.connect(on_finished)
    thread.error.connect(on_thread_error)
    thread.start()
    parent._stem_model_thread = thread


def run_consent_and_preload(parent):
    """Standalone consent + install + model-preload flow, wired to the Help
    menu so a user who declined consent inside the dialog (or never opened
    it) can retry without having to find the Stem Splitter entry point
    again."""
    def on_ready(_separator):
        QMessageBox.information(parent, tr("stem_splitter.title"), tr("stem_splitter.model_ready"))

    def on_error(error):
        if error:
            QMessageBox.critical(parent, tr("stem_splitter.title"), error)

    ensure_stem_separation_ready(parent, on_ready, on_error)


class StemSplitterDialog(QDialog):
    def __init__(self, tab_samples, esx_file, initial_sample=None):
        super().__init__(tab_samples)
        self._tab_samples = tab_samples
        self._esx = esx_file
        self._audio_player = AudioPlayer()
        self._input_path = None
        self._temp_input_path = None
        self._separator = None
        self._stems = {}
        self._stem_sample_rate = 44100
        self._stem_checks = {}
        self._stem_waveforms = {}
        self._stem_play_buttons = {}

        self.setWindowTitle(tr("stem_splitter.title"))
        self.resize(760, 660)
        self.setAcceptDrops(True)
        self._setup_ui()
        self._clear_stems()
        self._update_slot_range()

        if initial_sample is not None and not initial_sample.is_empty():
            self._load_from_sample(initial_sample)

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        file_group = QGroupBox(tr("stem_splitter.source_audio"))
        file_layout = QHBoxLayout(file_group)
        self._load_file_btn = QPushButton(icons.icon("folder-open"), tr("stem_splitter.load_audio_file"))
        self._load_file_btn.clicked.connect(self._browse_file)
        self._file_label = QLabel(tr("stem_splitter.no_file_loaded"))
        self._file_label.setWordWrap(True)
        file_layout.addWidget(self._load_file_btn)
        file_layout.addWidget(self._file_label, 1)
        layout.addWidget(file_group)

        hint = QLabel(tr("stem_splitter.drop_hint"))
        hint.setStyleSheet(f"color: {TEXT_DIM};")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._split_btn = QPushButton(icons.icon("wand-magic-sparkles"), tr("stem_splitter.split_button"))
        self._split_btn.setEnabled(False)
        self._split_btn.clicked.connect(self._start_split)
        layout.addWidget(self._split_btn)

        stems_group = QGroupBox(tr("stem_splitter.stems"))
        stems_layout = QVBoxLayout(stems_group)
        for name in stem_separator.STEM_NAMES:
            stems_layout.addWidget(self._build_stem_row(name))
        layout.addWidget(stems_group, 1)

        mix_row = QHBoxLayout()
        self._play_mix_btn = QPushButton(icons.icon("play"), tr("stem_splitter.play_mix"))
        self._play_mix_btn.clicked.connect(self._play_mix)
        self._stop_btn = QPushButton(icons.icon("stop"), tr("common.stop"))
        self._stop_btn.clicked.connect(self._stop_playback)
        mix_row.addWidget(self._play_mix_btn)
        mix_row.addWidget(self._stop_btn)
        mix_row.addStretch()
        layout.addLayout(mix_row)

        slot_group = QGroupBox(tr("stem_splitter.destination"))
        slot_layout = QHBoxLayout(slot_group)
        self._mono_check = QCheckBox(tr("stem_splitter.mono_checkbox"))
        self._mono_check.setChecked(getattr(self._tab_samples, "import_as_mono", True))
        self._mono_check.toggled.connect(self._update_slot_range)
        slot_layout.addWidget(self._mono_check)
        slot_layout.addWidget(QLabel(tr("stem_splitter.slot_colon")))
        self._slot_spin = QSpinBox()
        slot_layout.addWidget(self._slot_spin)
        slot_layout.addStretch()
        self._save_btn = QPushButton(icons.icon("floppy-disk"), tr("stem_splitter.save_to_slot"))
        self._save_btn.clicked.connect(self._save_to_slot)
        slot_layout.addWidget(self._save_btn)
        layout.addWidget(slot_group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("common.close"))
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def _build_stem_row(self, name: str) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        check = QCheckBox()
        check.setChecked(True)
        row_layout.addWidget(check, 0)

        label = QLabel(tr(f"stem_splitter.stem_{name}"))
        label.setFixedWidth(70)
        row_layout.addWidget(label, 0)

        waveform = WaveformWidget()
        waveform.setMinimumHeight(60)
        waveform.setMaximumHeight(60)
        row_layout.addWidget(waveform, 1)

        play_btn = QPushButton(icons.icon("play"), "")
        play_btn.setToolTip(tr("common.play"))
        play_btn.setFixedWidth(36)
        play_btn.clicked.connect(lambda: self._play_stem(name))
        row_layout.addWidget(play_btn, 0)

        self._stem_checks[name] = check
        self._stem_waveforms[name] = waveform
        self._stem_play_buttons[name] = play_btn
        return row

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(
            url.isLocalFile() and self._is_supported_audio(url.toLocalFile())
            for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and self._is_supported_audio(url.toLocalFile()):
                self._set_input_file(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()

    @staticmethod
    def _is_supported_audio(path: str) -> bool:
        return os.path.splitext(path)[1].lower() in SUPPORTED_AUDIO_EXTS

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("stem_splitter.load_audio_file"), "",
            f"{tr('stem_splitter.audio_files_filter')};;{tr('common.all_files_filter')}"
        )
        if path:
            self._set_input_file(path)

    def _load_from_sample(self, sample):
        """Writes the given (already-loaded) Sample out to a temp WAV file
        and uses it as the split input - lets the Sample Tools entry point
        default to the currently selected sample instead of requiring a
        separate file pick. The temp file is cleaned up once a different
        input replaces it or the dialog closes."""
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()
        with open(tmp_path, 'wb') as f:
            f.write(sample.to_export_wav_bytes())
        name = sample.name.strip('\x00').strip() or tr("common.empty_placeholder")
        label = tr("stem_splitter.using_current_sample", name=name, slot=sample.sample_number)
        self._set_input_file(tmp_path, is_temp=True, display_label=label)

    def _set_input_file(self, path: str, is_temp: bool = False, display_label: str = None):
        if self._temp_input_path and self._temp_input_path != path:
            self._cleanup_temp_input()
        self._input_path = path
        self._temp_input_path = path if is_temp else None
        self._file_label.setText(display_label if display_label else path)
        self._split_btn.setEnabled(True)
        self._clear_stems()

    def _cleanup_temp_input(self):
        if self._temp_input_path and os.path.exists(self._temp_input_path):
            try:
                os.remove(self._temp_input_path)
            except OSError:
                pass
        self._temp_input_path = None

    def _clear_stems(self):
        self._stems = {}
        for name in stem_separator.STEM_NAMES:
            self._stem_waveforms[name].clear()
            self._stem_play_buttons[name].setEnabled(False)
            self._stem_checks[name].setEnabled(False)
            self._stem_checks[name].setChecked(True)
        self._play_mix_btn.setEnabled(False)
        self._save_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Split flow
    # ------------------------------------------------------------------

    def _start_split(self):
        if self._input_path is None:
            return
        self._split_btn.setEnabled(False)
        ensure_stem_separation_ready(self, self._on_model_loaded, self._on_enable_failed)

    def _on_enable_failed(self, error: str):
        self._split_btn.setEnabled(True)
        if error:
            QMessageBox.critical(self, tr("stem_splitter.title"), error)

    def _on_model_loaded(self, separator):
        self._separator = separator

        self._progress = QProgressDialog(tr("stem_splitter.separating"), None, 0, 100, self)
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setCancelButton(None)
        self._progress.setValue(0)
        self._progress.show()

        self._sep_thread = SeparationThread(separator, self._input_path)
        self._sep_thread.progress.connect(self._progress.setValue)
        self._sep_thread.finished.connect(self._on_separation_finished)
        self._sep_thread.error.connect(self._on_separation_error)
        self._sep_thread.start()

    def _on_separation_finished(self, stems: dict, sample_rate: int):
        self._progress.close()
        self._split_btn.setEnabled(True)
        self._stems = stems
        self._stem_sample_rate = sample_rate

        any_stem = False
        for name in stem_separator.STEM_NAMES:
            arr = stems.get(name)
            has = arr is not None and arr.size > 0
            any_stem = any_stem or has
            self._stem_play_buttons[name].setEnabled(has)
            self._stem_checks[name].setEnabled(has)
            if has:
                self._stem_waveforms[name].set_audio(stem_separator.mono_preview_be16(arr))
            else:
                self._stem_waveforms[name].clear()

        self._play_mix_btn.setEnabled(any_stem)
        self._save_btn.setEnabled(any_stem)
        self._update_slot_range()

    def _on_separation_error(self, error: str):
        self._progress.close()
        self._split_btn.setEnabled(True)
        QMessageBox.critical(self, tr("stem_splitter.title"), tr("stem_splitter.separation_failed", error=error))

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def _selected_stem_names(self) -> list:
        return [
            name for name, check in self._stem_checks.items()
            if check.isChecked() and check.isEnabled()
        ]

    def _play_stem(self, name: str):
        arr = self._stems.get(name)
        if arr is None or arr.size == 0:
            return
        self._play_wav(stem_separator.stereo_float_to_wav_bytes(
            stem_separator.mix_stems(self._stems, [name]), self._stem_sample_rate
        ))

    def _play_mix(self):
        selected = self._selected_stem_names()
        if not selected:
            QMessageBox.information(self, tr("stem_splitter.title"), tr("stem_splitter.no_stems_selected"))
            return
        mixed = stem_separator.mix_stems(self._stems, selected)
        self._play_wav(stem_separator.stereo_float_to_wav_bytes(mixed, self._stem_sample_rate))

    def _play_wav(self, wav_bytes: bytes):
        if not wav_bytes:
            return
        try:
            self._audio_player.play(wav_bytes, self._stem_sample_rate)
        except Exception as exc:
            report_error("stem_splitter_playback", exc)

    def _stop_playback(self):
        self._audio_player.stop()

    # ------------------------------------------------------------------
    # Saving to a sample slot
    # ------------------------------------------------------------------

    def _update_slot_range(self, *_args):
        want_stereo = not self._mono_check.isChecked()
        lo, hi = (NUM_SAMPLES_MONO, NUM_SAMPLES - 1) if want_stereo else (0, NUM_SAMPLES_MONO - 1)
        self._slot_spin.blockSignals(True)
        self._slot_spin.setRange(lo, hi)
        suggested = self._tab_samples.next_empty_slot(lo, want_stereo)
        self._slot_spin.setValue(suggested if suggested is not None else lo)
        self._slot_spin.blockSignals(False)

    def _save_to_slot(self):
        selected = self._selected_stem_names()
        if not selected:
            QMessageBox.information(self, tr("stem_splitter.title"), tr("stem_splitter.no_stems_selected"))
            return

        mixed = stem_separator.mix_stems(self._stems, selected)
        if mixed.size == 0:
            QMessageBox.information(self, tr("stem_splitter.title"), tr("stem_splitter.no_stems_selected"))
            return

        mono = self._mono_check.isChecked()
        slot = self._slot_spin.value()

        if not self._esx.samples[slot].is_empty():
            reply = QMessageBox.question(
                self, tr("tab_samples.overwrite_sample_title"),
                tr("tab_samples.overwrite_sample_confirm", slot=slot),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            stem_separator.write_wav_file(tmp_path, mixed, self._stem_sample_rate, mono=mono)
            new_sample = Sample.from_wav_file(tmp_path, slot, as_mono=mono)
            self._tab_samples.commit_new_sample(slot, new_sample)
            QMessageBox.information(self, tr("stem_splitter.title"), tr("stem_splitter.saved_to_slot", slot=slot))
            self._update_slot_range()
        except Exception as exc:
            report_error("stem_splitter_save", exc)
            QMessageBox.critical(self, tr("common.error_title"), str(exc))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._audio_player.stop()
        self._cleanup_temp_input()
        super().closeEvent(event)
