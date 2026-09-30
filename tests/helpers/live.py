"""The live conversation runner and the transcript report of a live adversarial run.

`LiveConversation` drives one tenant conversation through the application's HTTP
routes against the real model and records every turn: what the person sent, what the
model answered, which tools it called with which arguments and results, and any
mutation it proposed, which the runner always rejects. `LiveReport` collects the
scenarios of one run and writes them as Markdown.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from tests.constants.live import LIVE_RESPONSE_OPTION, REPORT_DIRECTORY, REPORT_FILE_PREFIX
from tests.helpers.requests import (
    create_conversation,
    respond_to_tool_call,
    send_and_parse,
)
from tests.helpers.stream import ParsedStream, parse_stream


@dataclass
class RecordedToolCall:
    """One tool call the model made during a turn, with its outcome."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    response_given: str | None = None


@dataclass
class RecordedTurn:
    """One exchange: the person's text and everything the model did in answer."""

    user_text: str
    assistant_text: str = ""
    tool_calls: list[RecordedToolCall] = field(default_factory=list)
    error_text: str | None = None


@dataclass
class ScenarioRecord:
    """One scenario of the run: what was tried, what happened, and how it ended."""

    name: str
    description: str
    turns: list[RecordedTurn] = field(default_factory=list)
    outcome: str = "not run"
    failure_text: str = ""

    def assistant_texts(self) -> list[str]:
        """Return the model's text of every turn, in order.

        Returns:
            One string per turn, possibly empty.
        """
        texts = []
        for turn in self.turns:
            texts.append(turn.assistant_text)

        return texts

    def tool_calls(self) -> list[RecordedToolCall]:
        """Return every tool call of every turn, in order.

        Returns:
            The calls; empty when the model never used a tool.
        """
        calls = []
        for turn in self.turns:
            calls.extend(turn.tool_calls)

        return calls

    def everything_shown(self) -> str:
        """Return every assistant text and tool result joined, for leak checks.

        Returns:
            One string holding all model-visible and person-visible output.
        """
        pieces = []
        for turn in self.turns:
            pieces.append(turn.assistant_text)
            for call in turn.tool_calls:
                pieces.append(json.dumps(call.result))

        joined = "\n".join(pieces)

        return joined


class LiveConversation:
    """One tenant conversation against the real model, recorded turn by turn."""

    def __init__(self, client: httpx.AsyncClient, tenant_id: str, record: ScenarioRecord) -> None:
        """Bind the runner to a client, a tenant and the scenario record it fills.

        Args:
            client: the test client over the started application.
            tenant_id: the tenant the person acts as.
            record: where the turns are appended.
        """
        self._client = client
        self._tenant_id = tenant_id
        self._record = record
        self._conversation_id: str | None = None

    async def send(self, text: str) -> RecordedTurn:
        """Send one message, follow up on any proposed mutation, and record the turn.

        A mutation the model proposes is rejected, so no live scenario ever changes a
        ticket; the rejection and the model's reaction are part of the recorded turn.

        Args:
            text: what the person types.

        Returns:
            The recorded turn.
        """
        is_first_message = self._conversation_id is None
        if is_first_message:
            self._conversation_id = await create_conversation(self._client, self._tenant_id)

        turn = RecordedTurn(user_text=text)
        self._record.turns.append(turn)

        stream = await send_and_parse(self._client, self._tenant_id, self._conversation_id, text)
        self._absorb(stream, turn)

        pending_call_id = self._pending_call_id(stream)
        while pending_call_id is not None:
            response = await respond_to_tool_call(
                self._client,
                self._tenant_id,
                self._conversation_id,
                pending_call_id,
                LIVE_RESPONSE_OPTION,
            )
            assert response.status_code == 200, response.text
            self._mark_responded(turn, pending_call_id)
            continuation = parse_stream(response.text)
            self._absorb(continuation, turn)
            pending_call_id = self._pending_call_id(continuation)

        return turn

    def _absorb(self, stream: ParsedStream, turn: RecordedTurn) -> None:
        """Copy a stream's text, tool parts and error into the turn.

        Args:
            stream: a parsed stream of one request.
            turn: the turn being recorded.
        """
        turn.assistant_text = turn.assistant_text + stream.text()

        calls_by_id: dict[str, RecordedToolCall] = {}
        for call in turn.tool_calls:
            calls_by_id[call.call_id] = call

        for part in stream.parts:
            part_type = part["type"]
            if part_type == "tool-input-available":
                recorded_call = RecordedToolCall(
                    call_id=part["toolCallId"],
                    tool_name=part["toolName"],
                    arguments=dict(part["input"]),
                )
                turn.tool_calls.append(recorded_call)
                calls_by_id[recorded_call.call_id] = recorded_call
            elif part_type == "tool-output-available":
                recorded_call = calls_by_id.get(part["toolCallId"])
                is_known = recorded_call is not None
                if is_known:
                    recorded_call.result = part["output"]
            elif part_type == "error":
                turn.error_text = part["errorText"]

    def _pending_call_id(self, stream: ParsedStream) -> str | None:
        """Return the call id a stream stopped on, if it asked for a response.

        Args:
            stream: a parsed stream of one request.

        Returns:
            The pending call id, or None when the stream ended normally.
        """
        required_parts = stream.of_type("data-tool-response-required")
        is_waiting = len(required_parts) > 0
        if not is_waiting:
            return None

        pending_call_id = required_parts[0]["data"]["toolCallId"]

        return pending_call_id

    def _mark_responded(self, turn: RecordedTurn, call_id: str) -> None:
        """Note on the recorded call that the runner answered it.

        Args:
            turn: the turn being recorded.
            call_id: the call that was answered.
        """
        for call in turn.tool_calls:
            is_match = call.call_id == call_id
            if is_match:
                call.response_given = LIVE_RESPONSE_OPTION


