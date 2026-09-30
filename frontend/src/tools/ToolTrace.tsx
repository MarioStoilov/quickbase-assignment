/**
 * The trace of one tool call: its name, its arguments, and its result or its state.
 *
 * Registered once as the fallback for every tool, so a tool added to the backend is
 * traced without any change here. Nothing in this component knows a tool name. The
 * box is collapsed by default so the chat stays readable; the summary line always
 * shows the tool name and the call's state, and a click reveals the arguments and
 * the result.
 */

import type { ToolCallMessagePartProps } from "@assistant-ui/react";
import type { ReactElement } from "react";

import { TOOL_RESULT_ERROR_KEY } from "../constants/stream";
import {
  TOOL_TRACE_ARGUMENTS_LABEL,
  TOOL_TRACE_DONE_TEXT,
  TOOL_TRACE_FAILED_TEXT,
  TOOL_TRACE_HEADING,
  TOOL_TRACE_RESULT_LABEL,
  TOOL_TRACE_RUNNING_TEXT,
  TOOL_TRACE_WAITING_TEXT,
} from "../constants/ui";

// Indentation of the pretty-printed JSON in the trace, in spaces.
const JSON_INDENT = 2;

/**
 * Check whether a tool result reports a failure.
 *
 * @param result - the tool's output as streamed.
 * @returns True when the result carries the backend's error key.
 */
function isErrorResult(result: unknown): boolean {
  const isObject = typeof result === "object" && result !== null;
  if (!isObject) {
    return false;
  }

  const hasErrorKey = TOOL_RESULT_ERROR_KEY in result;

  return hasErrorKey;
}

/**
 * Pretty-print a value as JSON for the trace.
 *
 * @param value - arguments or a result.
 * @returns The indented JSON text.
 */
export function formatJson(value: unknown): string {
  const text = JSON.stringify(value, null, JSON_INDENT);

  return text;
}

/** The tool-call part as assistant-ui presents it, with arguments as a plain object. */
type ToolTraceProps = ToolCallMessagePartProps<Record<string, unknown>>;

/**
 * Render one tool call's trace box.
 *
 * @param props - the tool-call part as assistant-ui presents it.
 * @returns The trace box.
 */
export function ToolTrace(props: ToolTraceProps): ReactElement {
  const { toolName, args, result, status } = props;
  const hasResult = result !== undefined;
  const isWaiting = status.type === "requires-action";
  const isError = hasResult && isErrorResult(result);
  const argumentsText = formatJson(args);

  // The state word sits in the always-visible summary line, so a collapsed box still
  // tells whether the call ran, failed, waits for the person, or is in flight.
  let stateText: string;
  let stateClassName: string;
  if (isError) {
    stateText = TOOL_TRACE_FAILED_TEXT;
    stateClassName = "tool-trace-state tool-trace-state-error";
  } else if (hasResult) {
    stateText = TOOL_TRACE_DONE_TEXT;
    stateClassName = "tool-trace-state";
  } else if (isWaiting) {
    stateText = TOOL_TRACE_WAITING_TEXT;
    stateClassName = "tool-trace-state tool-trace-state-waiting";
  } else {
    stateText = TOOL_TRACE_RUNNING_TEXT;
    stateClassName = "tool-trace-state";
  }

  let resultElement: ReactElement;
  if (hasResult) {
    const resultText = formatJson(result);
    const resultClassName = isError
      ? "tool-trace-result tool-trace-error"
      : "tool-trace-result";
    resultElement = <pre className={resultClassName}>{resultText}</pre>;
  } else {
    resultElement = <p className="tool-trace-pending">{stateText}</p>;
  }

  return (
    <details className="tool-trace">
      <summary className="tool-trace-summary">
        <span className="tool-trace-heading">
          {TOOL_TRACE_HEADING}: <code>{toolName}</code>
        </span>
        <span className={stateClassName}>{stateText}</span>
      </summary>
      <div className="tool-trace-body">
        <p className="tool-trace-label">{TOOL_TRACE_ARGUMENTS_LABEL}</p>
        <pre className="tool-trace-arguments">{argumentsText}</pre>
        <p className="tool-trace-label">{TOOL_TRACE_RESULT_LABEL}</p>
        {resultElement}
      </div>
    </details>
  );
}
