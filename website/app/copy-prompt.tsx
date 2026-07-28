"use client";

import { useState } from "react";

export function CopyPrompt({
  prompt,
  label = "STARTER PROMPT FOR CODEX",
}: {
  prompt: string;
  label?: string;
}) {
  const [status, setStatus] = useState("Copy prompt");

  async function copy() {
    try {
      await navigator.clipboard.writeText(prompt);
      setStatus("Copied");
      window.setTimeout(() => setStatus("Copy prompt"), 1800);
    } catch {
      setStatus("Select the text");
    }
  }

  return (
    <div className="prompt-box">
      <div className="prompt-top">
        <span>{label}</span>
        <button type="button" onClick={copy}>
          {status}
        </button>
      </div>
      <textarea
        aria-label="Sunofriend starter prompt for Codex"
        readOnly
        value={prompt}
        rows={16}
        onFocus={(event) => event.currentTarget.select()}
      />
      <p>
        Paste this into <strong>Codex with local workspace access</strong>.
        A normal ChatGPT conversation can explain the steps, but it cannot
        quietly run commands or inspect files on your Mac.
      </p>
    </div>
  );
}
