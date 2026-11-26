/**
 * Page transition: every navigation re-mounts this template, so each page
 * fades in while rising slightly (350 ms). It is a CSS animation (`.page-enter`
 * in globals.css), so pages are visible as soon as the HTML arrives, without
 * waiting for JavaScript. Reduced motion: no movement.
 * (Exit animations are not reliable with the App Router, so pages enter only.)
 */
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
