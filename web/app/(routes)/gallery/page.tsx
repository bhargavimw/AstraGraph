import type { Metadata } from "next";
import { Suspense } from "react";
import Gallery from "@/components/gallery/Gallery";
import Footer from "@/components/home/Footer";
import { ConstellationSkeleton } from "@/components/ui/LoadingStates";

export const metadata: Metadata = {
  title: "Wallpapers",
  description: "Phone wallpapers of the real night sky over nine cities, in four styles. Free to download.",
};

export default function GalleryPage() {
  // Gallery reads its filters from the address (?city=&style=), which needs a Suspense boundary.
  return (
    <>
      <Suspense fallback={<ConstellationSkeleton className="min-h-[100svh]" label="Loading the gallery" />}>
        <Gallery />
      </Suspense>
      <Footer />
    </>
  );
}
