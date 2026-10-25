"""
Pont WebSocket Full-Duplex pour conversation vocale en temps réel (P2).
Architecture :
- Frontend WebSocket <--> Backend FastAPI Bridge <--> Groq Whisper STT + Groq LLM + ElevenLabs HD / Edge-TTS
- Streaming bidirectionnel à latence minimale avec interruption instantanée (Barge-In)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from app.core.config import settings
from app.inbound.schemas import VoiceCallSessionRequest, VoiceCallTurnRequest
from app.inbound.services.voice_call_service import VoiceCallService
from app.inbound.services.elevenlabs_service import elevenlabs_service

logger = logging.getLogger(__name__)
voice_service = VoiceCallService()


class RealtimeVoiceBridge:
    def __init__(self, site_key: str = "rockib-portfolio", voice_profile: str = "brian"):
        self.site_key = site_key
        self.voice_profile = voice_profile
        self.session_id: Optional[str] = None
        self.is_speaking = False
        self.active = True

    async def run(self, websocket: WebSocket):
        await websocket.accept()
        logger.info("[WebSocket Voice] Client connecté en mode Full-Duplex (site_key: %s)", self.site_key)

        # 1. Création de session vocale via start_call_session
        try:
            req = VoiceCallSessionRequest(page_url="ws://realtime", site_key=self.site_key)
            client_ip = websocket.client.host if websocket.client else "127.0.0.1"
            session_resp = voice_service.start_call_session(request=req, client_ip=client_ip)
            
            self.session_id = session_resp.session_id
            greeting_text = session_resp.greeting_text

            await websocket.send_json({
                "type": "session_started",
                "session_id": self.session_id,
                "provider": "elevenlabs_realtime" if elevenlabs_service.is_realtime_enabled() else "edge_realtime",
                "greeting_text": greeting_text,
            })

            # Synthèse audio du greeting
            greeting_audio = await voice_service.synthesize_neural_speech(
                text=greeting_text,
                voice_profile=self.voice_profile,
            )
            if greeting_audio:
                audio_b64 = base64.b64encode(greeting_audio).decode("utf-8")
                await websocket.send_json({
                    "type": "audio_reply",
                    "text": greeting_text,
                    "audio_b64": audio_b64,
                })

        except Exception as exc:
            logger.error("[WebSocket Voice] Erreur initialisation session: %s", exc, exc_info=True)
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close()
            return

        # 2. Boucle d'écoute des messages / flux audio du client
        audio_buffer = bytearray()
        try:
            while self.active:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"]:
                    audio_buffer.extend(message["bytes"])
                elif "text" in message and message["text"]:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")

                    if msg_type == "interrupt":
                        self.is_speaking = False
                        audio_buffer.clear()
                        await websocket.send_json({"type": "interrupted"})

                    elif msg_type in ("speech_end", "text_query"):
                        transcript = data.get("text")
                        if not transcript and len(audio_buffer) > 1000:
                            ext = data.get("ext", "webm")
                            transcript = await voice_service.transcribe_audio_bytes(
                                bytes(audio_buffer), filename=f"speech.{ext}"
                            )
                        audio_buffer.clear()

                        if transcript and transcript.strip():
                            await websocket.send_json({
                                "type": "transcript",
                                "role": "user",
                                "text": transcript.strip(),
                            })

                            # Génération de la réponse via handle_voice_turn
                            turn_req = VoiceCallTurnRequest(
                                session_id=self.session_id,
                                user_speech_transcript=transcript.strip(),
                                site_key=self.site_key,
                            )
                            reply_resp = await voice_service.handle_voice_turn(turn_req)
                            agent_reply = reply_resp.agent_reply_text

                            await websocket.send_json({
                                "type": "agent_text",
                                "text": agent_reply,
                                "lead_captured": reply_resp.lead_captured,
                                "should_end_call": reply_resp.should_end_call,
                            })

                            # Synthèse vocale de la réponse
                            audio_bytes = await voice_service.synthesize_neural_speech(
                                text=agent_reply,
                                voice_profile=self.voice_profile,
                            )
                            if audio_bytes:
                                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                                await websocket.send_json({
                                    "type": "audio_reply",
                                    "text": agent_reply,
                                    "audio_b64": audio_b64,
                                })

                    elif msg_type == "set_voice":
                        new_voice = data.get("voice", "brian")
                        self.voice_profile = new_voice
                        await websocket.send_json({"type": "voice_updated", "voice": new_voice})

                    elif msg_type == "hangup":
                        await websocket.send_json({"type": "call_ended"})
                        break

        except WebSocketDisconnect:
            logger.info("[WebSocket Voice] Déconnexion WebSocket normale.")
        except Exception as exc:
            logger.warning("[WebSocket Voice] Exception flux temps réel: %s", exc)
        finally:
            self.active = False
            if self.session_id and self.session_id in voice_service._sessions:
                del voice_service._sessions[self.session_id]
