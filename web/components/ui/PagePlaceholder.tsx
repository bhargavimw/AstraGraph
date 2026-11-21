/** Temporary page body used until each route is built (step 1 scaffold). */
export default function PagePlaceholder({
  label,
  title,
  subtitle,
}: {
  label: string;
  title: string;
  subtitle: string;
}) {
  return (
    <section className="mx-auto flex min-h-[100dvh] max-w-5xl flex-col items-center justify-center px-6 pt-[var(--nav-height)] text-center">
      <p className="label-caps mb-6">{label}</p>
      <h1 className="font-display text-5xl font-light leading-[1.05] tracking-tight text-ink sm:text-7xl">
        {title}
      </h1>
      <p className="mt-6 max-w-xl text-base text-muted sm:text-lg">{subtitle}</p>
    </section>
  );
}
