/**
 * One assistant message: its text as markdown, a trace box per tool call, and the
 * error line when the turn ended in an error.
 */

import { MessagePrimitive, useAuiState } from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import type { ReactElement } from "react";
import remarkGfm from "remark-gfm";

import { MESSAGE_ERROR_PREFIX } from "../constants/ui";
import { ToolTrace } from "../tools/ToolTrace";

// Markdown extensions the model's text may use: tables, task lists, strikethrough.
const REMARK_PLUGINS = [remarkGfm];

/**
 * Render a text part as markdown.
 *
 * @returns The rendered text; the primitive reads the part from context.
 */
function MarkdownText(): ReactElement {
  return <MarkdownTextPrimitive remarkPlugins={REMARK_PLUGINS} className="markdown" />;
}

/**
 * Render the error of the message the component sits in.
 *
 * @returns The error line; empty when the message has no error.
 */
function MessageErrorLine(): ReactElement | null {
  const status = useAuiState((assistantState) => assistantState.message.status);
  const isError = status?.type === "incomplete" && status.reason === "error";
  if (!isError) {
    return null;
  }

  const errorDetail = status.error;
  const errorText =
    typeof errorDetail === "string" ? errorDetail : formatUnknownError(errorDetail);

  return (
    <p className="message-error">
      {MESSAGE_ERROR_PREFIX}: {errorText}
    </p>
  );
}

/** The shape assistant-ui gives a chat error: a code and the message. */
interface ErrorWithMessage {
  message: string;
}

/**
 * Check whether a value carries a message string, as errors and error records do.
 *
 * @param value - whatever the runtime attached as the error.
 * @returns True when a `message` string can be read from it.
 */
function hasMessage(value: unknown): value is ErrorWithMessage {
  const isObject = typeof value === "object" && value !== null;
  if (!isObject) {
    return false;
  }

  const candidate: Partial<ErrorWithMessage> = value;
  const isMessageString = typeof candidate.message === "string";

  return isMessageString;
}

/**
 * Turn an error value of unknown shape into text.
 *
 * @param errorDetail - whatever the runtime attached as the error.
 * @returns A message for the person.
 */
function formatUnknownError(errorDetail: unknown): string {
  const isMessageCarrier = hasMessage(errorDetail);
  if (isMessageCarrier) {
    return errorDetail.message;
  }

  const text = JSON.stringify(errorDetail);

  return text;
}

/**
 * Render one assistant message with its parts.
 *
 * @returns The message block.
 */
export function AssistantMessage(): ReactElement {
  return (
    <MessagePrimitive.Root className="message message-assistant">
      <MessagePrimitive.Parts
        components={{ Text: MarkdownText, tools: { Fallback: ToolTrace } }}
      />
      <MessageErrorLine />
    </MessagePrimitive.Root>
  );
}
