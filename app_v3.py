#!/usr/bin/env python3
"""
Sheet Music Transcriber - Minimal Edition
Clean, sophisticated design inspired by Apple/Stripe
"""

import gradio as gr
import tempfile
import os
from pathlib import Path
import subprocess
import shutil
from typing import Tuple, Optional
import sys

# Import existing processing functions
from app import (
    check_homr_installation,
    convert_pdf_to_images,
    process_with_homr,
    musicxml_to_abc,
    musicxml_to_midi,
)


def process_sheet_music_v3(file) -> Tuple[str, str, str, str]:
    """
    Minimal processing function.
    Returns: (abc_text, midi_path, musicxml_path, status_message)
    """
    if file is None:
        return "", None, None, "Upload a file to begin"

    if not check_homr_installation():
        return "", None, None, "Error: homr not installed. See terminal for instructions."

    temp_dir = tempfile.mkdtemp()

    try:
        file_path = file.name
        file_ext = os.path.splitext(file_path)[1].lower()

        # Handle PDF conversion
        if file_ext == '.pdf':
            try:
                image_paths = convert_pdf_to_images(file_path, temp_dir)
                if not image_paths:
                    return "", None, None, "No pages found in PDF"
                process_image = image_paths[0]
            except Exception as e:
                return "", None, None, f"PDF conversion failed: {str(e)}"

        elif file_ext in ['.jpg', '.jpeg', '.png']:
            process_image = file_path

        else:
            return "", None, None, f"Unsupported format. Use JPG, PNG, or PDF"

        # Process with homr
        try:
            musicxml_path = process_with_homr(process_image, temp_dir)
        except Exception as e:
            return "", None, None, f"Recognition failed. Try a clearer image."

        # Convert to ABC
        try:
            abc_text = musicxml_to_abc(musicxml_path)
        except Exception as e:
            abc_text = f"ABC conversion error"

        # Convert to MIDI
        midi_path = os.path.join(temp_dir, "output.mid")
        try:
            musicxml_to_midi(musicxml_path, midi_path)
        except Exception as e:
            midi_path = None

        # Copy files
        output_dir = tempfile.gettempdir()
        final_musicxml = os.path.join(output_dir, "output.musicxml")
        final_midi = os.path.join(output_dir, "output.mid") if midi_path else None

        shutil.copy(musicxml_path, final_musicxml)
        if midi_path and os.path.exists(midi_path):
            shutil.copy(midi_path, final_midi)

        return abc_text, final_midi, final_musicxml, "Complete"

    except Exception as e:
        return "", None, None, f"Error: {str(e)}"

    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


# Minimal, sophisticated CSS
MINIMAL_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
@import url('https://fonts.googleapis.com/css2?family=SF+Mono:wght@400;500&family=JetBrains+Mono:wght@400&display=swap');

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

:root {
    --gray-50: #fafafa;
    --gray-100: #f5f5f5;
    --gray-200: #e5e5e5;
    --gray-300: #d4d4d4;
    --gray-400: #a3a3a3;
    --gray-500: #737373;
    --gray-600: #525252;
    --gray-700: #404040;
    --gray-800: #262626;
    --gray-900: #171717;
    --blue: #0066ff;
    --blue-light: #3388ff;
    --radius: 12px;
    --shadow: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02);
    --shadow-lg: 0 4px 6px rgba(0,0,0,0.05), 0 2px 4px rgba(0,0,0,0.03);
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #ffffff;
    color: var(--gray-900);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

.gradio-container {
    max-width: 1200px !important;
    margin: 0 auto !important;
    padding: 80px 40px !important;
    background: transparent !important;
}

/* Typography */
h1, h2, h3, h4, h5, h6 {
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.2;
}

/* Header */
.minimal-header {
    text-align: center;
    margin-bottom: 80px;
}

.minimal-header h1 {
    font-size: 56px;
    font-weight: 600;
    color: var(--gray-900);
    margin-bottom: 16px;
    letter-spacing: -0.03em;
}

.minimal-header p {
    font-size: 20px;
    color: var(--gray-500);
    font-weight: 400;
    max-width: 600px;
    margin: 0 auto;
    line-height: 1.5;
}

/* Upload area */
.upload-container {
    margin-bottom: 40px;
}

.upload-box {
    background: var(--gray-50);
    border: 1.5px dashed var(--gray-300);
    border-radius: var(--radius);
    padding: 48px 32px;
    text-align: center;
    transition: all 0.2s ease;
    cursor: pointer;
}

.upload-box:hover {
    background: var(--gray-100);
    border-color: var(--gray-400);
}

/* Button */
.transcribe-btn {
    background: var(--gray-900) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 14px 32px !important;
    font-size: 15px !important;
    font-weight: 500 !important;
    transition: all 0.15s ease !important;
    width: 100%;
    letter-spacing: -0.01em;
}

.transcribe-btn:hover {
    background: var(--gray-800) !important;
    transform: translateY(-1px);
    box-shadow: var(--shadow-lg);
}

.transcribe-btn:active {
    transform: translateY(0);
}

/* Status */
.status-text {
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: var(--radius);
    padding: 20px;
    font-size: 14px;
    color: var(--gray-600);
    font-family: 'JetBrains Mono', 'SF Mono', monospace;
    line-height: 1.6;
}

/* Output section */
.output-section {
    margin-top: 60px;
}

.output-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 24px;
    margin-top: 32px;
}

.output-card {
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: var(--radius);
    padding: 24px;
    transition: all 0.2s ease;
}

