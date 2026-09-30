/**
 * One message typed by the person, rendered as plain text.
 */

import { MessagePrimitive } from "@assistant-ui/react";
import type { ReactElement } from "react";

/**
 * Render one user message.
 *
 * @returns The message block.
 */
export function UserMessage(): ReactElement {
  return (
    <MessagePrimitive.Root className="message message-user">
      <MessagePrimitive.Parts />
    </MessagePrimitive.Root>
  );
}
