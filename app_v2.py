#!/usr/bin/env python3
"""
Sheet Music Transcriber - Premium Edition
Beautiful custom UI with advanced features
"""

import gradio as gr
import tempfile
import os
from pathlib import Path
import subprocess
import shutil
from typing import Tuple, Optional
import sys
import base64

# Import existing processing functions
from app import (
    check_homr_installation,
    convert_pdf_to_images,
    process_with_homr,
    musicxml_to_abc,
    musicxml_to_midi,
)


def process_sheet_music_v2(file) -> Tuple[str, str, str, str, str]:
    """
    Enhanced processing function with image preview.
    Returns: (abc_text, midi_path, musicxml_path, status_message, preview_image)
    """
    if file is None:
        return "", None, None, "❌ Please upload a file", None

    # Check homr installation
    if not check_homr_installation():
        return "", None, None, (
            "❌ homr is not installed!\n\n"
            "Please install homr:\n"
            "1. Clone: git clone https://github.com/liebharc/homr.git\n"
            "2. cd homr\n"
            "3. poetry install --only main\n"
            "4. poetry run homr --init\n"
            "5. Return to this directory and run the app"
        ), None

    temp_dir = tempfile.mkdtemp()
    preview_image = None

    try:
        file_path = file.name
        file_ext = os.path.splitext(file_path)[1].lower()

        # Handle PDF conversion
        if file_ext == '.pdf':
            status = "📄 Converting PDF to images..."
            try:
                image_paths = convert_pdf_to_images(file_path, temp_dir)
                if not image_paths:
                    return "", None, None, "❌ No pages found in PDF", None
                process_image = image_paths[0]
                preview_image = process_image
                status += f" {len(image_paths)} page(s) found. Processing first page...\n"
            except Exception as e:
                return "", None, None, f"❌ PDF conversion failed: {str(e)}", None

        elif file_ext in ['.jpg', '.jpeg', '.png']:
            process_image = file_path
            preview_image = file_path
            status = "🎼 Processing sheet music...\n"

        else:
            return "", None, None, f"❌ Unsupported file format: {file_ext}", None

        # Process with homr
        try:
            musicxml_path = process_with_homr(process_image, temp_dir)
            status += "✓ MusicXML generated\n"
        except Exception as e:
            return "", None, None, f"❌ OMR failed: {str(e)}\n\nTip: Ensure the image is clear and well-lit.", preview_image

        # Convert to ABC
        try:
            abc_text = musicxml_to_abc(musicxml_path)
            status += "✓ ABC notation generated\n"
        except Exception as e:
            abc_text = f"Error: {str(e)}"
            status += "⚠ ABC conversion failed\n"

        # Convert to MIDI
        midi_path = os.path.join(temp_dir, "output.mid")
        try:
            musicxml_to_midi(musicxml_path, midi_path)
            status += "✓ MIDI generated\n"
        except Exception as e:
            midi_path = None
            status += f"⚠ MIDI conversion failed: {str(e)}\n"

        # Copy files to persistent location
        output_dir = tempfile.gettempdir()
        final_musicxml = os.path.join(output_dir, "output.musicxml")
        final_midi = os.path.join(output_dir, "output.mid") if midi_path else None

        shutil.copy(musicxml_path, final_musicxml)
        if midi_path and os.path.exists(midi_path):
            shutil.copy(midi_path, final_midi)

        status += "\n✅ Processing complete!"

        return abc_text, final_midi, final_musicxml, status, preview_image

    except Exception as e:
        return "", None, None, f"❌ Unexpected error: {str(e)}", preview_image

    finally:
        # Cleanup
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


