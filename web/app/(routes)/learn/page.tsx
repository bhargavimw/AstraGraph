import type { Metadata } from "next";
import PagePlaceholder from "@/components/ui/PagePlaceholder";

export const metadata: Metadata = { title: "Learn" };

export default function LearnPage() {
  return <PagePlaceholder label="Learn" title="Learn" subtitle="Meet the constellations. Coming in step 5." />;
}
