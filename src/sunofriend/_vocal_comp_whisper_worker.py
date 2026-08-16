"""Isolated OpenAI Whisper worker for private word-timestamp evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--model-label", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import whisper

    model = whisper.load_model(args.checkpoint, device="cpu")
    result = model.transcribe(
        args.audio,
        language="en",
        task="transcribe",
        word_timestamps=True,
        condition_on_previous_text=False,
        initial_prompt=None,
        fp16=False,
        temperature=0.0,
        verbose=None,
    )
    segments = []
    for segment in result.get("segments", []):
        segments.append(
            {
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "text": str(segment.get("text", "")),
                "avg_logprob": segment.get("avg_logprob"),
                "compression_ratio": segment.get("compression_ratio"),
                "no_speech_prob": segment.get("no_speech_prob"),
                "words": [
                    {
                        "word": str(word.get("word", "")),
                        "start": float(word["start"]),
                        "end": float(word["end"]),
                        "probability": float(word.get("probability", 0.0)),
                    }
                    for word in segment.get("words", [])
                ],
            }
        )
    document = {
        "schema": "sunofriend.vocal-comp-stt-candidate.v1",
        "status": "complete_unreviewed",
        "engine": "openai-whisper",
        "engine_version": getattr(whisper, "__version__", "unknown"),
        "model": args.model_label,
        "language": result.get("language", "en"),
        "text": str(result.get("text", "")),
        "segments": segments,
        "canonical_lyrics_prompted": False,
        "condition_on_previous_text": False,
        "word_timestamps": True,
        "network_used": False,
    }
    output = Path(args.out)
    output.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.chmod(output, 0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
