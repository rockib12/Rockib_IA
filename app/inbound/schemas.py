"""Pydantic schemas for Inbound Portfolio Gateway."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class PortfolioInboundMessageRequest(BaseModel):
    """Payload received from the portfolio embeddable concierge widget."""
    message: str = Field(..., min_length=1, max_length=2000, description="Visitor's message or inquiry")
    contact_email: Optional[str] = Field(default=None, max_length=254, description="Optional email for quote/callback")
    contact_phone: Optional[str] = Field(default=None, max_length=40, description="Optional WhatsApp or phone number")
    sender_name: Optional[str] = Field(default=None, max_length=120, description="Optional visitor name")
    page_url: Optional[str] = Field(default="https://rockib-quenum.netlify.app/", max_length=500, description="Referrer page context")
    conversation_id: Optional[str] = Field(default=None, max_length=64, description="Session tracking UUID for multi-turn dialogues")


class PortfolioInboundResponse(BaseModel):
    """Response returned to the portfolio visitor widget."""
    reply: str
    conversation_id: str
    lead_captured: bool = False
    status: str = "ok"


class VoiceCallSessionRequest(BaseModel):
    """Initiates an interactive voice call session with the Concierge."""
    page_url: Optional[str] = Field(default="https://rockib-quenum.netlify.app/", max_length=500, description="Referrer page context")
    visitor_id: Optional[str] = Field(default=None, max_length=64, description="Optional visitor device tracking ID")


class VoiceCallSessionResponse(BaseModel):
    """Session credentials and initial voice greeting."""
    session_id: str
    status: str = "connected"
    greeting_text: str
    voice_locale: str = "fr-FR"
    max_duration_seconds: int = 300


class VoiceCallTurnRequest(BaseModel):
    """A vocal utterance transcribed from the visitor's microphone."""
    session_id: str = Field(..., min_length=1, max_length=64)
    user_speech_transcript: str = Field(..., min_length=1, max_length=2000)
    duration_seconds: Optional[float] = Field(default=None)


class VoiceCallTurnResponse(BaseModel):
    """Agent response intended to be spoken back to the caller."""
    session_id: str
    agent_reply_text: str
    lead_captured: bool = False
    should_end_call: bool = False
    status: str = "ok"


class CallMeBackRequest(BaseModel):
    """Request by visitor to receive a phone or WhatsApp voice call."""
    phone_number: str = Field(..., min_length=6, max_length=30, description="International phone number")
    contact_name: Optional[str] = Field(default=None, max_length=120, description="Visitor's name")
    topic: Optional[str] = Field(default="Discussion projet", max_length=500, description="Reason for call")
    channel: str = Field(default="whatsapp", pattern=r"(?i)^(whatsapp|phone)$", description="'whatsapp' or 'phone'")
    preferred_time: Optional[str] = Field(default="immediate", max_length=100, description="'immediate' or scheduled slot")


class CallMeBackResponse(BaseModel):
    """Confirmation of callback registration."""
    callback_id: str
    status: str = "scheduled"
    channel: str
    phone_number: str
    message: str
    estimated_wait_minutes: int = 5