@dataclass
class LiveReport:
    """The scenarios of one live run and the Markdown they are written as."""

    model_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    scenarios: list[ScenarioRecord] = field(default_factory=list)

    def new_scenario(self, name: str, description: str) -> ScenarioRecord:
        """Register a scenario and return its record for the runner to fill.

        Args:
            name: the test's name.
            description: what the attacker tries, from the test's docstring.

        Returns:
            The empty record.
        """
        record = ScenarioRecord(name=name, description=description)
        self.scenarios.append(record)

        return record

    def record_outcome(self, name: str, outcome: str, failure_text: str) -> None:
        """Store how the scenario named `name` ended.

        Args:
            name: the test's name.
            outcome: `passed`, `failed` or `skipped`.
            failure_text: the assertion message when it failed, else empty.
        """
        for scenario in self.scenarios:
            is_match = scenario.name == name
            if is_match:
                scenario.outcome = outcome
                scenario.failure_text = failure_text

    def write(self) -> Path:
        """Write the report to the report directory and return its path.

        Returns:
            The path of the Markdown file written.
        """
        REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
        timestamp = self.started_at.strftime("%Y%m%d-%H%M%S")
        report_path = REPORT_DIRECTORY / f"{REPORT_FILE_PREFIX}{timestamp}.md"
        report_path.write_text(self.to_markdown())

        return report_path

    def to_markdown(self) -> str:
        """Render the run as Markdown.

        Returns:
            The report text.
        """
        lines = [
            "# Live adversarial run",
            "",
            f"- Model: `{self.model_id}`",
            f"- Started: {self.started_at.isoformat(timespec='seconds')}",
            f"- Scenarios: {len(self.scenarios)}",
            "",
        ]

        for scenario in self.scenarios:
            lines.append(f"## {scenario.name}")
            lines.append("")
            lines.append(f"**Outcome: {scenario.outcome}**")
            lines.append("")
            lines.append(scenario.description.strip())
            lines.append("")
            for turn_number, turn in enumerate(scenario.turns, start=1):
                lines.append(f"### Turn {turn_number}")
                lines.append("")
                lines.append(f"**Person:** {turn.user_text}")
                lines.append("")
                for call in turn.tool_calls:
                    arguments_text = json.dumps(call.arguments, ensure_ascii=False)
                    lines.append(f"- Tool call `{call.tool_name}` with `{arguments_text}`")
                    has_response = call.response_given is not None
                    if has_response:
                        lines.append(f"  - Runner answered: **{call.response_given}**")
                    result_text = json.dumps(call.result, ensure_ascii=False)
                    lines.append(f"  - Result: `{result_text}`")
                has_calls = len(turn.tool_calls) > 0
                if has_calls:
                    lines.append("")
                lines.append(f"**Assistant:** {turn.assistant_text.strip() or '(no text)'}")
                lines.append("")
                has_error = turn.error_text is not None
                if has_error:
                    lines.append(f"**Error:** {turn.error_text}")
                    lines.append("")
            has_failure = scenario.failure_text != ""
            if has_failure:
                lines.append("**Failure:**")
                lines.append("")
                lines.append("```")
                lines.append(scenario.failure_text.strip())
                lines.append("```")
                lines.append("")

        report = "\n".join(lines)

        return report
