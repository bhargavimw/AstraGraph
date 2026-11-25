import type { Metadata } from "next";
import { Suspense } from "react";
import Learn from "@/components/learn/Learn";
import { ConstellationSkeleton } from "@/components/ui/LoadingStates";

export const metadata: Metadata = {
  title: "Learn",
  description: "Meet the constellations: charts, star facts, the best month to look, and when each one rises tonight.",
};

export default function LearnPage() {
  // Learn reads ?c= from the address, which needs a Suspense boundary.
  return (
    <Suspense fallback={<ConstellationSkeleton className="min-h-[100svh]" label="Loading" />}>
      <Learn />
    </Suspense>
  );
}
