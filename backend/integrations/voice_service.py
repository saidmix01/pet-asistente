"""
Voice Service — Speech recognition and voice intent parser for Pet Asistente.
Transcribes audio commands in Spanish and maps them to physical pet actions or conversational responses.
"""

import io
import re
import unicodedata
from typing import Any
import speech_recognition as sr
from services.logger import info, warning, error


def normalize_text(text: str) -> str:
    """Normalize text: lowercased, stripped, and without accent marks for robust matching."""
    text = (text or "").strip().lower()
    # Remove accents: á -> a, é -> e, etc.
    nfkd = unicodedata.normalize('NFKD', text)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


class VoiceService:
    def __init__(self, language: str = "es-ES"):
        self.language = language
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True

    def transcribe(self, wav_bytes: bytes) -> str | None:
        """Transcribe raw WAV bytes to text using speech recognition."""
        if not wav_bytes or len(wav_bytes) < 44:  # WAV header is 44 bytes
            return None

        try:
            buf = io.BytesIO(wav_bytes)
            with sr.AudioFile(buf) as source:
                audio_data = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio_data, language=self.language)
                info(f"[VoiceService] Transcribed: '{text}'")
                return text.strip()
        except sr.UnknownValueError:
            info("[VoiceService] Speech not understood or silence.")
            return None
        except sr.RequestError as e:
            error(f"[VoiceService] Recognition request error: {e}")
            return None
        except Exception as e:
            error(f"[VoiceService] Unexpected transcription error: {e}")
            return None

    def match_intent(self, text: str) -> dict[str, Any] | None:
        """
        Analyze voice text and match against direct physical dog actions.
        Returns a pet action dict if recognized, or None if general conversation.
        """
        if not text:
            return None

        norm = normalize_text(text)

        # 1. Fetch ball (Pelota / Trae / Jugar)
        if any(w in norm for w in ["pelota", "pelotita", "balon", "jugar pelota", "trae la", "traeme la", "busca la pelota"]):
            return {
                "action": "fetch_ball",
                "speech": "¡A por la pelota! 🎾",
                "sound": "ladrido",
                "mood": "playful",
            }

        # 2. Step up / Climb platform (Subir escalón / Arriba)
        if any(w in norm for w in ["sube escalon", "sube un escalon", "subete", "subir", "arriba", "escalon", "un escalon"]):
            return {
                "action": "step_up",
                "speech": "¡Subo de escalón! 🪜",
                "sound": "ladrido",
                "mood": "playful",
            }

        # 3. Step down / Floor (Bajar escalón / Al suelo)
        if any(w in norm for w in ["al suelo", "al piso", "baja al piso", "baja al suelo", "baja todo"]):
            return {
                "action": "reset_step",
                "speech": "¡De vuelta al piso! 🐾",
                "sound": "none",
                "mood": "calm",
            }
        if any(w in norm for w in ["baja escalon", "baja", "bajate", "abajo"]):
            return {
                "action": "step_down",
                "speech": "¡Bajando un escalón! 🐾",
                "sound": "none",
                "mood": "calm",
            }

        # 4. Climb active window (Trepar ventana de código)
        if any(w in norm for w in ["trepa", "ventana", "mi ventana", "acompáñame a la ventana", "al codigo", "a la pantalla"]):
            return {
                "action": "climb_window",
                "speech": "¡Trepo a tu ventana activa! 🪟",
                "sound": "ladrido",
                "mood": "focused",
            }

        # 5. Feed snack (Galleta / Premio / Come)
        if any(w in norm for w in ["galleta", "galletita", "snack", "premio", "come", "comete", "comida", "toma esto"]):
            return {
                "action": "feed_snack",
                "speech": "¡Ñam ñam, gracias por la galleta! 🍪",
                "sound": "ladrido",
                "mood": "happy",
            }

        # 6. Jump (Salta / Brinca)
        if any(w in norm for w in ["salta", "saltar", "brinca", "brincar", "hop"]):
            return {
                "action": "jump",
                "speech": "¡Hop hop! 🐾",
                "sound": "ladrido",
                "mood": "playful",
            }

        # 7. Sit (Siéntate / Quieto)
        if any(w in norm for w in ["sientate", "sientese", "quieto", "sienta", "parate"]):
            return {
                "action": "sit",
                "speech": "¡Me siento aquí juicioso! 🐶",
                "sound": "none",
                "mood": "calm",
            }

        # 8. Run (Corre / Rápido)
        if any(w in norm for w in ["corre", "correr", "a correr", "rapido", "velocidad"]):
            return {
                "action": "run",
                "direction": "flip",
                "duration_ms": 3000,
                "speech": "¡A toda velocidad! ⚡🐾",
                "sound": "ladrido",
                "mood": "playful",
            }

        # 9. Center (Ven aquí / Al centro)
        if any(w in norm for w in ["ven", "ven aqui", "ven aca", "al centro", "aqui", "conmigo"]):
            return {
                "action": "walk",
                "move_to": "center",
                "duration_ms": 2500,
                "speech": "¡Voy contigo al centro! 📍",
                "sound": "none",
                "mood": "calm",
            }

        # 10. Sniff / Look around (Olfatea / Busca)
        if any(w in norm for w in ["huele", "olfatea", "sniff", "inspecciona"]):
            return {
                "action": "sniff",
                "duration_ms": 2500,
                "speech": "¡Sniff sniff! Inspeccionando el entorno 🔍🐾",
                "sound": "none",
                "mood": "curious",
            }

        # 11. Sleep / Rest (Duérmete / A descansar)
        if any(w in norm for w in ["duermete", "a dormir", "descansa", "a descansar", "buenas noches", "toma una siesta"]):
            return {
                "action": "idle2",
                "duration_ms": 6000,
                "speech": "Zzz... me echo una siesta 😴💤",
                "sound": "ronquido",
                "mood": "sleepy",
            }

        # 12. Praise / Affection (Buen chico / Te quiero)
        if any(w in norm for w in ["buen chico", "buen perro", "te quiero", "lindo perro", "caricia", "te amo"]):
            return {
                "action": "jump",
                "speech": "¡Awww, gracias! Eres el mejor humano 🥰❤️",
                "sound": "ronquido",
                "mood": "happy",
            }

        return None
