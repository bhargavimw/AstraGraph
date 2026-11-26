import Link from "next/link";
import Logo from "@/components/ui/Logo";

export default function Footer() {
  return (
    <footer className="mx-auto max-w-[100rem] px-6 pb-12 pt-24 sm:px-10 lg:px-16">
      <div className="h-px w-full bg-gradient-to-r from-transparent via-line to-transparent" aria-hidden="true" />
      <div className="mt-12 grid gap-10 md:grid-cols-[1.2fr_1fr_1fr]">
        <div>
          <Logo />
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-muted">
            Find constellations with your camera, see where everything will be tonight, and learn the
            stories behind the stars.
          </p>
        </div>
        <div>
          <p className="label-caps mb-4">Data</p>
          <ul className="space-y-2 text-sm text-muted">
            <li>
              Star data:{" "}
              <a href="https://github.com/astronexus/HYG-Database" className="underline decoration-line underline-offset-4 hover:text-ink">
                HYG Database v4.1
              </a>{" "}
              (CC BY-SA 4.0)
            </li>
            <li>
              Sky positions:{" "}
              <a href="https://rhodesmill.org/skyfield/" className="underline decoration-line underline-offset-4 hover:text-ink">
                Skyfield
              </a>{" "}
              + JPL DE421 ephemeris
            </li>
            <li>Constellation boundaries: IAU</li>
          </ul>
        </div>
        <div>
          <p className="label-caps mb-4">Privacy</p>
          <p className="text-sm leading-relaxed text-muted">
            Your location is saved only in this browser. While Live Camera is open, camera frames are sent
            to the AstraGraph server so it can find the stars in them; nothing is sent when it is closed.
          </p>
        </div>
      </div>
      <div className="mt-12 flex flex-wrap items-center justify-between gap-4 text-xs text-muted/70">
        <p>© {new Date().getFullYear()} AstraGraph</p>
        <nav aria-label="Footer" className="flex gap-6">
          <Link href="/live" className="hover:text-ink">Live</Link>
          <Link href="/time-travel" className="hover:text-ink">Time Travel</Link>
          <Link href="/learn" className="hover:text-ink">Learn</Link>
          <Link href="/gallery" className="hover:text-ink">Gallery</Link>
        </nav>
      </div>
    </footer>
  );
}
