import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import Starfield from "@/components/sky/Starfield";
import TopNav from "@/components/ui/TopNav";
import { LocationProvider } from "@/hooks/useLocation";
import "./globals.css";

const display = Space_Grotesk({
  subsets: ["latin"],
  weight: ["300", "400", "500"],
  variable: "--font-space-grotesk",
  display: "swap",
});

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: { default: "AstraGraph — your window to the night sky", template: "%s · AstraGraph" },
  description:
    "Find constellations with your camera, travel through time to see tomorrow's sky, and learn the stories written in the stars.",
  applicationName: "AstraGraph",
  openGraph: {
    title: "AstraGraph — your window to the night sky",
    description: "An immersive planetarium in your browser.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#05070f",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${sans.variable}`}>
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-full focus:bg-gold focus:px-4 focus:py-2 focus:text-void"
        >
          Skip to content
        </a>
        <LocationProvider>
          <Starfield />
          <TopNav />
          <main id="main" className="relative">
            {children}
          </main>
        </LocationProvider>
      </body>
    </html>
  );
}
