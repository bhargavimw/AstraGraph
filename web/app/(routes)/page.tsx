import CameraDemo from "@/components/home/CameraDemo";
import Footer from "@/components/home/Footer";
import Hero from "@/components/home/Hero";
import QuizDemo from "@/components/home/QuizDemo";
import SkyMotionDemo from "@/components/home/SkyMotionDemo";
import StoriesDemo from "@/components/home/StoriesDemo";
import StorySection from "@/components/home/StorySection";
import TonightSection from "@/components/home/TonightSection";

export default function HomePage() {
  return (
    <>
      <Hero />

      <TonightSection />

      <StorySection
        index="01"
        label="Live camera"
        title={<>Point your camera.<br /><span className="text-muted">We&apos;ll find the stars.</span></>}
        visual={<CameraDemo />}
      >
        <p>
          AstraGraph recognises constellations from the shape of the stars themselves, so it works even
          when your phone&apos;s compass is wrong.
        </p>
        <p>Clouds in the way? Hidden stars are worked out and drawn as ghosts. Satellites get tracked too.</p>
      </StorySection>

      <StorySection
        index="02"
        label="Time travel"
        title={<>Watch the sky<br /><span className="text-muted">turn overhead.</span></>}
        visual={<SkyMotionDemo />}
        flip
      >
        <p>
          A whole day of sky from where you are, in seconds. Stars rise in the east, swing overhead and set
          in the west, all computed from real orbital mechanics.
        </p>
      </StorySection>

      <StorySection
        index="03"
        label="Learn"
        title={<>Every pattern<br /><span className="text-muted">has a story.</span></>}
        visual={<StoriesDemo />}
      >
        <p>
          Hunters, queens and bears: the myths behind the constellations, with the facts about their
          brightest stars.
        </p>
      </StorySection>

      <StorySection
        index="04"
        label="Academy"
        title={<>Test yourself.<br /><span className="text-muted">Draw the sky.</span></>}
        visual={<QuizDemo />}
        flip
      >
        <p>Connect the stars to build a constellation. Click one star, then another, to join them.</p>
        <p>Can you draw Cassiopeia&apos;s famous W?</p>
      </StorySection>

      <Footer />
    </>
  );
}
