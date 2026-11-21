"use client";

import { useCallback } from "react";
import TonightStrip from "@/components/home/TonightStrip";
import UpTonight from "@/components/home/UpTonight";
import { ApiErrorNotice, ConstellationSkeleton, WakingTelescope } from "@/components/ui/LoadingStates";
import { useApiResource } from "@/hooks/useApiResource";
import { formatLocation, useLocation } from "@/hooks/useLocation";
import { toTonightSummary } from "@/lib/adapters";
import { api, type RequestOptions } from "@/lib/api";

/** "Tonight's sky" for the saved location, live from the API's /tonight. */
export default function TonightSection() {
  const { location, ready } = useLocation();
  const fetcher = useCallback((opts: RequestOptions) => api.tonight(location, opts), [location]);
  // Wait until the saved location has been read, so we don't fetch the default first.
  const key = ready ? `${location.lat},${location.lon},${location.tz}` : null;
  const { data, status, error, retry } = useApiResource(key, fetcher);

  return (
    <section id="tonight" className="mx-auto max-w-[100rem] scroll-mt-28 px-6 pt-10 sm:px-10 lg:px-16">
      <div className="mb-5 flex flex-wrap items-baseline justify-between gap-3">
        <p className="label-caps">Tonight&apos;s sky</p>
        <p className="text-xs text-muted tabular-nums">{formatLocation(location)}</p>
      </div>

      {data ? (
        <>
          <TonightStrip key={key} data={toTonightSummary(data)} />
          <div className="mt-10">
            <UpTonight items={data.up_tonight} />
          </div>
        </>
      ) : status === "waking" ? (
        <div className="glass rounded-3xl px-6 py-12">
          <WakingTelescope />
        </div>
      ) : status === "error" && error ? (
        <div className="glass rounded-3xl px-6 py-12">
          <ApiErrorNotice
            message={error.status === null
              ? "We couldn't reach the AstraGraph server. Check your connection, or try again in a moment."
              : error.message}
            onRetry={retry}
          />
        </div>
      ) : (
        <div className="glass rounded-3xl px-6 py-10">
          <ConstellationSkeleton label="Loading tonight's sky" />
        </div>
      )}
      {data && status === "error" && (
        <p className="mt-3 text-xs text-muted" role="status">
          Couldn&apos;t refresh just now; showing the last result.{" "}
          <button type="button" onClick={retry} className="text-gold underline-offset-4 hover:underline">Retry</button>
        </p>
      )}
    </section>
  );
}
