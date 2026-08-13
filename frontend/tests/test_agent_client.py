import responses

from agent_client import AgentClientError, MockAgentClient, RestAgentClient


def test_mock_agent_client_returns_answer():
    client = MockAgentClient()

    result = client.ask("what is the capital of France?", session_id="s1")

    assert "capital of France" in result.answer
    assert result.sources
    assert result.latency_ms > 0


@responses.activate
def test_rest_agent_client_parses_successful_response():
    responses.add(
        responses.POST,
        "http://agent.test/chat",
        json={"answer": "Paris", "sources": ["kb://geo"]},
        status=200,
    )
    client = RestAgentClient(base_url="http://agent.test", timeout_seconds=5)

    result = client.ask("what is the capital of France?", session_id="s1")

    assert result.answer == "Paris"
    assert result.sources == ["kb://geo"]


@responses.activate
def test_rest_agent_client_raises_on_http_error():
    responses.add(responses.POST, "http://agent.test/chat", status=500)
    client = RestAgentClient(base_url="http://agent.test", timeout_seconds=5)

    try:
        client.ask("anything", session_id="s1")
        assert False, "expected AgentClientError"
    except AgentClientError:
        pass


@responses.activate
def test_rest_agent_client_raises_on_malformed_response():
    responses.add(responses.POST, "http://agent.test/chat", json={"unexpected": "shape"}, status=200)
    client = RestAgentClient(base_url="http://agent.test", timeout_seconds=5)

    try:
        client.ask("anything", session_id="s1")
        assert False, "expected AgentClientError"
    except AgentClientError:
        pass