# Custom CSS for premium look
CUSTOM_CSS = """
/* Import Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* Root variables */
:root {
    --primary-color: #6366f1;
    --primary-dark: #4f46e5;
    --primary-light: #818cf8;
    --accent-color: #ec4899;
    --success-color: #10b981;
    --warning-color: #f59e0b;
    --error-color: #ef4444;
    --bg-primary: #0f172a;
    --bg-secondary: #1e293b;
    --bg-tertiary: #334155;
    --text-primary: #f1f5f9;
    --text-secondary: #cbd5e1;
    --text-muted: #94a3b8;
    --border-color: #334155;
    --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
    --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
    --shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1);
    --shadow-glow: 0 0 30px rgba(99, 102, 241, 0.3);
}

/* Global styles */
* {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

body {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: var(--text-primary);
}

.gradio-container {
    max-width: 1400px !important;
    margin: 0 auto !important;
    background: transparent !important;
}

/* Header styling */
.header-container {
    text-align: center;
    padding: 3rem 2rem 2rem;
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(236, 72, 153, 0.1) 100%);
    border-radius: 24px;
    margin-bottom: 2rem;
    border: 1px solid rgba(99, 102, 241, 0.2);
    box-shadow: var(--shadow-xl);
}

.header-title {
    font-size: 3rem;
    font-weight: 700;
    background: linear-gradient(135deg, #6366f1 0%, #ec4899 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.5rem;
    letter-spacing: -0.02em;
}

.header-subtitle {
    font-size: 1.125rem;
    color: var(--text-secondary);
    font-weight: 400;
}

/* Card styling */
.custom-card {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 16px !important;
    padding: 1.5rem !important;
    box-shadow: var(--shadow-lg) !important;
    transition: all 0.3s ease !important;
}

.custom-card:hover {
    border-color: var(--primary-color) !important;
    box-shadow: var(--shadow-glow) !important;
    transform: translateY(-2px);
}

/* Upload area */
.upload-area {
    background: var(--bg-tertiary) !important;
    border: 2px dashed var(--border-color) !important;
    border-radius: 16px !important;
    padding: 3rem 2rem !important;
    text-align: center !important;
    transition: all 0.3s ease !important;
    cursor: pointer !important;
}

.upload-area:hover {
    border-color: var(--primary-color) !important;
    background: rgba(99, 102, 241, 0.05) !important;
}

/* Buttons */
.primary-button {
    background: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-dark) 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 0.875rem 2rem !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    box-shadow: var(--shadow-lg) !important;
    transition: all 0.3s ease !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}

.primary-button:hover {
    transform: translateY(-2px) !important;
    box-shadow: var(--shadow-xl), var(--shadow-glow) !important;
}

/* Textbox styling */
textarea, input {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 12px !important;
    color: var(--text-primary) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.875rem !important;
    padding: 1rem !important;
}

textarea:focus, input:focus {
    border-color: var(--primary-color) !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1) !important;
    outline: none !important;
}

/* Tabs */
.tab-nav {
    background: var(--bg-secondary) !important;
    border-radius: 12px !important;
    padding: 0.5rem !important;
    border: 1px solid var(--border-color) !important;
}

button[role="tab"] {
    background: transparent !important;
    color: var(--text-secondary) !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.625rem 1.25rem !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}

button[role="tab"][aria-selected="true"] {
    background: var(--primary-color) !important;
    color: white !important;
}

button[role="tab"]:hover {
    background: rgba(99, 102, 241, 0.1) !important;
}

/* Status box */
.status-box {
    background: var(--bg-tertiary) !important;
    border-left: 4px solid var(--primary-color) !important;
    border-radius: 8px !important;
    padding: 1rem 1.25rem !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.875rem !important;
}

/* File download buttons */
.download-button {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 12px !important;
    padding: 1rem !important;
    transition: all 0.3s ease !important;
}

.download-button:hover {
    border-color: var(--success-color) !important;
    background: rgba(16, 185, 129, 0.1) !important;
}

/* Image preview */
.image-preview {
    border-radius: 16px !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-lg) !important;
    border: 1px solid var(--border-color) !important;
}

/* Footer */
.footer-info {
    text-align: center;
    padding: 2rem;
    color: var(--text-muted);
    font-size: 0.875rem;
    border-top: 1px solid var(--border-color);
    margin-top: 3rem;
}

.footer-link {
    color: var(--primary-light);
    text-decoration: none;
    transition: color 0.2s ease;
}

.footer-link:hover {
    color: var(--primary-color);
}

/* Label styling */
label {
    color: var(--text-secondary) !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    margin-bottom: 0.5rem !important;
}

/* Animations */
@keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 20px rgba(99, 102, 241, 0.3); }
    50% { box-shadow: 0 0 40px rgba(99, 102, 241, 0.6); }
}

.processing {
    animation: pulse-glow 2s ease-in-out infinite;
}

/* Scrollbar */
::-webkit-scrollbar {
    width: 10px;
}

::-webkit-scrollbar-track {
    background: var(--bg-secondary);
}

::-webkit-scrollbar-thumb {
    background: var(--bg-tertiary);
    border-radius: 5px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--primary-color);
}

/* Responsive */
@media (max-width: 768px) {
    .header-title {
        font-size: 2rem;
    }

    .custom-card {
        padding: 1rem !important;
    }
}
"""


