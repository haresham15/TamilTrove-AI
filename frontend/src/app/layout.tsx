import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://tamiltrove.com"),
  title: "TamilTrove | Kollywood AI Search Engine & Movie Discovery",
  description: "Discover modern Tamil cinema (Kollywood) masterpieces. Describe the narrative vibe, plot, or aesthetics of your favorite films, and our AI will find the perfect counterpart.",
  keywords: ["Tamil cinema", "Kollywood", "AI movie search", "Tamil movies 2024", "semantic movie search", "Tamil movie recommendations", "Kollywood hidden gems"],
  authors: [{ name: "TamilTrove" }],
  creator: "TamilTrove AI",
  publisher: "TamilTrove",
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://tamiltrove.com",
    title: "TamilTrove | Kollywood AI Search Engine",
    description: "Discover modern Tamil cinema. Describe the narrative vibe and our AI will find the perfect counterpart.",
    siteName: "TamilTrove",
    images: [
      {
        url: "/logo.png",
        width: 512,
        height: 512,
        alt: "TamilTrove Logo",
      }
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "TamilTrove | Kollywood AI Search Engine",
    description: "Discover modern Tamil cinema with semantic AI search.",
    images: ["/logo.png"],
  },
  icons: {
    icon: "/icon.png",
    apple: "/icon.png",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
