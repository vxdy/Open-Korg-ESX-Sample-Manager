import json
import os
import tempfile
import zipfile

from .constants import NUM_SAMPLES_MONO, NUM_SAMPLES, PlayLevel, StretchStep
from .pattern import Pattern
from .sample import Sample, SampleTune
from .utils import safe_enum

FORMAT_NAME = "open-electribe-editor-pattern"
FORMAT_VERSION = 1


def _referenced_sample_slots(pattern: Pattern):
    slots = set()
    for part_list in (pattern.drum_parts, pattern.keyboard_parts, pattern.stretch_slice_parts):
        for part in part_list:
            if part.sample_pointer is not None and part.sample_pointer >= 0:
                slots.add(part.sample_pointer)
    return slots


def export_pattern(esx_file, pattern_index: int, filepath: str):
    """Save a pattern (with all its settings) and the samples it references
    into a single .esxpat archive that can be inserted into another ESX file."""
    pattern = esx_file.patterns[pattern_index]
    slots = sorted(_referenced_sample_slots(pattern))

    manifest_samples = []
    with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
        for slot in slots:
            if not (0 <= slot < len(esx_file.samples)):
                continue
            sample = esx_file.samples[slot]
            if sample.is_empty():
                continue
            wav_name = f"samples/{slot:03d}.wav"
            zf.writestr(wav_name, sample.to_export_wav_bytes())
            manifest_samples.append({
                "slot": slot,
                "name": sample.name.strip('\x00'),
                "sample_rate": sample.sample_rate,
                "is_stereo": sample.is_stereo_original,
                "play_level": int(sample.play_level),
                "stretch_step": int(sample.stretch_step),
                "loop_start": sample.loop_start,
                "sample_tune": sample.sample_tune.value,
                "wav": wav_name,
            })

        manifest = {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "pattern_name": pattern.name.strip('\x00'),
            "tempo": pattern.tempo.value,
            "samples": manifest_samples,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("pattern.bin", pattern.to_bytes())


def read_pattern_summary(filepath: str):
    """Read display info (name, tempo) from a .esxpat file without importing
    it, for listing saved patterns in the Pattern Browser. Returns None if
    the file isn't a valid pattern export."""
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            manifest = json.loads(zf.read("manifest.json").decode('utf-8'))
    except (KeyError, zipfile.BadZipFile, json.JSONDecodeError, OSError):
        return None
    if manifest.get("format") != FORMAT_NAME:
        return None
    return {
        "name": manifest.get("pattern_name", ""),
        "tempo": manifest.get("tempo"),
    }


def _find_empty_slot(samples, start: int, want_stereo: bool):
    if want_stereo:
        begin, end = NUM_SAMPLES_MONO, NUM_SAMPLES
    else:
        begin, end = 0, NUM_SAMPLES_MONO

    start = max(begin, min(start, end - 1))
    for idx in list(range(start, end)) + list(range(begin, start)):
        if samples[idx].is_empty():
            return idx
    return None


def import_pattern(esx_file, filepath: str, target_pattern_index: int):
    """Insert a pattern exported by export_pattern() into target_pattern_index,
    importing its referenced samples into free slots and remapping the
    pattern's sample pointers to those new slots.

    Returns (new_pattern, warnings). Sample references that could not be
    placed (no free slot of the right type) are dropped (-1) and reported
    as a warning rather than raising, since the pattern is otherwise usable.
    """
    warnings = []

    with zipfile.ZipFile(filepath, 'r') as zf:
        try:
            manifest = json.loads(zf.read("manifest.json").decode('utf-8'))
        except KeyError:
            raise ValueError("Not a valid pattern export file (missing manifest.json)")
        if manifest.get("format") != FORMAT_NAME:
            raise ValueError("Not a valid pattern export file")

        pattern_bytes = zf.read("pattern.bin")

        slot_map = {}
        next_mono = 0
        next_stereo = NUM_SAMPLES_MONO
        for entry in manifest.get("samples", []):
            want_stereo = bool(entry["is_stereo"])
            new_slot = _find_empty_slot(
                esx_file.samples, next_stereo if want_stereo else next_mono, want_stereo
            )
            if new_slot is None:
                warnings.append(
                    f"No free {'stereo' if want_stereo else 'mono'} sample slot for "
                    f"'{entry['name']}' (original slot {entry['slot']}); reference dropped."
                )
                continue

            wav_bytes = zf.read(entry["wav"])
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(tmp_fd)
            try:
                with open(tmp_path, 'wb') as f:
                    f.write(wav_bytes)
                new_sample = Sample.from_wav_file(tmp_path, new_slot, as_mono=not want_stereo)
            finally:
                os.unlink(tmp_path)

            new_sample.name = entry["name"][:8]
            new_sample.sample_rate = entry["sample_rate"]
            new_sample.play_level = safe_enum(PlayLevel, entry["play_level"])
            new_sample.stretch_step = safe_enum(StretchStep, entry["stretch_step"])
            new_sample.loop_start = entry["loop_start"]
            new_sample.sample_tune = SampleTune(entry["sample_tune"])

            esx_file.samples[new_slot] = new_sample
            slot_map[entry["slot"]] = new_slot
            if want_stereo:
                next_stereo = new_slot + 1
            else:
                next_mono = new_slot + 1

    new_pattern = Pattern.from_bytes(pattern_bytes, target_pattern_index)
    dropped = 0
    for part_list in (new_pattern.drum_parts, new_pattern.keyboard_parts, new_pattern.stretch_slice_parts):
        for part in part_list:
            if part.sample_pointer is not None and part.sample_pointer >= 0:
                if part.sample_pointer in slot_map:
                    part.sample_pointer = slot_map[part.sample_pointer]
                else:
                    part.sample_pointer = -1
                    dropped += 1

    if dropped:
        warnings.append(f"{dropped} sample reference(s) in the pattern could not be resolved and were cleared.")

    esx_file.patterns[target_pattern_index] = new_pattern
    return new_pattern, warnings
