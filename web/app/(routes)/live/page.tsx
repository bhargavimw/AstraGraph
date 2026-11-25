import type { Metadata } from "next";
import LiveCamera from "@/components/live/LiveCamera";

export const metadata: Metadata = {
  title: "Live Camera",
  description: "Point your camera at the night sky: AstraGraph finds the stars, names the constellations and spots satellites.",
};

export default function LivePage() {
  return <LiveCamera />;
}
