from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QGridLayout
from PyQt6.QtCore import Qt


class TabInfo(QWidget):
    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # File statistics group
        stats_group = QGroupBox("File Statistics")
        stats_layout = QGridLayout(stats_group)
        stats_layout.setHorizontalSpacing(24)
        stats_layout.setVerticalSpacing(10)
        stats_layout.setColumnStretch(2, 1)

        self._labels = {}
        rows = [
            ("patterns_used", "Patterns Used:"),
            ("samples_used", "Samples Used:"),
            ("mono_samples", "Mono Samples:"),
            ("stereo_samples", "Stereo Samples:"),
            ("songs_used", "Songs Used:"),
            ("sample_memory", "Sample Memory Used:"),
            ("sample_memory_pct", "Sample Memory %:"),
        ]

        for row_idx, (key, label_text) in enumerate(rows):
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setStyleSheet("color: #9aa0a8;")
            value = QLabel("—")
            value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            value.setStyleSheet("font-weight: 600; color: #4fb6ff;")
            stats_layout.addWidget(label, row_idx, 0)
            stats_layout.addWidget(value, row_idx, 1)
            self._labels[key] = value

        layout.addWidget(stats_group)
        layout.addStretch()

    def update_data(self, esx_file):
        from esx.constants import MAX_SAMPLE_MEM_IN_BYTES, NUM_PATTERNS, NUM_SAMPLES, NUM_SONGS

        used_patterns = esx_file.get_used_pattern_count()
        used_samples = esx_file.get_used_sample_count()
        mono_samples = esx_file.get_used_mono_sample_count()
        stereo_samples = esx_file.get_used_stereo_sample_count()
        used_songs = esx_file.get_used_song_count()
        mem_bytes = esx_file.get_sample_memory_used_bytes()
        mem_pct = (mem_bytes / MAX_SAMPLE_MEM_IN_BYTES * 100) if MAX_SAMPLE_MEM_IN_BYTES > 0 else 0

        self._labels["patterns_used"].setText(f"{used_patterns} / {NUM_PATTERNS}")
        self._labels["samples_used"].setText(f"{used_samples} / {NUM_SAMPLES}")
        self._labels["mono_samples"].setText(f"{mono_samples} / 256")
        self._labels["stereo_samples"].setText(f"{stereo_samples} / 128")
        self._labels["songs_used"].setText(f"{used_songs} / {NUM_SONGS}")
        self._labels["sample_memory"].setText(f"{mem_bytes:,} bytes")
        self._labels["sample_memory_pct"].setText(f"{mem_pct:.1f}%")
