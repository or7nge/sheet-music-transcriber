#!/usr/bin/env python3
"""Core transcription utilities shared by the web server and legacy UIs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
import os
import shutil
import subprocess

from music21 import converter
from pdf2image import convert_from_path


ProgressCallback = Callable[[str, float, str], None]

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
DEFAULT_HOMR_DIR = Path("/Users/andrew/Documents/git/homr")


@dataclass(slots=True)
class ProcessingResult:
    abc_text: str
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
    image_path = Path(image_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    homr_dir = resolve_homr_dir()
    if not homr_dir.exists():
        raise RuntimeError(f"homr directory not found: {homr_dir}")

    try:
        result = subprocess.run(
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

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or "Unknown homr error"
        raise RuntimeError(f"homr processing failed: {details}")

    # homr writes output next to the source image.
    generated_musicxml = image_path.with_suffix(".musicxml")
    if not generated_musicxml.exists():
        raise RuntimeError("homr finished but no MusicXML file was generated")

    # Keep artifacts inside output_dir for predictable server downloads.
    destination = output_dir / "score.musicxml"
    if generated_musicxml.resolve() != destination.resolve():
        shutil.copy2(generated_musicxml, destination)
    else:
        destination = generated_musicxml

    return destination


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
        abc_lines.append("% Simplified chord list (letter names only):")
        simplified_chords: list[str] = []
        for measure in chordified.getElementsByClass("Measure"):
            for element in measure.flatten().notesAndRests:
                if element.isChord:
                    pitches = sorted(list(element.pitches), key=lambda pitch: pitch.ps)
                    simplified_chords.append("".join([pitch.step for pitch in pitches]))

        if simplified_chords:
            abc_lines.append(" | ".join(simplified_chords))

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
        log.append(message)
        if progress_callback:
            progress_callback(stage, progress, message)

    suffix = input_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise RuntimeError(
            f"Unsupported file format: {suffix or 'unknown'}. "
            "Please upload JPG, PNG, or PDF."
        )

    emit("preparing", 0.12, "Preparing input file")

    if suffix == ".pdf":
        emit("preparing", 0.2, "Converting PDF pages")
        pages = convert_pdf_to_images(input_path, output_dir)
        if not pages:
            raise RuntimeError("No pages were found in the uploaded PDF")
        process_image = pages[0]
        preview_path = process_image
        log.append(f"Detected {len(pages)} PDF page(s); processing page 1")
    else:
        process_image = input_path
        preview_path = input_path

    emit("recognizing", 0.5, "Running optical music recognition")
    musicxml_path = process_with_homr(process_image, output_dir)

    emit("converting_abc", 0.72, "Converting MusicXML to ABC")
    abc_text = musicxml_to_abc(musicxml_path)

    emit("converting_midi", 0.86, "Converting MusicXML to MIDI")
    midi_path: Optional[Path] = output_dir / "score.mid"
    try:
        musicxml_to_midi(musicxml_path, midi_path)
    except Exception as exc:
        log.append(f"MIDI conversion warning: {exc}")
        midi_path = None

    emit("packaging", 0.95, "Packaging output files")

    return ProcessingResult(
        abc_text=abc_text,
        musicxml_path=musicxml_path,
        midi_path=midi_path,
        preview_path=preview_path,
        log=log,
    )
