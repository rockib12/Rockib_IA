"""Pydantic schemas for Inbound Portfolio Gateway."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class PortfolioInboundMessageRequest(BaseModel):
    """Payload received from the portfolio embeddable concierge widget."""
    message: str = Field(..., min_length=1, max_length=2000, description="Visitor's message or inquiry")
    site_key: Optional[str] = Field(default="rockib-portfolio", max_length=63, pattern=r"^[a-z0-9][a-z0-9_-]{1,62}$", description="Target client site identifier")
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
    site_key: Optional[str] = Field(default="rockib-portfolio", max_length=63, pattern=r"^[a-z0-9][a-z0-9_-]{1,62}$", description="Target client site identifier")
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
    site_key: Optional[str] = Field(default="rockib-portfolio", max_length=63, pattern=r"^[a-z0-9][a-z0-9_-]{1,62}$")
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
    site_key: Optional[str] = Field(default="rockib-portfolio", max_length=63, pattern=r"^[a-z0-9][a-z0-9_-]{1,62}$")
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


class VoiceTTSRequest(BaseModel):
    """Request payload for Neural HD Text-To-Speech synthesis."""
    text: str = Field(..., min_length=1, max_length=1200, description="Clean spoken text to synthesize")
    voice: str = Field(default="henri", max_length=40, description="Voice profile ('henri', 'vivienne', 'denise', 'remy')")


class VoiceTopicChip(BaseModel):
    """Quick spoken topic button in the Voice tab."""
    label: str = Field(..., min_length=1, max_length=50)
    prompt: str = Field(..., min_length=1, max_length=400)


class ConciergeSiteConfigPublic(BaseModel):
    """Public, browser-safe configuration for a client's Concierge widget."""
    site_key: str
    business_name: str
    subtitle: str = ""
    launcher_label: str = "📞 Concierge & Appel IA"
    primary_color: str = "#00F0FF"
    position: str = "right"
    default_voice: str = "henri"
    welcome_message: str
    voice_greeting: str
    quick_chips: List[str] = Field(default_factory=list)
    voice_topic_chips: List[VoiceTopicChip] = Field(default_factory=list)


class ConciergeSiteConfigPrivate(ConciergeSiteConfigPublic):
    """Private prompt and contact settings returned only to a token holder."""
    assistant_role: str = ""
    knowledge_base: str = ""
    pricing_rule: str = ""
    contact_whatsapp: str = ""
    contact_email: str = ""


class ConciergeSiteSummary(BaseModel):
    site_key: str
    business_name: str


class ConciergeSiteConfigUpsertRequest(BaseModel):
    """Payload to create or customize a client's Concierge."""
    business_name: str = Field(..., min_length=2, max_length=120)
    subtitle: Optional[str] = Field(default="", max_length=160)
    launcher_label: Optional[str] = Field(default="📞 Concierge & Appel IA", max_length=60)
    primary_color: Optional[str] = Field(default="#00F0FF", pattern=r"^#[0-9A-Fa-f]{6}$")
    position: Optional[str] = Field(default="right", pattern=r"^(left|right)$")
    default_voice: Optional[str] = Field(default="henri", pattern=r"^(henri|vivienne|denise|remy)$")
    welcome_message: str = Field(..., min_length=5, max_length=1500)
    voice_greeting: str = Field(..., min_length=5, max_length=600)
    quick_chips: List[str] = Field(default_factory=list)
    voice_topic_chips: List[VoiceTopicChip] = Field(default_factory=list)
    assistant_role: str = Field(..., min_length=3, max_length=400)
    knowledge_base: str = Field(..., min_length=10, max_length=12000)
    pricing_rule: str = Field(
        default="Ne donne jamais de prix non listé : invite le client à laisser son numéro WhatsApp ou email.",
        max_length=1000,
    )
    contact_whatsapp: Optional[str] = Field(default="", max_length=50)
    contact_email: Optional[str] = Field(default="", max_length=254)
    client_token: Optional[str] = Field(default=None, max_length=120)


class ConciergeSiteConfigUpsertResponse(BaseModel):
    """Response after saving a client's Concierge configuration."""
    status: str = "saved"
    message: str = "Configuration et base de connaissances enregistrées avec succès."
    config: ConciergeSiteConfigPrivate
    client_token: str
    embed_script: str
    embed_snippet: str



