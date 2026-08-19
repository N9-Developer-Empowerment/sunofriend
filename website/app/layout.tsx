import type { Metadata } from "next";
import "./globals.css";

const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL || "https://sunofriend.com";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Sunofriend — Hear the song. Change the parts.",
    template: "%s — Sunofriend",
  },
  description:
    "Use the Sunofriend skill with a local coding agent to turn authorised music stems into editable MIDI, a balanced song-interpretation WAV and a starter ZIP. macOS is supported; native Windows setup is partially verified and documented.",
  applicationName: "Sunofriend",
  alternates: {
    canonical: "/",
  },
  keywords: [
    "Sunofriend",
    "सुनो",
    "suno means listen",
    "listen deeper create further",
    "stems to MIDI",
    "audio to MIDI",
    "GarageBand MIDI",
    "third-party Suno stems",
    "Moises stems",
    "music transcription",
    "Codex music skill",
    "Claude Code music skill",
    "Antigravity music skill",
    "AI agent skill",
    "local music tool",
  ],
  authors: [{ name: "Unsigned Media Ltd" }],
  creator: "Unsigned Media Ltd",
  publisher: "Unsigned Media Ltd",
  icons: {
    icon: "/brand/sunofriend-logo.png",
    apple: "/brand/sunofriend-logo.png",
  },
  openGraph: {
    type: "website",
    title: "Sunofriend — Hear the song. Change the parts.",
    description:
      "Let a skills-aware coding agent guide the local setup. Authorised stems become editable MIDI, a balanced MIDI-derived listening WAV and a starter ZIP.",
    siteName: "Sunofriend",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "Sunofriend — सुनो means listen; listen deeper, create further; not affiliated with Suno Inc.",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Sunofriend — Hear the song. Change the parts.",
    description:
      "Use the Sunofriend skill with a local coding agent: authorised stems in; editable MIDI, listening WAV and a starter ZIP out.",
    images: ["/og.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
