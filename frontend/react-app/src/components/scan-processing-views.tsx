import React, { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  LoaderCircle,
  RefreshCcw,
  WifiOff,
} from "lucide-react";
import { type Inspection } from "@/lib/types";
import { ApiError, preprocessParallel } from "@/lib/api-client";
import { dataUrlToBlob } from "@/lib/data-url";
import { Button } from "./ui-primitives";
import { TeslaScannerAnimation } from "./tesla-scanner-animation";
import { BeforeAfterSlider } from "./before-after-slider";


export function PreprocessingRunner({
  images,
  onDone,
  onError,
}: {
  images: string[];
  onDone: (canonicalUrls: string[]) => void;
  onError: (msg: string) => void;
}) {
  const [stageIdx, setStageIdx] = useState(0);
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    // Step through the 5 CV normalization stages
    const interval = window.setInterval(() => {
      setStageIdx((value) => Math.min(value + 1, 4));
    }, 500);

    const minDisplay = new Promise((resolve) => window.setTimeout(resolve, 1200));

    const executePreprocessing = async (): Promise<string[]> => {
      if (!images || images.length === 0) return [];
      try {
        const blobs = images.map(dataUrlToBlob);
        const res = await preprocessParallel(blobs);
        if (res && res.faces) {
          const canonicalUrls = Object.values(res.faces)
            .map((f) => f.canonical_image_url)
            .filter(Boolean);
          if (canonicalUrls.length > 0) {
            return canonicalUrls;
          }
        }
      } catch (err) {
        console.warn("[Offline Engine] Preprocessing server unreachable, running on client:", err);
      }
      return images;
    };

    Promise.all([executePreprocessing(), minDisplay])
      .then(([canonicalUrls]) => {
        window.clearInterval(interval);
        setStageIdx(4);
        window.setTimeout(() => onDone(canonicalUrls), 300);
      })
      .catch(() => {
        window.clearInterval(interval);
        setStageIdx(4);
        window.setTimeout(() => onDone(images), 300);
      });

    return () => window.clearInterval(interval);
  }, [images, onDone, onError]);

  return (
    <div className="min-h-screen bg-white">
      <TeslaScannerAnimation stageIndex={stageIdx} />
    </div>
  );
}

export function ProcessingRunner({
  onRun,
  onDone,
  onError,
}: {
  onRun: () => Promise<Inspection>;
  onDone: (inspection: Inspection) => void;
  onError: (message: string) => void;
}) {
  const [stageIdx, setStageIdx] = useState(0);

  const resultRef = useRef<Inspection | null>(null);
  const errorRef = useRef<any>(null);
  const isFinishedRef = useRef(false);
  const isStartedRef = useRef(false);
  const isCompletedRef = useRef(false);
  const currentStageRef = useRef(0);

  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const onRunRef = useRef(onRun);
  onRunRef.current = onRun;

  useEffect(() => {
    function attemptFinish() {
      if (isCompletedRef.current) return;
      // Only finish when we have reached the last box (stage 4) AND backend results are ready
      if (currentStageRef.current >= 4 && isFinishedRef.current) {
        isCompletedRef.current = true;
        if (errorRef.current) {
          console.error("[Inspection Flow Error]", errorRef.current);
          onErrorRef.current(
            errorRef.current instanceof ApiError
              ? errorRef.current.message
              : errorRef.current instanceof Error
              ? errorRef.current.message
              : "Inspection failed. Please check network and backend."
          );
        } else if (resultRef.current) {
          // Immediately load inspection results page!
          onDoneRef.current(resultRef.current);
        }
      }
    }

    // 1. Start scan once
    if (!isStartedRef.current) {
      isStartedRef.current = true;
      onRunRef.current()
        .then((res) => {
          resultRef.current = res;
          isFinishedRef.current = true;
          attemptFinish();
        })
        .catch((err) => {
          console.error("[Scan Error]", err);
          errorRef.current = err;
          isFinishedRef.current = true;
          attemptFinish();
        });
    }

    // 2. Stage timer: each box stays purple for approx 3 seconds (3000ms)
    // 0 (3s) -> 1 (3s) -> 2 (3s) -> 3 (3s) -> 4 (stops on last box until results load)
    const stageTimer = window.setInterval(() => {
      if (currentStageRef.current < 4) {
        currentStageRef.current += 1;
        setStageIdx(currentStageRef.current);
        if (currentStageRef.current === 4) {
          // Reached the last box! If results are already loaded, finish immediately!
          attemptFinish();
        }
      } else {
        // Stopped on the last box, waiting for results
        attemptFinish();
      }
    }, 3000);

    attemptFinish();

    return () => {
      window.clearInterval(stageTimer);
    };
  }, []);

  return (
    <div className="min-h-screen bg-white">
      <TeslaScannerAnimation stageIndex={stageIdx} />
    </div>
  );
}

export function ProcessingErrorView({ message, onRetry, onCancel }: { message: string; onRetry: () => void; onCancel: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-danger-soft text-destructive"><WifiOff className="h-9 w-9" /></div>
        <h1 className="mt-8 text-2xl font-semibold tracking-[-.04em]">Couldn't complete the check</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{message}</p>
        <div className="mt-8 flex justify-center gap-3">
          <Button variant="secondary" onClick={onCancel}>Cancel</Button>
          <Button onClick={onRetry}><RefreshCcw className="h-4 w-4" />Try again</Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Result
// ---------------------------------------------------------------------------