def create_premium_ui():
    """Create premium custom UI."""

    with gr.Blocks(css=CUSTOM_CSS, title="Sheet Music Transcriber Pro") as demo:
        # Header
        with gr.Row():
            gr.HTML("""
                <div class="header-container">
                    <h1 class="header-title">🎹 Sheet Music Transcriber</h1>
                    <p class="header-subtitle">Transform handwritten or printed sheet music into digital formats using AI</p>
                </div>
            """)

        # Main content
        with gr.Row():
            # Left column - Input
            with gr.Column(scale=1, elem_classes="custom-card"):
                gr.Markdown("### 📤 Upload")
                file_input = gr.File(
                    label="Drop your sheet music here",
                    file_types=[".jpg", ".jpeg", ".png", ".pdf"],
                    type="filepath",
                    elem_classes="upload-area"
                )

                process_btn = gr.Button(
                    "🎵 Transcribe Music",
                    variant="primary",
                    size="lg",
                    elem_classes="primary-button"
                )

                gr.Markdown("### 📊 Status")
                status_output = gr.Textbox(
                    label="Processing Status",
                    lines=10,
                    interactive=False,
                    placeholder="Upload a file and click Transcribe to begin...",
                    elem_classes="status-box"
                )

                gr.Markdown("### 🖼️ Preview")
                preview_image = gr.Image(
                    label="Uploaded Image",
                    type="filepath",
                    interactive=False,
                    elem_classes="image-preview"
                )

            # Right column - Output
            with gr.Column(scale=1, elem_classes="custom-card"):
                gr.Markdown("### 🎼 Output Formats")

                with gr.Tabs():
                    with gr.Tab("📝 ABC Notation"):
                        gr.Markdown("""
                            <div style="padding: 1rem; background: rgba(99, 102, 241, 0.1); border-radius: 8px; margin-bottom: 1rem;">
                                <strong>💡 Quick Guide:</strong><br>
                                • Standard ABC shows octaves: [B,DFB]<br>
                                • Simplified list shows just letters: BDFB<br>
                                • Copy and paste into ABC editors
                            </div>
                        """)
                        abc_output = gr.Textbox(
                            label="ABC Notation",
                            lines=20,
                            interactive=False,
                            buttons=["copy"],
                            placeholder="ABC notation will appear here..."
                        )

                    with gr.Tab("🎹 MIDI"):
                        gr.Markdown("""
                            <div style="padding: 1rem; background: rgba(16, 185, 129, 0.1); border-radius: 8px; margin-bottom: 1rem;">
                                <strong>💡 MIDI File:</strong><br>
                                • Import into DAWs (Logic, Ableton, FL Studio)<br>
                                • Play in music software<br>
                                • Edit and arrange digitally
                            </div>
                        """)
                        midi_output = gr.File(
                            label="Download MIDI",
                            elem_classes="download-button"
                        )

                    with gr.Tab("📄 MusicXML"):
                        gr.Markdown("""
                            <div style="padding: 1rem; background: rgba(236, 72, 153, 0.1); border-radius: 8px; margin-bottom: 1rem;">
                                <strong>💡 MusicXML File:</strong><br>
                                • Open in MuseScore, Finale, Sibelius<br>
                                • Most accurate notation format<br>
                                • Professional editing and printing
                            </div>
                        """)
                        musicxml_output = gr.File(
                            label="Download MusicXML",
                            elem_classes="download-button"
                        )

        # Footer
        gr.HTML("""
            <div class="footer-info">
                <p>
                    <strong>⚠️ Beta Software:</strong> Results may contain errors, especially on complex or handwritten scores.<br>
                    <strong>💡 Best Results:</strong> Use high-resolution (300 DPI), well-lit images of printed sheet music.
                </p>
                <p style="margin-top: 1rem;">
                    Powered by
                    <a href="https://github.com/liebharc/homr" class="footer-link" target="_blank">homr</a> (OMR) +
                    <a href="https://web.mit.edu/music21/" class="footer-link" target="_blank">music21</a> (conversion)
                </p>
            </div>
        """)

        # Connect events
        process_btn.click(
            fn=process_sheet_music_v2,
            inputs=[file_input],
            outputs=[abc_output, midi_output, musicxml_output, status_output, preview_image]
        )

    return demo


if __name__ == "__main__":
    print("🎹 Starting Sheet Music Transcriber Pro...")
    print("✨ Premium Edition with Custom UI")
    print("")

    if not check_homr_installation():
        print("\n⚠️  WARNING: homr is not installed!")
        print("\nPlease install homr first:")
        print("1. git clone https://github.com/liebharc/homr.git")
        print("2. cd homr")
        print("3. poetry install --only main")
        print("4. poetry run homr --init")
        print("\nContinuing anyway (app will show error message to users)...\n")

    demo = create_premium_ui()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False
    )
