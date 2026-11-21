import type { Metadata } from "next";
import PagePlaceholder from "@/components/ui/PagePlaceholder";

export const metadata: Metadata = { title: "Live" };

export default function LivePage() {
  return <PagePlaceholder label="Live Camera" title="Live" subtitle="Point your camera at the sky. Coming in step 6." />;
}
