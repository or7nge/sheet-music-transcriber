#!/usr/bin/env python3
"""Core transcription utilities shared by the web server and legacy UIs."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional
import os
import shutil
import subprocess
import time


ProgressCallback = Callable[[str, float, str], None]

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_HOMR_DIR_NAME = "homr"
HOMR_CHECK_TTL_SECONDS = 15.0
_homr_check_cache: dict[str, float | bool] = {"checked_at": 0.0, "value": False}


@dataclass(slots=True)
class ProcessingResult:
    concise_notes_text: str
    musicxml_path: Path
    midi_path: Optional[Path]
    preview_path: Optional[Path]
    log: list[str]


def resolve_homr_dir() -> Path:
    """Resolve homr working directory with env override."""
    env_override = os.environ.get("HOMR_DIR")
    if env_override:
        return Path(env_override).expanduser().resolve()

    candidates = (
        BASE_DIR.parent / DEFAULT_HOMR_DIR_NAME,
        BASE_DIR / DEFAULT_HOMR_DIR_NAME,
        Path.cwd().parent / DEFAULT_HOMR_DIR_NAME,
        Path.cwd() / DEFAULT_HOMR_DIR_NAME,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return (BASE_DIR.parent / DEFAULT_HOMR_DIR_NAME).resolve()


@lru_cache(maxsize=1)
def _music21_converter():
    from music21 import converter

    return converter


@lru_cache(maxsize=1)
def _pdf2image_convert():
    from pdf2image import convert_from_path

    return convert_from_path


@lru_cache(maxsize=1)
def _cv2_module():
    import cv2

    return cv2


@lru_cache(maxsize=1)
def _numpy_module():
    import numpy as np

    return np


def check_homr_installation(force_refresh: bool = False) -> bool:
    """Check whether homr is callable from the configured directory."""
    cache_age = time.time() - float(_homr_check_cache["checked_at"])
    if not force_refresh and cache_age < HOMR_CHECK_TTL_SECONDS:
        return bool(_homr_check_cache["value"])

    homr_dir = resolve_homr_dir()
    if not homr_dir.exists():
        _homr_check_cache.update({"checked_at": time.time(), "value": False})
        return False

    try:
        result = subprocess.run(
            ["poetry", "run", "homr", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=homr_dir,
        )
        success = result.returncode == 0
        _homr_check_cache.update({"checked_at": time.time(), "value": success})
        return success
    except (subprocess.SubprocessError, FileNotFoundError):
        _homr_check_cache.update({"checked_at": time.time(), "value": False})
        return False


def convert_pdf_to_images(pdf_path: str | Path, output_dir: str | Path) -> list[Path]:
    """Convert the first PDF page to JPEG and return output paths."""
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    convert_from_path = _pdf2image_convert()

    try:
        images = convert_from_path(
            str(pdf_path),
            dpi=220,
            first_page=1,
            last_page=1,
            fmt="jpeg",
            thread_count=1,
        )
    except Exception as exc:
        raise RuntimeError(f"PDF conversion failed: {exc}") from exc

    image_paths: list[Path] = []
    for index, image in enumerate(images, start=1):
        destination = output_dir / f"page_{index}.jpg"
        image.save(destination, "JPEG")
        image_paths.append(destination)

    return image_paths


def process_with_homr(image_path: str | Path, output_dir: str | Path) -> Path:
    """Run homr on an image and return generated MusicXML path."""
    image_path = Path(image_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    homr_dir = resolve_homr_dir()
    if not homr_dir.exists():
        raise RuntimeError(f"homr directory not found: {homr_dir}")

    processed_image = image_path
    result = _run_homr(homr_dir=homr_dir, image_path=processed_image)
    details = _extract_homr_details(result)

    # homr can fail early on low-contrast or low-resolution uploads.
    # Retry once with a staff-friendly enhanced render before surfacing an error.
    if result.returncode != 0 and _is_staff_detection_failure(details):
        retry_image = _prepare_retry_image_for_homr(image_path=image_path, output_dir=output_dir)
        processed_image = retry_image
        retry_result = _run_homr(homr_dir=homr_dir, image_path=processed_image)
        retry_details = _extract_homr_details(retry_result)
        if retry_result.returncode != 0:
            summary = _summarize_homr_error(retry_details)
            raise RuntimeError(
                "homr could not detect enough notation structure after one enhancement retry. "
                "Try a straighter, higher-resolution crop where staff lines and noteheads are clear. "
                f"Details: {summary}"
            )

        result = retry_result
        details = retry_details

    if result.returncode != 0:
        summary = _summarize_homr_error(details)
        raise RuntimeError(f"homr processing failed: {summary}")

    # homr writes output next to the source image.
    generated_musicxml = processed_image.with_suffix(".musicxml")
    if not generated_musicxml.exists():
        raise RuntimeError("homr finished but no MusicXML file was generated")

    # Keep artifacts inside output_dir for predictable server downloads.
    destination = output_dir / "score.musicxml"
    if generated_musicxml.resolve() != destination.resolve():
        shutil.copy2(generated_musicxml, destination)
    else:
        destination = generated_musicxml

    return destination


def _run_homr(homr_dir: Path, image_path: Path) -> subprocess.CompletedProcess[str]:
    """Execute homr for one image and return the subprocess result."""
    try:
        return subprocess.run(
            ["poetry", "run", "homr", str(image_path)],
            capture_output=True,
            text=True,
            cwd=homr_dir,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("homr timed out while processing the score") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("poetry was not found in PATH") from exc


def _extract_homr_details(result: subprocess.CompletedProcess[str]) -> str:
    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    return stderr or stdout or "Unknown homr error"


def _summarize_homr_error(details: str) -> str:
    lines = [line.strip() for line in details.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.lower().startswith("exception:"):
            return line
    if lines:
        return lines[-1]
    return "Unknown homr error"


def _is_staff_detection_failure(details: str) -> bool:
    lower = details.lower()
    markers = (
        "no staffs found",
        "no noteheads found",
        "found 0 staffs",
        "found 0 staff anchors",
    )
    return any(marker in lower for marker in markers)


def _prepare_retry_image_for_homr(image_path: Path, output_dir: Path) -> Path:
    """Build a contrast-enhanced binary image that improves staff detection."""
    cv2 = _cv2_module()
    np = _numpy_module()
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError("Uploaded image could not be read for retry preprocessing")

    height, width = image.shape[:2]
    max_dim = max(height, width)
    if max_dim < 2200:
        scale = min(3.0, 2200.0 / float(max_dim))
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    clahe = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8))
    enhanced = clahe.apply(image)
    enhanced = cv2.GaussianBlur(enhanced, (3, 3), 0)

    binary = cv2.adaptiveThreshold(
        enhanced,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        41,
        11,
    )

    if float(np.mean(binary)) < 127:
        binary = cv2.bitwise_not(binary)

    retry_path = output_dir / f"{image_path.stem}_staff_retry.png"
    if not cv2.imwrite(str(retry_path), binary):
        raise RuntimeError("Failed to write enhanced retry image")
    return retry_path


def pitch_to_note_label(pitch) -> str:
    """Convert music21 pitch to readable note name with octave (e.g., G3, Bb4)."""
    base_name = pitch.name.replace("-", "b")
    if pitch.octave is None:
        return base_name
    return f"{base_name}{int(pitch.octave)}"


def quarter_length_to_fraction(quarter_length: float) -> str:
    """Represent quarterLength as a whole-note fraction string (e.g., 1/4, 3/8)."""
    if quarter_length <= 0:
        return "0"
    whole_note_fraction = Fraction(quarter_length).limit_denominator(192) / 4
    if whole_note_fraction.denominator == 1:
        return str(whole_note_fraction.numerator)
    return f"{whole_note_fraction.numerator}/{whole_note_fraction.denominator}"


def element_to_concise_token(element) -> str | None:
    """Convert one music21 note/chord/rest element to a concise token."""
    duration = quarter_length_to_fraction(float(element.quarterLength))

    if element.isChord:
        pitches = sorted(list(element.pitches), key=lambda pitch: pitch.ps)
        pitch_labels = [pitch_to_note_label(pitch) for pitch in pitches]
        if not pitch_labels:
            return None
        if len(pitch_labels) == 1:
            return f"{pitch_labels[0]}:{duration}"
        return f"[{','.join(pitch_labels)}]:{duration}"

    if element.isNote:
        return f"{pitch_to_note_label(element.pitch)}:{duration}"

    if element.isRest:
        return f"R:{duration}"

    return None


def stream_to_concise_tokens(stream) -> list[str]:
    """Convert one ordered note/rest stream into concise tokens."""
    tokens: list[str] = []
    for element in stream.flatten().notesAndRests:
        token = element_to_concise_token(element)
        if token:
            tokens.append(token)
    return tokens


@dataclass(slots=True)
class VoiceEvent:
    token: str
    offset: Fraction
    duration: Fraction
    is_rest: bool


def _fraction_to_quarter_length(value: Fraction) -> float:
    return float(value)


def _duration_token_from_quarter_length(value: Fraction) -> str:
    return quarter_length_to_fraction(_fraction_to_quarter_length(value))


def _append_rest_event(events: list[VoiceEvent], offset: Fraction, duration: Fraction) -> None:
    if duration <= 0:
        return

    if events and events[-1].is_rest and events[-1].offset + events[-1].duration == offset:
        merged = events[-1]
        merged.duration += duration
        merged.token = f"R:{_duration_token_from_quarter_length(merged.duration)}"
        return

    events.append(
        VoiceEvent(
            token=f"R:{_duration_token_from_quarter_length(duration)}",
            offset=offset,
            duration=duration,
            is_rest=True,
        )
    )


def stream_to_voice_events(stream) -> list[VoiceEvent]:
    """
    Convert a stream into ordered events, filling offset gaps with rests.

    music21 can leave gaps implicit inside voices; representing them explicitly keeps
    duration totals comparable across voices without depending on the written meter.
    """
    events: list[VoiceEvent] = []
    current_offset = Fraction(0)

    for element in stream.flatten().notesAndRests:
        offset = Fraction(element.offset).limit_denominator(192)
        duration = Fraction(float(element.quarterLength)).limit_denominator(192)
        if duration <= 0:
            continue

        if offset > current_offset:
            _append_rest_event(events, current_offset, offset - current_offset)

        token = element_to_concise_token(element)
        if token is None:
            current_offset = max(current_offset, offset + duration)
            continue

        events.append(
            VoiceEvent(
                token=token,
                offset=offset,
                duration=duration,
                is_rest=bool(element.isRest),
            )
        )
        current_offset = max(current_offset, offset + duration)

    return events


def _voice_effective_end(events: list[VoiceEvent]) -> Fraction:
    """Return the end of the last non-rest event, or total rest length if the voice is silent."""
    for event in reversed(events):
        if not event.is_rest:
            return event.offset + event.duration
    if events:
        last_event = events[-1]
        return last_event.offset + last_event.duration
    return Fraction(0)


def _normalize_voice_events(events: list[VoiceEvent], target_duration: Fraction) -> list[str]:
    """Trim/pad one voice so all voices in a measure end at the same effective duration."""
    normalized: list[VoiceEvent] = []

    for event in events:
        if event.offset >= target_duration:
            break
        end = min(event.offset + event.duration, target_duration)
        clipped_duration = end - event.offset
        if clipped_duration <= 0:
            continue

        if event.is_rest:
            _append_rest_event(normalized, event.offset, clipped_duration)
            continue

        token_body = event.token.split(":", 1)[0]
        normalized.append(
            VoiceEvent(
                token=f"{token_body}:{_duration_token_from_quarter_length(clipped_duration)}",
                offset=event.offset,
                duration=clipped_duration,
                is_rest=False,
            )
        )

    current_duration = _voice_effective_end(normalized)
    if current_duration < target_duration:
        _append_rest_event(normalized, current_duration, target_duration - current_duration)

    return [event.token for event in normalized if event.duration > 0]


def normalize_measure_voice_token_groups(measure) -> list[list[str]]:
    """
    Build measure voice groups with equalized durations across voices.

    The target duration is the latest non-rest endpoint among voices in the measure,
    so output does not depend on the measure's written time signature.
    """
    voices = list(measure.getElementsByClass("Voice"))
    if not voices:
        tokens = stream_to_concise_tokens(measure)
        return [tokens] if tokens else []

    voice_events = [stream_to_voice_events(voice) for voice in voices]
    voice_events = [events for events in voice_events if events]
    if not voice_events:
        return []

    target_duration = max((_voice_effective_end(events) for events in voice_events), default=Fraction(0))
    normalized_groups = [
        _normalize_voice_events(events, target_duration)
        for events in voice_events
    ]
    return [group for group in normalized_groups if group]


def measure_to_voice_token_groups(measure) -> list[list[str]]:
    """
    Convert one measure into 1..N ordered voice token groups.

    Explicit music21 Voice objects are preserved. If the measure has no Voice
    wrappers, the measure is treated as a single voice.
    """
    return normalize_measure_voice_token_groups(measure)


def format_key_signature_accidentals(key_signature) -> str:
    """Format a key signature as an ordered accidental list like F#,C# or Bb,Eb."""
    sharps = getattr(key_signature, "sharps", None)
    if not sharps:
        return ""

    sharp_order = ["F#", "C#", "G#", "D#", "A#", "E#", "B#"]
    flat_order = ["Bb", "Eb", "Ab", "Db", "Gb", "Cb", "Fb"]
    if sharps > 0:
        return ",".join(sharp_order[:sharps])
    return ",".join(flat_order[: abs(sharps)])


