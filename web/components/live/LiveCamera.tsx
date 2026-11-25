"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { HudFrame, Legend, Readout, type HudStats, type Link } from "@/components/hud/Hud";
import Overlay, { type FrameHistory, type Layer, type Layers } from "@/components/hud/Overlay";
import { CameraIcon, SparkleIcon, UploadIcon } from "@/components/ui/icons-extra";
import { ApiErrorNotice, WakingTelescope } from "@/components/ui/LoadingStates";
import { useCamera } from "@/hooks/useCamera";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { api, ApiError } from "@/lib/api";
import type { FitMode } from "@/lib/overlay";
import type { ApiDemoSkyInfo } from "@/lib/types";

/**
 * Live Camera: a full-screen picture (webcam, uploaded photo/video, or the
 * built-in demo sky) with the AstraGraph analysis drawn over it.
 *
 * Capture loop: draw the current picture to an off-screen canvas (640 px wide),
 * encode it as JPEG (quality 0.7) and POST it to /frame. The next frame is only
 * sent after the previous answer has arrived, so requests never pile up — slow
 * connections simply analyse fewer frames.
 *
 * The camera needs a secure page (HTTPS or localhost); see hooks/useCamera.ts.
 */

type Source = "webcam" | "upload" | "demo";
interface UploadedFile { url: string; kind: "image" | "video"; name: string }

const SEND_WIDTH = 640;
const JPEG_QUALITY = 0.7;
const INTERVAL_MS: Record<Source, number> = { webcam: 300, upload: 300, demo: 160 };
const ALL_LAYERS: Layers = { stars: true, lines: true, ghosts: true, satellites: true, anomalies: true };
const NO_STATS: HudStats = { stars: 0, constellations: 0, satellites: 0, anomalies: 0, fps: null, latencyMs: null };

const newSessionId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `s-${Date.now()}-${Math.random().toString(36).slice(2)}`;

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const id = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => { clearTimeout(id); resolve(); }, { once: true });
  });
}

