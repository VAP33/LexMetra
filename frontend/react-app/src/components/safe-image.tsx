import React, { useState, useEffect, forwardRef } from "react";
import { fetchBlobUrl, resolveImageUrl } from "../lib/api-client";

export interface SafeImageProps extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, "src"> {
  src?: string | null;
  fallbackSrc?: string;
  onLoadedDimensions?: (dimensions: { naturalWidth: number; naturalHeight: number }) => void;
}

export const SafeImage = forwardRef<HTMLImageElement, SafeImageProps>(function SafeImage(
  {
    src,
    fallbackSrc,
    alt = "",
    className = "",
    onLoadedDimensions,
    onLoad,
    onError,
    ...props
  },
  ref
) {
  const [blobUrl, setBlobUrl] = useState<string | null>(() => {
    if (!src) return null;
    if (src.startsWith("data:") || src.startsWith("blob:")) return src;
    return null;
  });

  useEffect(() => {
    let active = true;

    if (!src) {
      setBlobUrl(null);
      return;
    }

    if (src.startsWith("data:") || src.startsWith("blob:")) {
      setBlobUrl(src);
      return;
    }

    fetchBlobUrl(src)
      .then((resolvedBlobUrl) => {
        if (!active) return;
        if (resolvedBlobUrl) {
          setBlobUrl(resolvedBlobUrl);
        } else {
          setBlobUrl(resolveImageUrl(src) || src);
        }
      })
      .catch(() => {
        if (!active) return;
        setBlobUrl(resolveImageUrl(src) || src);
      });

    return () => {
      active = false;
    };
  }, [src]);

  if (!src && !fallbackSrc) {
    return null;
  }

  const finalSrc = blobUrl || fallbackSrc || (src ? resolveImageUrl(src) || src : undefined);

  if (!finalSrc) {
    return null;
  }

  return (
    <img
      {...props}
      ref={ref}
      src={finalSrc}
      alt={alt}
      className={className}
      onLoad={(e) => {
        const img = e.currentTarget;
        if (img.naturalWidth > 0 && onLoadedDimensions) {
          onLoadedDimensions({
            naturalWidth: img.naturalWidth,
            naturalHeight: img.naturalHeight,
          });
        }
        onLoad?.(e);
      }}
      onError={(e) => {
        if (fallbackSrc && blobUrl !== fallbackSrc) {
          setBlobUrl(fallbackSrc);
        }
        onError?.(e);
      }}
    />
  );
});
