#!/usr/bin/env python3
"""Core transcription utilities shared by the web server and legacy UIs."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable, Optional
import os
import shutil
import subprocess

import cv2
from music21 import converter
import numpy as np
from pdf2image import convert_from_path


ProgressCallback = Callable[[str, float, str], None]

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
DEFAULT_HOMR_DIR = Path("/Users/andrew/Documents/git/homr")


@dataclass(slots=True)
class ProcessingResult:
    abc_text: str
    concise_notes_text: str
    musicxml_path: Path
    midi_path: Optional[Path]
    preview_path: Optional[Path]
    log: list[str]


def resolve_homr_dir() -> Path:
    """Resolve homr working directory with env override."""
    env_override = os.environ.get("HOMR_DIR")
    if env_override:
        return Path(env_override).expanduser()

    sibling_candidate = Path.cwd().parent / "homr"
    if sibling_candidate.exists():
        return sibling_candidate

    return DEFAULT_HOMR_DIR


def check_homr_installation() -> bool:
    """Check whether homr is callable from the configured directory."""
    homr_dir = resolve_homr_dir()
    if not homr_dir.exists():
        return False

    try:
        result = subprocess.run(
            ["poetry", "run", "homr", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=homr_dir,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def convert_pdf_to_images(pdf_path: str | Path, output_dir: str | Path) -> list[Path]:
    """Convert each PDF page to JPEG and return output paths."""
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        images = convert_from_path(str(pdf_path), dpi=300)
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


def musicxml_to_abc(musicxml_path: str | Path) -> str:
    """Convert MusicXML to a readable ABC representation."""
    musicxml_path = Path(musicxml_path)

    try:
        score = converter.parse(str(musicxml_path))

        abc_lines: list[str] = [
            "X:1",
            "T:Transcribed Sheet Music",
            "M:4/4",
            "L:1/4",
            "K:C",
            "",
            "% Standard ABC notation (with octaves):",
            "",
        ]

        if score.metadata and score.metadata.title:
            abc_lines[1] = f"T:{score.metadata.title}"

        time_signatures = score.recurse().getElementsByClass("TimeSignature")
        if time_signatures:
            time_signature = time_signatures[0]
            abc_lines[2] = f"M:{time_signature.numerator}/{time_signature.denominator}"

        key_signatures = score.recurse().getElementsByClass("KeySignature")
        if key_signatures:
            key_obj = key_signatures[0].asKey()
            tonic = key_obj.tonic.name
            abc_lines[4] = f"K:{tonic}m" if key_obj.mode == "minor" else f"K:{tonic}"

        try:
            chordified = score.chordify()
        except Exception:
            return "\n".join(
                abc_lines
                + [
                    "% Could not properly analyze chords",
                    "% Use MusicXML output for accurate representation",
                ]
            )

        for measure in chordified.getElementsByClass("Measure"):
            measure_items: list[str] = []
            for element in measure.flatten().notesAndRests:
                if element.isChord:
                    pitches = sorted(list(element.pitches), key=lambda pitch: pitch.ps)
                    chord_notes = [pitch_to_abc(pitch) for pitch in pitches]
                    duration = duration_to_abc(element.quarterLength)
                    if len(pitches) > 1:
                        measure_items.append("[" + "".join(chord_notes) + "]" + duration)
                    else:
                        measure_items.append(chord_notes[0] + duration)
                elif element.isNote:
                    measure_items.append(
                        pitch_to_abc(element.pitch) + duration_to_abc(element.quarterLength)
                    )
                elif element.isRest:
                    measure_items.append("z" + duration_to_abc(element.quarterLength))

            if measure_items:
                abc_lines.append(" ".join(measure_items) + " |")

        abc_lines.append("")
        abc_lines.append("% Simplified chord/note list (pitch + octave):")
        simplified_events: list[str] = []
        for measure in chordified.getElementsByClass("Measure"):
            for element in measure.flatten().notesAndRests:
                if element.isChord:
                    pitches = sorted(list(element.pitches), key=lambda pitch: pitch.ps)
                    pitch_labels = [pitch_to_note_label(pitch) for pitch in pitches]
                    if pitch_labels:
                        simplified_events.append("/".join(pitch_labels))
                elif element.isNote:
                    simplified_events.append(pitch_to_note_label(element.pitch))

        if simplified_events:
            abc_lines.append(" | ".join(simplified_events))

        return "\n".join(abc_lines)

    except Exception as exc:
        return (
            "Error converting to ABC: "
            f"{exc}\n\n"
            "(ABC conversion is experimental - use MusicXML for best results)"
        )


def pitch_to_abc(pitch, simple_letters: bool = True) -> str:
    """Convert music21 pitch to ABC notation."""
    note_name = pitch.step if simple_letters else pitch.name.replace("-", "_").replace("#", "^")
    octave = pitch.octave

    if octave >= 5:
        abc_note = note_name.lower() + ("'" * (octave - 5))
    elif octave == 4:
        abc_note = note_name.upper()
    else:
        abc_note = note_name.upper() + ("," * (4 - octave))

    return abc_note


def pitch_to_note_label(pitch) -> str:
    """Convert music21 pitch to readable note name with octave (e.g., G3, Bb4)."""
    base_name = pitch.name.replace("-", "b")
    if pitch.octave is None:
        return base_name
    return f"{base_name}{int(pitch.octave)}"


def duration_to_abc(quarter_length: float) -> str:
    """Convert music21 quarterLength to ABC duration syntax."""
    if quarter_length == 4:
        return "4"
    if quarter_length == 3:
        return "3"
    if quarter_length == 2:
        return "2"
    if quarter_length == 1.5:
        return "3/2"
    if quarter_length == 1:
        return ""
    if quarter_length == 0.75:
        return "3/4"
    if quarter_length == 0.5:
        return "/2"
    if quarter_length == 0.25:
        return "/4"

    if quarter_length > 1 and quarter_length == int(quarter_length):
        return str(int(quarter_length))
    if quarter_length < 1 and (1 / quarter_length) == int(1 / quarter_length):
        return f"/{int(1 / quarter_length)}"
    return str(quarter_length)


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


def musicxml_to_concise_notes(musicxml_path: str | Path) -> str:
    """
    Build an ordered concise note stream from MusicXML.
    Format: NOTE_OR_CHORD:DURATION, with measures separated by '|'.
    Examples: C4:1/4, [C4,E4,G4]:1/2, R:1/8
    """
    musicxml_path = Path(musicxml_path)

    try:
        score = converter.parse(str(musicxml_path))
        try:
            ordered_score = score.chordify()
        except Exception:
            ordered_score = score

        measure_chunks: list[str] = []
        for measure in ordered_score.getElementsByClass("Measure"):
            tokens: list[str] = []
            for element in measure.flatten().notesAndRests:
                token = element_to_concise_token(element)
                if token:
                    tokens.append(token)
            if tokens:
                measure_chunks.append(" ".join(tokens))

        if measure_chunks:
            return " | ".join(measure_chunks)

        # Fallback when score has no measure wrappers.
        tokens: list[str] = []
        for element in ordered_score.flatten().notesAndRests:
            token = element_to_concise_token(element)
            if token:
                tokens.append(token)
        if tokens:
            return " ".join(tokens)

        return "No note events detected."
    except Exception as exc:
        return f"Error building concise note output: {exc}"


def musicxml_to_midi(musicxml_path: str | Path, output_path: str | Path) -> Path:
    """Convert MusicXML to MIDI."""
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
        log.append(f"Detected {len(pages)} PDF page(s); processing page 1")
        emit("preparing", 0.3, "Preparing input file")
    else:
        process_image = input_path
        preview_path = input_path
        emit("preparing", 0.24, "Preparing input file")

    emit("recognizing", 0.34, "Running optical music recognition")
    emit("recognizing", 0.46, "Running optical music recognition")
    musicxml_path = process_with_homr(process_image, output_dir)
    emit("recognizing", 0.62, "Running optical music recognition")

    emit("converting_abc", 0.68, "Converting MusicXML to ABC")
    abc_text = musicxml_to_abc(musicxml_path)
    emit("converting_abc", 0.78, "Converting MusicXML to ABC")
    emit("converting_notes", 0.8, "Generating concise note sequence")
    concise_notes_text = musicxml_to_concise_notes(musicxml_path)
    emit("converting_notes", 0.82, "Generating concise note sequence")

    emit("converting_midi", 0.83, "Converting MusicXML to MIDI")
    midi_path: Optional[Path] = output_dir / "score.mid"
    try:
        musicxml_to_midi(musicxml_path, midi_path)
    except Exception as exc:
        log.append(f"MIDI conversion warning: {exc}")
        midi_path = None

    emit("converting_midi", 0.9, "Converting MusicXML to MIDI")
    emit("packaging", 0.94, "Packaging output files")

    return ProcessingResult(
        abc_text=abc_text,
        concise_notes_text=concise_notes_text,
        musicxml_path=musicxml_path,
        midi_path=midi_path,
        preview_path=preview_path,
        log=log,
    )