.output-card:hover {
    border-color: var(--gray-300);
    box-shadow: var(--shadow-lg);
}

/* Tabs */
.tab-container {
    border-bottom: 1px solid var(--gray-200);
    margin-bottom: 32px;
}

button[role="tab"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    color: var(--gray-500) !important;
    padding: 12px 0 !important;
    margin: 0 24px 0 0 !important;
    font-size: 15px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}

button[role="tab"]:hover {
    color: var(--gray-900) !important;
}

button[role="tab"][aria-selected="true"] {
    color: var(--gray-900) !important;
    border-bottom-color: var(--gray-900) !important;
}

/* Textbox */
textarea {
    background: var(--gray-50) !important;
    border: 1px solid var(--gray-200) !important;
    border-radius: var(--radius) !important;
    color: var(--gray-900) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px !important;
    line-height: 1.6 !important;
    padding: 16px !important;
    resize: vertical !important;
}

textarea:focus {
    outline: none !important;
    border-color: var(--gray-400) !important;
    background: white !important;
}

/* File component */
.file-component {
    background: var(--gray-50) !important;
    border: 1px solid var(--gray-200) !important;
    border-radius: var(--radius) !important;
    padding: 16px !important;
}

/* Labels */
label {
    color: var(--gray-700) !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    margin-bottom: 8px !important;
    letter-spacing: -0.01em !important;
}

/* Footer */
.minimal-footer {
    text-align: center;
    margin-top: 80px;
    padding-top: 40px;
    border-top: 1px solid var(--gray-200);
    color: var(--gray-500);
    font-size: 14px;
    line-height: 1.6;
}

.minimal-footer a {
    color: var(--gray-900);
    text-decoration: none;
    border-bottom: 1px solid var(--gray-300);
    transition: border-color 0.2s ease;
}

.minimal-footer a:hover {
    border-bottom-color: var(--gray-900);
}

/* Remove Gradio branding */
.gradio-container .footer {
    display: none !important;
}

/* Clean scrollbar */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: var(--gray-300);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--gray-400);
}

/* Spacing utilities */
.mt-1 { margin-top: 8px; }
.mt-2 { margin-top: 16px; }
.mt-3 { margin-top: 24px; }
.mt-4 { margin-top: 32px; }
.mb-1 { margin-bottom: 8px; }
.mb-2 { margin-bottom: 16px; }
.mb-3 { margin-bottom: 24px; }
.mb-4 { margin-bottom: 32px; }

/* Remove unnecessary decorations */
.prose {
    color: var(--gray-600);
    font-size: 14px;
    line-height: 1.6;
}

.prose strong {
    color: var(--gray-900);
    font-weight: 500;
}

/* Responsive */
@media (max-width: 768px) {
    .gradio-container {
        padding: 40px 20px !important;
    }

    .minimal-header h1 {
        font-size: 36px;
    }

    .minimal-header p {
        font-size: 16px;
    }

    .output-grid {
        grid-template-columns: 1fr;
    }
}
"""


def create_minimal_ui():
    """Create minimal, sophisticated UI."""

    with gr.Blocks(css=MINIMAL_CSS, title="Sheet Music Transcriber") as demo:

        # Header
        gr.HTML("""
            <div class="minimal-header">
                <h1>Sheet Music Transcriber</h1>
                <p>Upload sheet music and get ABC notation, MIDI, and MusicXML in seconds</p>
            </div>
        """)

        # Upload section
        with gr.Column(elem_classes="upload-container"):
            file_input = gr.File(
                label="Upload Image or PDF",
                file_types=[".jpg", ".jpeg", ".png", ".pdf"],
                type="filepath",
                elem_classes="upload-box"
            )

            process_btn = gr.Button(
                "Transcribe",
                elem_classes="transcribe-btn"
            )

            status_output = gr.Textbox(
                label="Status",
                lines=2,
                interactive=False,
                placeholder="Ready",
                elem_classes="status-text"
            )

        # Output section
        gr.HTML('<div class="output-section"></div>')

        with gr.Tabs(elem_classes="tab-container"):
            with gr.Tab("ABC Notation"):
                abc_output = gr.Textbox(
                    label="",
                    lines=18,
                    interactive=False,
                    buttons=["copy"],
                    placeholder="ABC notation will appear here..."
                )

            with gr.Tab("MIDI"):
                midi_output = gr.File(
                    label="Download MIDI File",
                    elem_classes="file-component"
                )

            with gr.Tab("MusicXML"):
                musicxml_output = gr.File(
                    label="Download MusicXML File",
                    elem_classes="file-component"
                )

        # Footer
        gr.HTML("""
            <div class="minimal-footer">
                <p>
                    Powered by <a href="https://github.com/liebharc/homr" target="_blank">homr</a>
                    and <a href="https://web.mit.edu/music21/" target="_blank">music21</a>
                </p>
                <p style="margin-top: 12px; font-size: 13px;">
                    Results may contain errors. Use high-resolution images for best accuracy.
                </p>
            </div>
        """)

        # Events
        process_btn.click(
            fn=process_sheet_music_v3,
            inputs=[file_input],
            outputs=[abc_output, midi_output, musicxml_output, status_output]
        )

    return demo


if __name__ == "__main__":
    print("Sheet Music Transcriber")
    print("Starting server at http://127.0.0.1:7860")
    print("")

    if not check_homr_installation():
        print("Warning: homr not installed")
        print("Install: cd homr && poetry install --only main && poetry run homr --init")
        print("")

    demo = create_minimal_ui()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False
    )
