/**
 * LexMetra Official PDF Generator
 * Uses jsPDF + html2canvas to render a fully self-contained PDF
 * that opens in a new browser tab directly (no print/save-as dialog).
 */
import jsPDF from "jspdf";
import html2canvas from "html2canvas";

export interface PdfProgress {
  stage: string;
  pct: number;
}

/**
 * Capture a DOM element (by id), paginate it, and open the resulting PDF
 * in a new browser tab.
 *
 * @param elementId  id of the root element to capture
 * @param onProgress optional progress callback
 */
export async function exportElementAsPdf(
  elementId: string,
  filename: string = "LexMetra_Inspection_Report.pdf",
  onProgress?: (p: PdfProgress) => void
): Promise<void> {
  const el = document.getElementById(elementId);
  if (!el) throw new Error(`Element #${elementId} not found`);

  onProgress?.({ stage: "Preparing document…", pct: 5 });

  // Temporarily un-hide any print-hidden elements that are relevant to PDF
  // We render a clone in off-screen position so the live page isn't affected.
  const clone = el.cloneNode(true) as HTMLElement;
  clone.style.position = "absolute";
  clone.style.top = "-99999px";
  clone.style.left = "0";
  clone.style.width = "1024px"; // fixed render width for consistent PDF
  clone.style.background = "#ffffff";
  clone.style.fontFamily = "sans-serif";
  // Remove on-screen action bar (print-hidden) from clone
  clone.querySelectorAll(".print-hidden").forEach((n) => (n as HTMLElement).remove());
  document.body.appendChild(clone);

  onProgress?.({ stage: "Preparing and loading document assets…", pct: 10 });

  // Ensure all images in the clone have finished loading before capturing
  const imgs = Array.from(clone.querySelectorAll("img"));
  await Promise.all(
    imgs.map((img) => {
      if (img.complete) return Promise.resolve();
      return new Promise<void>((resolve) => {
        img.onload = () => resolve();
        img.onerror = () => resolve();
        setTimeout(resolve, 2500);
      });
    })
  );

  // A4 in mm
  const A4_W = 210;
  const A4_H = 297;
  const MARGIN = 6; // mm - slim margins for maximum readable width

  const pageW = A4_W - MARGIN * 2;
  const pageContentH = A4_H - MARGIN * 2;

  const pdf = new jsPDF({
    orientation: "portrait",
    unit: "mm",
    format: "a4",
    compress: true,
  });

  const pageNodes = Array.from(clone.querySelectorAll<HTMLElement>("[data-report-page]"));
  let pageIndex = 0;

  try {
    if (pageNodes.length > 0) {
      for (let p = 0; p < pageNodes.length; p++) {
        onProgress?.({
          stage: `Composing certified page ${p + 1} of ${pageNodes.length}…`,
          pct: 20 + Math.round((p / pageNodes.length) * 70),
        });

        const pageEl = pageNodes[p];
        const pageCanvas = await html2canvas(pageEl, {
          scale: 2,
          useCORS: true,
          allowTaint: true,
          backgroundColor: "#ffffff",
          logging: false,
          windowWidth: 1024,
        });

        const imgW = pageCanvas.width;
        const imgH = pageCanvas.height;
        const mmPerPx = pageW / imgW;
        const renderH = imgH * mmPerPx;

        // Fit across the entire width (100% readable width)
        if (renderH <= pageContentH) {
          if (pageIndex > 0) pdf.addPage();
          pageIndex++;
          const dataUrl = pageCanvas.toDataURL("image/jpeg", 0.95);
          pdf.addImage(dataUrl, "JPEG", MARGIN, MARGIN, pageW, renderH, undefined, "FAST");
        } else {
          // If a section is taller than single page, slice vertically at full width
          const slicesCount = Math.ceil(renderH / pageContentH);
          for (let s = 0; s < slicesCount; s++) {
            const srcYPx = Math.round((s * pageContentH) / mmPerPx);
            const srcHPx = Math.min(Math.round(pageContentH / mmPerPx), imgH - srcYPx);
            if (srcHPx <= 0) continue;

            if (pageIndex > 0) pdf.addPage();
            pageIndex++;

            const sliceCanvas = document.createElement("canvas");
            sliceCanvas.width = imgW;
            sliceCanvas.height = srcHPx;
            const ctx = sliceCanvas.getContext("2d")!;
            ctx.drawImage(pageCanvas, 0, srcYPx, imgW, srcHPx, 0, 0, imgW, srcHPx);

            const sliceDataUrl = sliceCanvas.toDataURL("image/jpeg", 0.95);
            const sliceHMm = srcHPx * mmPerPx;
            pdf.addImage(sliceDataUrl, "JPEG", MARGIN, MARGIN, pageW, sliceHMm, undefined, "FAST");
          }
        }
      }
    } else {
      // Fallback: render continuous canvas if no page markers exist
      onProgress?.({ stage: "Rendering full dossier…", pct: 30 });
      const canvas = await html2canvas(clone, {
        scale: 2,
        useCORS: true,
        allowTaint: true,
        backgroundColor: "#ffffff",
        logging: false,
        windowWidth: 1024,
      });

      const imgW = canvas.width;
      const imgH = canvas.height;
      const mmPerPx = pageW / imgW;
      const totalHeightMm = imgH * mmPerPx;
      const pagesCount = Math.ceil(totalHeightMm / pageContentH);

      for (let p = 0; p < pagesCount; p++) {
        if (pageIndex > 0) pdf.addPage();
        pageIndex++;
        const srcYPx = Math.round((p * pageContentH) / mmPerPx);
        const srcHPx = Math.min(Math.round(pageContentH / mmPerPx), imgH - srcYPx);
        if (srcHPx <= 0) continue;

        const pageCanvas = document.createElement("canvas");
        pageCanvas.width = imgW;
        pageCanvas.height = srcHPx;
        const ctx = pageCanvas.getContext("2d")!;
        ctx.drawImage(canvas, 0, srcYPx, imgW, srcHPx, 0, 0, imgW, srcHPx);

        const dataUrl = pageCanvas.toDataURL("image/jpeg", 0.92);
        const imgHMm = srcHPx * mmPerPx;
        pdf.addImage(dataUrl, "JPEG", MARGIN, MARGIN, pageW, imgHMm, undefined, "FAST");
      }
    }
  } finally {
    document.body.removeChild(clone);
  }

  onProgress?.({ stage: "Opening PDF in new tab…", pct: 95 });

  // Generate blob and open in new tab — no print dialog
  const blob = pdf.output("blob");
  const url = URL.createObjectURL(blob);
  const tab = window.open(url, "_blank");

  // Revoke URL after a delay so the tab has time to load it
  setTimeout(() => URL.revokeObjectURL(url), 60_000);

  if (!tab) {
    // Fallback: trigger download if popup was blocked
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
  }

  onProgress?.({ stage: "Done", pct: 100 });
}
