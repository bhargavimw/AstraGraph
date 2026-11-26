"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Camera access for the Live page.
 *
 * NOTE: browsers only allow the camera on secure pages: HTTPS, or
 * http://localhost while developing. On plain HTTP from another device (for
 * example a phone opening http://192.168.x.x:3000) `navigator.mediaDevices`
 * is missing and the status becomes "insecure".
 *
 * Prefers the rear camera on phones (facingMode "environment"). Every track
 * is stopped on `stop()` and when the component using the hook unmounts.
 */

export type CameraStatus = "idle" | "requesting" | "live" | "denied" | "unavailable" | "insecure" | "error";

export function useCamera() {
  const [status, setStatus] = useState<CameraStatus>("idle");
  const [stream, setStream] = useState<MediaStream | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setStream(null);
    setStatus((s) => (s === "live" || s === "requesting" ? "idle" : s));
  }, []);

  const start = useCallback(async () => {
    if (typeof window !== "undefined" && !window.isSecureContext) {
      setStatus("insecure");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("unavailable");
      return;
    }
    setStatus("requesting");
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      });
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = media;
      setStream(media);
      setStatus("live");
    } catch (error) {
      const name = error instanceof DOMException ? error.name : "";
      if (name === "NotAllowedError" || name === "SecurityError") setStatus("denied");
      else if (name === "NotFoundError" || name === "OverconstrainedError") setStatus("unavailable");
      else setStatus("error");
    }
  }, []);

  // Release the camera when the page goes away.
  useEffect(() => () => streamRef.current?.getTracks().forEach((t) => t.stop()), []);

  return { status, stream, start, stop };
}