/** Draw a video or image into a canvas `maxWidth` wide and encode it as JPEG. */
async function grab(
  el: HTMLVideoElement | HTMLImageElement | null,
  canvas: HTMLCanvasElement,
  maxWidth: number,
  quality: number,
): Promise<Blob | null> {
  if (!el) return null;
  const w = el instanceof HTMLVideoElement ? el.videoWidth : el.naturalWidth;
  const h = el instanceof HTMLVideoElement ? el.videoHeight : el.naturalHeight;
  if (el instanceof HTMLVideoElement && el.readyState < 2) return null;
  if (!w || !h) return null;
  const scale = Math.min(1, maxWidth / w);
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(el, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}

export default function LiveCamera() {
  const reduced = useReducedMotion();
  const camera = useCamera();
  const [source, setSource] = useState<Source>("webcam");
  const [upload, setUpload] = useState<UploadedFile | null>(null);
  const [demoName, setDemoName] = useState("Orion");
  const [demoInfo, setDemoInfo] = useState<ApiDemoSkyInfo | null>(null);
  const [demoFrame, setDemoFrame] = useState<string | null>(null);
  const [layers, setLayers] = useState<Layers>(ALL_LAYERS);
  const [stats, setStats] = useState<HudStats>(NO_STATS);
  const [link, setLink] = useState<Link>("idle");
  const [linkError, setLinkError] = useState<string | null>(null);
  const [names, setNames] = useState<string[]>([]);
  const [hasResult, setHasResult] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [wide, setWide] = useState(true);

  const history = useRef<FrameHistory>({ prev: null, cur: null, at: 0 });
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => setWide(window.matchMedia("(min-width: 768px)").matches), []);

  const usesImage = source === "demo" || (source === "upload" && upload?.kind === "image");
  const fit: FitMode = source === "webcam" ? "cover" : "contain";

  const sourceSize = useCallback(() => {
    const video = videoRef.current;
    if (video && video.videoWidth) return { width: video.videoWidth, height: video.videoHeight };
    const img = imageRef.current;
    if (img && img.naturalWidth) return { width: img.naturalWidth, height: img.naturalHeight };
    return null;
  }, []);

  // Webcam stream → <video>.
  useEffect(() => {
    if (source === "webcam" && videoRef.current && camera.stream) videoRef.current.srcObject = camera.stream;
  }, [source, camera.stream]);

  // Leaving the webcam releases the camera.
  useEffect(() => {
    if (source !== "webcam") camera.stop();
  }, [source, camera.stop]); // eslint-disable-line react-hooks/exhaustive-deps

  // Free the uploaded file's object URL when it is replaced.
  useEffect(() => () => { if (upload) URL.revokeObjectURL(upload.url); }, [upload]);
  useEffect(() => () => { if (demoFrame) URL.revokeObjectURL(demoFrame); }, [demoFrame]);

  // ------------------------------------------------------------ capture loop
  const active = source === "webcam" ? camera.status === "live" : source === "upload" ? upload !== null : true;

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const { signal } = controller;
    const canvas = document.createElement("canvas");
    history.current = { prev: null, cur: null, at: 0 };
    setStats(NO_STATS);
    setNames([]);
    setHasResult(false);
    setLinkError(null);
    setLink("idle");
    if (source === "demo") setDemoFrame(null);

    const run = async () => {
      // Make sure the server is awake before streaming frames.
      try {
        await api.health({ signal, onWaking: () => !signal.aborted && setLink("waking") });
      } catch (error) {
        if (signal.aborted) return;
        setLink("error");
        setLinkError(error instanceof ApiError && error.status !== null ? error.message
          : "We couldn't reach the AstraGraph server. Check your connection, or try again in a moment.");
        return;
      }
      if (signal.aborted) return;
      setLink("ok");

      let session = newSessionId();
      let info: ApiDemoSkyInfo | null = null;
      if (source === "demo") {
        info = demoInfo ?? (await api.demoSky({ signal }).catch(() => null));
        if (signal.aborted) return;
        if (info) setDemoInfo(info);
      }
      let demoIndex = 0;
      let lastAnswer: number | null = null;
      let fps: number | null = null;
      let latency: number | null = null;
      let failures = 0;

      while (!signal.aborted) {
        const started = performance.now();
        // A hidden tab sends nothing.
        if (document.hidden) {
          await sleep(500, signal);
          lastAnswer = null;
          continue;
        }

        let blob: Blob | null = null;
        if (source === "demo") {
          try {
            const res = await fetch(api.demoFrameUrl(demoName, demoIndex), { signal });
            if (res.ok) blob = await res.blob();
          } catch {
            blob = null;
          }
          demoIndex = (demoIndex + 1) % (info?.frame_count ?? 120);
        } else if (source === "upload" && upload?.kind === "image") {
          await imageRef.current?.decode().catch(() => undefined);
          blob = await grab(imageRef.current, canvas, 1280, 0.85); // a photo: analyse once, at higher quality
        } else {
          blob = await grab(videoRef.current, canvas, SEND_WIDTH, JPEG_QUALITY);
        }
        if (signal.aborted) return;

        if (blob) {
          const sentAt = performance.now();
          try {
            const result = await api.frame(blob, session, { signal });
            if (signal.aborted) return;
            const now = performance.now();
            if (source === "demo") {
              // Show the picture and its analysis together.
              setDemoFrame(URL.createObjectURL(blob));
              await new Promise((r) => requestAnimationFrame(() => r(null)));
            }
            history.current = { prev: history.current.cur, cur: result, at: performance.now() };
            latency = latency === null ? now - sentAt : latency * 0.7 + (now - sentAt) * 0.3;
            if (lastAnswer !== null) {
              const rate = 1000 / (now - lastAnswer);
              fps = fps === null ? rate : fps * 0.7 + rate * 0.3;
            }
            lastAnswer = now;
            failures = 0;
            setLink("ok");
            setHasResult(true);
            setStats({
              stars: result.stars.length,
              constellations: result.constellations.length,
              satellites: result.satellites.length,
              anomalies: result.anomalies.length,
              fps,
              latencyMs: latency,
            });
            const found = result.constellations.map((c) => c.name).sort();
            setNames((old) => (old.join() === found.join() ? old : found));
          } catch {
            if (signal.aborted) return;
            failures += 1;
            setLink("error");
            lastAnswer = null;
            await sleep(Math.min(8000, 1000 * 2 ** Math.min(failures, 3)), signal);
            continue;
          }
          // The demo clip loops: start a fresh tracking session each time round.
          if (source === "demo" && demoIndex === 0) session = newSessionId();
        }

        if (source === "upload" && upload?.kind === "image") return;
        const wait = INTERVAL_MS[source] - (performance.now() - started);
        if (wait > 0) await sleep(wait, signal);
      }
    };
    void run();
    return () => controller.abort();
  }, [active, source, upload, demoName, attempt]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleLayer = useCallback((layer: Layer) => setLayers((l) => ({ ...l, [layer]: !l[layer] })), []);

  const onFile = (file: File | undefined) => {
    if (!file) return;
    const kind = file.type.startsWith("video/") ? "video" : file.type.startsWith("image/") ? "image" : null;
    if (!kind) return;
    setUpload({ url: URL.createObjectURL(file), kind, name: file.name });
    setSource("upload");
  };

  const showMedia =
    (source === "webcam" && camera.status === "live") ||
    (source === "upload" && upload !== null) ||
    (source === "demo" && demoFrame !== null);

  // ----------------------------------------------------------------- screens
  let screen: ReactNode = null;
  if (link === "error" && !hasResult && linkError) {
    screen = <ApiErrorNotice message={linkError} onRetry={() => setAttempt((n) => n + 1)} />;
  } else if (link === "waking" && !hasResult) {
    screen = <WakingTelescope />;
  } else if (source === "webcam" && camera.status !== "live") {
    screen = <CameraScreen status={camera.status} onAllow={camera.start} onUpload={() => fileInput.current?.click()} onDemo={() => setSource("demo")} />;
  } else if (source === "upload" && !upload) {
    screen = <UploadScreen onPick={() => fileInput.current?.click()} onFile={onFile} />;
  } else if (source === "demo" && !demoFrame) {
    screen = <p className="font-display text-lg font-light text-muted">Loading the demo sky…</p>;
  }

  return (
    <section className="relative h-[100svh] min-h-[32rem] overflow-hidden bg-void" aria-label="Live camera">
      {/* Picture */}
      {source === "webcam" && (
        <video ref={videoRef} autoPlay playsInline muted
          className={`absolute inset-0 h-full w-full object-cover ${camera.status === "live" ? "" : "hidden"}`} />
      )}
      {source === "upload" && upload?.kind === "video" && (
        <video ref={videoRef} key={upload.url} src={upload.url} autoPlay loop playsInline muted
          className="absolute inset-0 h-full w-full object-contain" />
      )}
      {usesImage && (source === "demo" ? demoFrame : upload?.url) && (
        // eslint-disable-next-line @next/next/no-img-element -- blob: URLs from the camera pipeline
        <img
          ref={imageRef}
          src={(source === "demo" ? demoFrame : upload?.url) ?? undefined}
          alt={source === "demo" ? `Demo sky: ${demoName}` : `Your photo: ${upload?.name ?? ""}`}
          className="absolute inset-0 h-full w-full object-contain"
        />
      )}

      {showMedia && (
        <>
          <Overlay history={history} sourceSize={sourceSize} fit={fit} layers={layers} reduced={reduced} />
          <HudFrame />
        </>
      )}

      {/* Centre screens (permission, upload, waking, errors) */}
      <AnimatePresence mode="wait">
        {screen && (
          <motion.div
            key={`${source}-${camera.status}-${link}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="absolute inset-0 flex items-center justify-center px-6 pt-[calc(var(--nav-height)+4rem)]"
          >
            {screen}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Source switcher */}
      <div data-hud className="absolute inset-x-0 top-[calc(var(--nav-height)+0.75rem)] z-20 mx-auto flex w-fit flex-col items-center gap-2 px-4">
        <SourceSwitcher source={source} onChange={setSource} />
        {source === "demo" && (
          <label className="glass flex min-h-10 items-center gap-2 rounded-full pl-4 pr-2 text-xs text-muted">
            Demo of
            <select
              value={demoName}
              onChange={(e) => setDemoName(e.target.value)}
              className="min-h-9 rounded-full bg-transparent px-2 text-sm text-ink outline-none [&>option]:bg-deep"
            >
              {(demoInfo?.constellations ?? ["Orion"]).map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        )}
        {source === "upload" && upload && (
          <button type="button" onClick={() => fileInput.current?.click()}
            className="glass min-h-10 max-w-[80vw] truncate rounded-full px-4 text-xs text-muted transition-colors hover:text-gold">
            {upload.name} · choose another
          </button>
        )}
      </div>

      {/* HUD readout + legend */}
      {showMedia && (
        <div className="absolute inset-x-4 bottom-4 z-20 flex items-end justify-between gap-3 sm:inset-x-8 sm:bottom-8">
          <div data-hud><Readout stats={stats} link={link} names={names} /></div>
          <div data-hud><Legend layers={layers} onToggle={toggleLayer} defaultOpen={wide} /></div>
        </div>
      )}
      <p className="sr-only" aria-live="polite">
        {names.length ? `Identified: ${names.join(", ")}` : ""}
      </p>

      <input
        ref={fileInput}
        type="file"
        accept="image/*,video/*"
        className="hidden"
        onChange={(e) => {
          onFile(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
    </section>
  );
}

// ------------------------------------------------------------------ pieces
const SOURCES: Array<{ id: Source; label: string; icon: ReactNode }> = [
  { id: "webcam", label: "Webcam", icon: <CameraIcon size={16} /> },
  { id: "upload", label: "Upload", icon: <UploadIcon size={16} /> },
  { id: "demo", label: "Demo sky", icon: <SparkleIcon size={16} /> },
];

function SourceSwitcher({ source, onChange }: { source: Source; onChange: (s: Source) => void }) {
  return (
    <div role="group" aria-label="Picture source" className="glass flex rounded-full p-1">
      {SOURCES.map(({ id, label, icon }) => {
        const on = id === source;
        return (
          <button
            key={id}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(id)}
            className={`relative flex min-h-10 items-center gap-2 rounded-full px-3.5 text-sm transition-colors sm:px-4 ${on ? "text-void" : "text-ink/80 hover:text-ink"}`}
          >
            {on && (
              <motion.span layoutId="source-pill" className="absolute inset-0 rounded-full bg-gold shadow-[0_0_18px_rgb(245_196_81/0.45)]"
                transition={{ type: "spring", stiffness: 420, damping: 34 }} />
            )}
            <span className="relative">{icon}</span>
            <span className="relative">{label}</span>
          </button>
        );
      })}
    </div>
  );
}

function ScreenCard({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="flex max-w-md flex-col items-center text-center">
      <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full border border-gold/40 text-gold shadow-[0_0_40px_rgb(245_196_81/0.15)]">
        {icon}
      </div>
      <h1 className="font-display text-3xl font-light text-ink sm:text-4xl">{title}</h1>
      {children}
    </div>
  );
}

const primary = "min-h-11 rounded-full bg-gold px-6 text-sm font-medium text-void shadow-[0_0_24px_rgb(245_196_81/0.35)] transition-shadow hover:shadow-[0_0_36px_rgb(245_196_81/0.6)]";
const ghost = "min-h-11 rounded-full border border-line px-5 text-sm text-ink transition-colors hover:border-gold/50 hover:text-gold";

function CameraScreen({ status, onAllow, onUpload, onDemo }: {
  status: ReturnType<typeof useCamera>["status"];
  onAllow: () => void;
  onUpload: () => void;
  onDemo: () => void;
}) {
  const fallback = (
    <div className="mt-6 flex flex-wrap justify-center gap-3">
      <button type="button" onClick={onUpload} className={ghost}>Upload a photo</button>
      <button type="button" onClick={onDemo} className={ghost}>Try the demo sky</button>
    </div>
  );
  const text = "mt-4 text-sm leading-relaxed text-muted";

  if (status === "denied") {
    return (
      <ScreenCard icon={<CameraIcon size={30} />} title="Camera blocked">
        <p className={text}>
          Your browser is blocking the camera for this site. Allow it from the camera icon in the address bar, then
          reload — or use a photo or the demo sky instead.
        </p>
        {fallback}
      </ScreenCard>
    );
  }
  if (status === "insecure" || status === "unavailable" || status === "error") {
    const message = status === "insecure"
      ? "The camera only works on a secure (https://) page. Open AstraGraph over HTTPS to use it."
      : status === "unavailable"
        ? "No camera was found on this device."
        : "The camera couldn't be started. It may be in use by another app.";
    return (
      <ScreenCard icon={<CameraIcon size={30} />} title="Camera unavailable">
        <p className={text}>{message}</p>
        {fallback}
      </ScreenCard>
    );
  }
  return (
    <ScreenCard icon={<CameraIcon size={30} />} title="Point your camera at the sky">
      <p className={text}>
        AstraGraph finds stars, names constellations and spots satellites in real time. Frames go to the AstraGraph
        server to be analysed and are not saved. On a phone, the rear camera is used.
      </p>
      <div className="mt-7 flex flex-wrap justify-center gap-3">
        <button type="button" onClick={onAllow} disabled={status === "requesting"} className={`${primary} disabled:opacity-60`}>
          {status === "requesting" ? "Waiting for permission…" : "Allow camera"}
        </button>
        <button type="button" onClick={onDemo} className={ghost}>Try the demo sky</button>
      </div>
    </ScreenCard>
  );
}

function UploadScreen({ onPick, onFile }: { onPick: () => void; onFile: (f: File | undefined) => void }) {
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onFile(e.dataTransfer.files[0]); }}
      className={`rounded-[2rem] border border-dashed px-8 py-10 transition-colors sm:px-14 ${over ? "border-gold/70 bg-gold/5" : "border-ink/20"}`}
    >
      <ScreenCard icon={<UploadIcon size={30} />} title="Upload the night sky">
        <p className="mt-4 text-sm leading-relaxed text-muted">
          Drop a photo or a short video of the stars here. Longer exposures with less city light work best.
        </p>
        <div className="mt-7">
          <button type="button" onClick={onPick} className={primary}>Choose a file</button>
        </div>
      </ScreenCard>
    </div>
  );
}
