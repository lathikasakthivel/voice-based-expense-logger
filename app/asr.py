# app/asr.py
import os
import subprocess

def _ensure_ffmpeg():
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except Exception:
        raise RuntimeError(
            "FFmpeg not found. Install it and ensure it's on PATH "
            "(macOS: 'brew install ffmpeg', Ubuntu: 'sudo apt-get install -y ffmpeg', "
            "Windows: download from ffmpeg.org and add to PATH)."
        )

def transcribe_with_whisper(audio_path: str) -> str:
    _ensure_ffmpeg()

    try:
        import whisper  # pip install openai-whisper
    except Exception as e:
        raise RuntimeError(
            "Python package 'openai-whisper' is not installed. "
            "Install with: pip install openai-whisper torch --extra-index-url https://download.pytorch.org/whl/cu121"
        ) from e

    # Small models are fast and good enough
    model_name = os.environ.get("WHISPER_MODEL", "base")
    try:
        model = whisper.load_model(model_name)
        result = model.transcribe(audio_path, language="en")
        return (result.get("text") or "").strip()
    except Exception as e:
        # Typically decoding failure or torch/ffmpeg issues
        raise RuntimeError(f"Whisper/ffmpeg failed to transcribe: {e}") from e