def score_to_measure_voice_groups(score) -> list[tuple[str, str, list[list[str]]]]:
    """Collect measure-aligned voice groups and active key signature in score order."""
    parts = list(getattr(score, "parts", []))
    if not parts:
        measure_groups: list[tuple[str, str, list[list[str]]]] = []
        active_key_signature = ""
        for index, measure in enumerate(score.getElementsByClass("Measure"), start=1):
            key_signatures = list(measure.getElementsByClass("KeySignature"))
            if key_signatures:
                active_key_signature = format_key_signature_accidentals(key_signatures[0])
            voice_groups = measure_to_voice_token_groups(measure)
            if voice_groups:
                label = str(measure.number) if measure.number is not None else str(index)
                measure_groups.append((label, active_key_signature, voice_groups))
        return measure_groups

    part_measures = [list(part.getElementsByClass("Measure")) for part in parts]
    total_measures = max((len(measures) for measures in part_measures), default=0)
    measure_groups: list[tuple[str, str, list[list[str]]]] = []
    active_key_signature = ""

    for measure_index in range(total_measures):
        combined_voice_groups: list[list[str]] = []
        measure_label = str(measure_index + 1)
        measure_key_signature = ""

        for measures in part_measures:
            if measure_index >= len(measures):
                continue
            measure = measures[measure_index]
            if measure.number is not None:
                measure_label = str(measure.number)
            if not measure_key_signature:
                key_signatures = list(measure.getElementsByClass("KeySignature"))
                if key_signatures:
                    measure_key_signature = format_key_signature_accidentals(key_signatures[0])
            combined_voice_groups.extend(measure_to_voice_token_groups(measure))

        if measure_key_signature or any(
            measure_index < len(measures)
            and list(measures[measure_index].getElementsByClass("KeySignature"))
            for measures in part_measures
        ):
            active_key_signature = measure_key_signature

        if combined_voice_groups:
            measure_groups.append((measure_label, active_key_signature, combined_voice_groups))

    return measure_groups


