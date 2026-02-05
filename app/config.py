# app/config.py
import os
class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "devsecret")
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/voice_expense")
    # ASR options
    ASR_BACKEND = os.environ.get("ASR_BACKEND", "whisper")  # or "browser"
