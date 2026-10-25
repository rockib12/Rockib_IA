"""Pydantic schemas for Inbound Portfolio Gateway."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


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
    consent: bool = Field(default=True, description="Explicit consent to store the callback request")
    site_key: Optional[str] = Field(default="rockib-portfolio", max_length=63, pattern=r"^[a-z0-9][a-z0-9_-]{1,62}$")
    contact_name: Optional[str] = Field(default=None, max_length=120, description="Visitor's name")
    topic: Optional[str] = Field(default="Discussion projet", max_length=500, description="Reason for call")
    channel: str = Field(default="whatsapp", pattern=r"(?i)^(whatsapp|phone)$", description="'whatsapp' or 'phone'")
    preferred_time: Optional[str] = Field(default="immediate", max_length=100, description="'immediate' or scheduled slot")

    @field_validator("phone_number")
    @classmethod
    def validate_international_phone(cls, value: str) -> str:
        cleaned = value.strip()
        digits = re.sub(r"\D", "", cleaned)
        if not 8 <= len(digits) <= 15:
            raise ValueError("Le numéro doit contenir entre 8 et 15 chiffres.")
        return cleaned


class CallMeBackResponse(BaseModel):
    """Acknowledgement that the callback request was durably recorded."""
    callback_id: str
    status: str = "scheduled"
    channel: str
    phone_number: str
    message: str
    estimated_wait_minutes: Optional[int] = None


class ConciergeLeadSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    site_key: str
    contact_name: Optional[str] = None
    phone_number: str
    topic: Optional[str] = None
    channel: str
    status: str
    created_at: datetime


class ConciergeLeadStatusUpdateRequest(BaseModel):
    """Request to update a lead's follow-up state (contacted, converted, archived)."""
    status: str = Field(..., pattern=r"^(received|contacted|converted|archived)$")


class ConciergeTunnelStatusResponse(BaseModel):
    """Public healthcheck and tunnel diagnostics for the Concierge gateway."""
    status: str = "operational"
    backend_time: datetime
    active_sites_count: int
    groq_llm_ready: bool
    voice_tts_ready: bool
    tunnel_reachable: bool = True


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
    realtime_voice_enabled: bool = False
    voice_provider: str = "native"


class VoiceCapabilitiesResponse(BaseModel):
    realtime_enabled: bool
    provider: str
    scribe_model: str
    tts_model: str
    barge_in_supported: bool


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


class ConciergeTraceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: str
    site_key: str
    channel: str
    model: str
    duration_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    tools_called: List[str] = Field(default_factory=list)
    result_status: str
    lead_captured: bool
    transferred_to_rockib: bool
    error_message: Optional[str] = None
    created_at: datetime


class ConciergeMetricsResponse(BaseModel):
    site_key: Optional[str] = None
    total_requests: int
    avg_duration_ms: float
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    success_rate: float
    lead_captured_count: int
    lead_capture_rate: float
    transferred_count: int
    by_channel: dict[str, int] = Field(default_factory=dict)
    by_model: dict[str, int] = Field(default_factory=dict)


class BenchmarkScenarioResult(BaseModel):
    scenario_id: str
    name: str
    passed: bool
    score: float
    duration_ms: float
    checks: dict[str, bool] = Field(default_factory=dict)
    reply_snippet: str
    details: str = ""


class BenchmarkSuiteReport(BaseModel):
    total_scenarios: int
    passed_scenarios: int
    overall_score: float
    avg_duration_ms: float
    results: List[BenchmarkScenarioResult]
    timestamp: datetime




