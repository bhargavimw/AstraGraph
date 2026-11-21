import type { Metadata } from "next";
import PagePlaceholder from "@/components/ui/PagePlaceholder";

export const metadata: Metadata = { title: "Time Travel" };

export default function TimeTravelPage() {
  return <PagePlaceholder label="Time Travel" title="Time Travel" subtitle="Slide through 24 hours of sky. Coming in step 4." />;
}
