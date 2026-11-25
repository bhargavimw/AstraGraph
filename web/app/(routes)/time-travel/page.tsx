import type { Metadata } from "next";
import TimeTravel from "@/components/time-travel/TimeTravel";

export const metadata: Metadata = {
  title: "Time Travel",
  description: "Slide through 24 hours of sky and watch the constellations rise, cross and set.",
};

export default function TimeTravelPage() {
  return <TimeTravel />;
}
