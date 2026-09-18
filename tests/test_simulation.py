import pytest
import json
from unittest.mock import AsyncMock
from app.cognitive.schemas import CognitiveInput, CognitiveOutput
from app.cognitive.services.simulation import CognitiveSimulator
from app.intelligence.services.ai_provider import AIProvider
from app.intelligence.exceptions import AIProviderParsingError

@pytest.fixture
def mock_provider():
    return AsyncMock(spec=AIProvider)

@pytest.fixture
def simulator(mock_provider):
    return CognitiveSimulator(provider=mock_provider)

@pytest.fixture
def cognitive_input():
    return CognitiveInput(
        workspace_id="ws1",
        objective="Fix a bug",
        situation="The server is crashing on startup"
    )

@pytest.mark.asyncio
async def test_simulate_success(simulator, mock_provider, cognitive_input):
    # Setup mock response
    mock_provider.generate.return_value = json.dumps({
        "action": "Check the logs",
        "confidence": 0.95,
        "reasoning": "Rockib always checks logs first when a crash occurs"
    })

    patterns = "- [DECISION] Always check logs on crash (poids: 0.90)"
    output = await simulator.simulate(cognitive_input, patterns)

    assert isinstance(output, CognitiveOutput)
    assert output.action == "Check the logs"
    assert output.confidence == 0.95
    assert "logs first" in output.reasoning

@pytest.mark.asyncio
async def test_simulate_markdown_success(simulator, mock_provider, cognitive_input):
    # Setup mock response with markdown wrappers
    mock_provider.generate.return_value = "```json\n{\n  \"action\": \"Restart server\",\n  \"confidence\": 0.8,\n  \"reasoning\": \"Typical first step\"\n}\n```"

    patterns = "Some patterns"
    output = await simulator.simulate(cognitive_input, patterns)

    assert output.action == "Restart server"
    assert output.confidence == 0.8

@pytest.mark.asyncio
async def test_simulate_parsing_error(simulator, mock_provider, cognitive_input):
    # Setup mock response with invalid JSON
    mock_provider.generate.return_value = "This is not JSON"

    patterns = "Some patterns"
    with pytest.raises(AIProviderParsingError):
        await simulator.simulate(cognitive_input, patterns)

@pytest.mark.asyncio
async def test_simulate_missing_field(simulator, mock_provider, cognitive_input):
    # Setup mock response missing "action"
    mock_provider.generate.return_value = json.dumps({
        "confidence": 0.5,
        "reasoning": "Missing action here"
    })

    patterns = "Some patterns"
    with pytest.raises(AIProviderParsingError):
        await simulator.simulate(cognitive_input, patterns)
