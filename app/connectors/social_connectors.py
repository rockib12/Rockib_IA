import asyncio
import logging
from decimal import Decimal

from app.execution.models import ActionRecord
from app.execution.services.executor import ExecutionResult

logger = logging.getLogger(__name__)

async def simulate_network_delay():
    """Simule la latence d'un appel API."""
    await asyncio.sleep(1.0)

async def facebook_post_handler(action: ActionRecord) -> ExecutionResult:
    """Connecteur 'facebook.post'."""
    args = action.arguments or {}
    text = args.get("text")
    if not text:
        return ExecutionResult(success=False, output=None, error="Missing 'text' argument")
    
    await simulate_network_delay()
    logger.info(f"[FACEBOOK MOCK] Posting: {text}")
    return ExecutionResult(success=True, output=f"Successfully posted to Facebook: {text}", cost_amount=Decimal("0.0"), cost_unit="credits")

async def instagram_post_handler(action: ActionRecord) -> ExecutionResult:
    """Connecteur 'instagram.post'."""
    args = action.arguments or {}
    image_url = args.get("image_url")
    caption = args.get("caption", "")
    if not image_url:
        return ExecutionResult(success=False, output=None, error="Missing 'image_url' argument")
    
    await simulate_network_delay()
    logger.info(f"[INSTAGRAM MOCK] Posting image {image_url} with caption: {caption}")
    return ExecutionResult(success=True, output=f"Successfully posted to Instagram", cost_amount=Decimal("0.0"), cost_unit="credits")

async def whatsapp_send_handler(action: ActionRecord) -> ExecutionResult:
    """Connecteur 'whatsapp.send'."""
    args = action.arguments or {}
    phone_number = args.get("phone_number")
    message = args.get("message")
    if not phone_number or not message:
        return ExecutionResult(success=False, output=None, error="Missing 'phone_number' or 'message' argument")
    
    await simulate_network_delay()
    logger.info(f"[WHATSAPP MOCK] Sending to {phone_number}: {message}")
    return ExecutionResult(success=True, output=f"Message sent to {phone_number} on WhatsApp", cost_amount=Decimal("0.0"), cost_unit="credits")

async def twitter_post_handler(action: ActionRecord) -> ExecutionResult:
    """Connecteur 'twitter.post'."""
    args = action.arguments or {}
    text = args.get("text")
    if not text:
        return ExecutionResult(success=False, output=None, error="Missing 'text' argument")
    
    await simulate_network_delay()
    logger.info(f"[TWITTER MOCK] Tweeting: {text}")
    return ExecutionResult(success=True, output=f"Successfully tweeted: {text}", cost_amount=Decimal("0.0"), cost_unit="credits")

async def discord_send_handler(action: ActionRecord) -> ExecutionResult:
    """Connecteur 'discord.send'."""
    args = action.arguments or {}
    channel_id = args.get("channel_id")
    content = args.get("content")
    if not channel_id or not content:
        return ExecutionResult(success=False, output=None, error="Missing 'channel_id' or 'content' argument")
    
    await simulate_network_delay()
    logger.info(f"[DISCORD MOCK] Sending to {channel_id}: {content}")
    return ExecutionResult(success=True, output=f"Message sent to Discord channel {channel_id}", cost_amount=Decimal("0.0"), cost_unit="credits")
