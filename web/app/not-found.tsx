import Link from "next/link";

export default function NotFound() {
  return (
    <section className="mx-auto flex min-h-[100svh] max-w-3xl flex-col items-center justify-center px-6 pt-[var(--nav-height)] text-center">
      <p className="label-caps mb-6">404 · Lost in space</p>
      <h1 className="font-display text-5xl font-light leading-[1.05] tracking-tight text-ink sm:text-7xl">
        This page drifted out of orbit.
      </h1>
      <p className="mt-6 max-w-md text-base text-muted sm:text-lg">
        The page you were looking for doesn&apos;t exist, or has moved.
      </p>
      <Link
        href="/"
        className="mt-10 inline-flex min-h-11 items-center rounded-full bg-gold px-7 text-sm font-medium text-void shadow-[0_0_24px_rgb(245_196_81/0.35)] transition-shadow hover:shadow-[0_0_36px_rgb(245_196_81/0.6)]"
      >
        Back to the sky
      </Link>
    </section>
  );
}