def musicxml_to_concise_notes(musicxml_path: str | Path) -> str:
    """
    Build a measure-by-measure voice-preserving note encoding from MusicXML.

    Format:
    - one line per measure
    - optional `ks=` line before a measure only when the key signature changes
    - voices separated by ' || '
    - events inside each voice are space-separated NOTE:DURATION tokens

    Example:
    ks=F#,C#
    m1: v1=C5:1/4 D5:1/4 E5:1/4 F#5:1/4 || v2=A3:1/2 B3:1/2
    m2: v1=G5:1/4 A5:1/4 B5:1/4 C#6:1/4 || v2=...
    m9: v1=C5:1/4 B4:1/4 A4:1/4 G4:1/4
    """
    musicxml_path = Path(musicxml_path)
    converter = _music21_converter()

    try:
        score = converter.parse(str(musicxml_path))
        measure_voice_groups = score_to_measure_voice_groups(score)
        if measure_voice_groups:
            lines: list[str] = []
            last_emitted_key_signature: str | None = None
            for measure_label, key_signature, voice_groups in measure_voice_groups:
                encoded_voices = [
                    f"v{voice_index}=" + " ".join(tokens)
                    for voice_index, tokens in enumerate(voice_groups, start=1)
                ]
                measure_prefix: list[str] = []
                if key_signature and key_signature != last_emitted_key_signature:
                    measure_prefix.append(f"ks={key_signature}")
                last_emitted_key_signature = key_signature
                measure_prefix.append(f"m{measure_label}: " + " || ".join(encoded_voices))
                lines.append("\n".join(measure_prefix))
            return "\n".join(lines)

        tokens = stream_to_concise_tokens(score)
        if tokens:
            return " ".join(tokens)

        return "No note events detected."
    except Exception as exc:
        return f"Error building note output: {exc}"


