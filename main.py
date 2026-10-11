#!/usr/bin/env python3
"""Ebook Generator — AI-Powered Book Creation with llama.cpp.

A PySide6 desktop application that uses local LLM inference via llama.cpp
to generate complete ebooks with prompt engineering, context engineering,
and an AI harness for pipeline orchestration.

Usage:
    python main.py

    # With a specific model:
    python main.py --model path/to/model.gguf

    # With custom context size:
    python main.py --model path/to/model.gguf --ctx-size 16384
"""

from __future__ import annotations

import argparse
import logging
import sys


from pathlib import Path

SETTINGS_DIR = Path.home() / ".ebook-generator"
SETTINGS_FILE = str(SETTINGS_DIR / "settings.json")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ebook Generator — AI-Powered Book Creation with llama.cpp",
    )
    parser.add_argument(
        "--model", "-m",
        type=str, default=None,
        help="Path to a GGUF model file to load at startup.",
    )
    parser.add_argument(
        "--ctx-size", "-c",
        type=int, default=8192,
        help="Context window size in tokens (default: 8192).",
    )
    parser.add_argument(
        "--gpu-layers", "-g",
        type=int, default=-1,
        help="Number of layers to offload to GPU (-1 = all, default: -1).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger("main")

    # Import PySide6
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
    except ImportError:
        print("ERROR: PySide6 is not installed. Install with: pip install PySide6")
        sys.exit(1)

    # Create the application
    app = QApplication(sys.argv)
    app.setApplicationName("Ebook Generator")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("EbookGenerator")

    # High DPI scaling
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.Round
    )

    # Import and create main window
    from app.main_window import MainWindow

    window = MainWindow(settings_path=SETTINGS_FILE)
    window.show()

    # Auto-load model if specified
    if args.model:
        logger.info("Loading model: %s", args.model)
        try:
            window._llm.load_model(
                args.model,
                n_ctx=args.ctx_size,
                n_gpu_layers=args.gpu_layers,
            )
            model_name = Path(args.model).name
            window._model_label.setText(f"  Model: {model_name}")
            window._model_label.setStyleSheet(
                "color: #27ae60; font-weight: bold; padding: 0 12px;"
            )
            window._context_eng = window._context_eng.__class__(
                count_tokens_fn=window._llm.count_tokens,
                strategy=window._context_combo.currentText(),
            )
            window._harness._context_eng = window._context_eng
            window.statusBar().showMessage(
                f"Model loaded: {model_name} (ctx={args.ctx_size})", 5000
            )
        except Exception as e:
            logger.error("Failed to load model: %s", e)
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                window, "Model Load Error",
                f"Failed to load model:\n{e}\n\n"
                f"Make sure llama-cpp-python is installed and the model file is valid.",
            )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()