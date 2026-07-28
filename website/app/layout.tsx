import type { Metadata } from "next";
import "./globals.css";

const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL || "https://sunofriend.example.com";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "Sunofriend — Listen deeper. Create further.",
  description:
    "Named from the Hindi सुनो, “listen”: Sunofriend turns separated music stems into editable MIDI and a balanced MIDI-derived song interpretation. Independent of Suno Inc.",
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
    title: "Sunofriend — Listen deeper. Create further.",
    description:
      "सुनो means “listen.” Sunofriend is an independent music tool that turns stems into editable MIDI and a balanced song interpretation—not a Suno Inc. product.",
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
    title: "Sunofriend — Listen deeper. Create further.",
    description:
      "Named from Hindi सुनो, “listen.” Independent of Suno Inc. Stems in; editable MIDI and a balanced interpretation out.",
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