def musicxml_to_midi(musicxml_path: str | Path, output_path: str | Path) -> Path:
    """Convert MusicXML to MIDI."""
    converter = _music21_converter()
    score = converter.parse(str(musicxml_path))
    output = Path(output_path)
    score.write("midi", fp=str(output))
    return output


def process_sheet_music_file(
    input_path: str | Path,
    output_dir: str | Path,
    progress_callback: Optional[ProgressCallback] = None,
) -> ProcessingResult:
    """Process one uploaded file and return generated assets."""
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log: list[str] = []

    def emit(stage: str, progress: float, message: str) -> None:
        if not log or log[-1] != message:
            log.append(message)
        if progress_callback:
            progress_callback(stage, progress, message)

    suffix = input_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise RuntimeError(
            f"Unsupported file format: {suffix or 'unknown'}. "
            "Please upload JPG, PNG, or PDF."
        )

    emit("preparing", 0.1, "Preparing input file")
    emit("preparing", 0.16, "Preparing input file")

    if suffix == ".pdf":
        emit("preparing", 0.22, "Converting PDF pages")
        pages = convert_pdf_to_images(input_path, output_dir)
        if not pages:
            raise RuntimeError("No pages were found in the uploaded PDF")
        process_image = pages[0]
        preview_path = process_image
        log.append("Converted PDF page 1 to an image for recognition")
        emit("preparing", 0.3, "Preparing input file")
    else:
        process_image = input_path
        preview_path = input_path
        emit("preparing", 0.24, "Preparing input file")

    emit("recognizing", 0.34, "Running optical music recognition")
    emit("recognizing", 0.46, "Running optical music recognition")
    musicxml_path = process_with_homr(process_image, output_dir)
    emit("recognizing", 0.62, "Running optical music recognition")

    emit("converting_notes", 0.8, "Generating note sequence")
    concise_notes_text = musicxml_to_concise_notes(musicxml_path)
    emit("converting_notes", 0.82, "Generating note sequence")

    emit("converting_midi", 0.83, "Converting MusicXML to MIDI")
    midi_path: Optional[Path] = output_dir / "output.mid"
    try:
        musicxml_to_midi(musicxml_path, midi_path)
    except Exception as exc:
        log.append(f"MIDI conversion warning: {exc}")
        midi_path = None

    emit("converting_midi", 0.9, "Converting MusicXML to MIDI")
    emit("packaging", 0.94, "Packaging output files")

    return ProcessingResult(
        concise_notes_text=concise_notes_text,
        musicxml_path=musicxml_path,
        midi_path=midi_path,
        preview_path=preview_path,
        log=log,
    )
