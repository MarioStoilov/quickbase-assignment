/**
 * The blocking dialog that asks the person to answer a pending tool call.
 *
 * Generic on purpose: it shows whatever tool name and arguments the call carries and
 * makes one button per option the backend offered. A new backend tool with response
 * options gets this dialog without a frontend change.
 */

import type { ReactElement } from "react";

import {
  TOOL_RESPONSE_MODAL_EXPLANATION,
  TOOL_RESPONSE_MODAL_HEADING,
  TOOL_TRACE_ARGUMENTS_LABEL,
} from "../constants/ui";
import type { PendingToolResponse } from "./pendingToolResponse";
import { formatJson } from "./ToolTrace";

/** What the dialog shows and what it does when an option is picked. */
export interface ToolResponseModalProps {
  pending: PendingToolResponse;
  isBusy: boolean;
  onRespond: (option: string) => void;
}

// Id of the heading, referenced by the dialog for assistive technology.
const HEADING_ELEMENT_ID = "tool-response-heading";

/**
 * Render the dialog over the chat.
 *
 * @param props - the pending call, whether an answer is in flight, and the callback.
 * @returns The dialog and its backdrop.
 */
export function ToolResponseModal(props: ToolResponseModalProps): ReactElement {
  const { pending, isBusy, onRespond } = props;
  const argumentsText = formatJson(pending.arguments);

  const optionButtons: ReactElement[] = [];
  for (const option of pending.options) {
    const optionButton = (
      <button
        key={option}
        type="button"
        className="modal-option"
        disabled={isBusy}
        onClick={(): void => {
          onRespond(option);
        }}
      >
        {option}
      </button>
    );
    optionButtons.push(optionButton);
  }

  return (
    <div className="modal-backdrop">
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={HEADING_ELEMENT_ID}
      >
        <h2 id={HEADING_ELEMENT_ID}>{TOOL_RESPONSE_MODAL_HEADING}</h2>
        <p>{TOOL_RESPONSE_MODAL_EXPLANATION}</p>
        <p className="modal-tool-name">
          <code>{pending.toolName}</code>
        </p>
        <p className="tool-trace-label">{TOOL_TRACE_ARGUMENTS_LABEL}</p>
        <pre className="tool-trace-arguments">{argumentsText}</pre>
        <div className="modal-options">{optionButtons}</div>
      </div>
    </div>
  );
}
