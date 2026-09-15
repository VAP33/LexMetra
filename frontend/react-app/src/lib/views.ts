/** Inspector view registry. FE-01 owns this map; EVID-01/CON-01/FE-02 add views here
 * rather than growing a second navigator. Navigation is internal view-state
 * (no router package) so a later agent can wrap these in real routes without
 * rewriting screens. */
export type View =
  | "home"
  | "history"
  | "register"
  | "reviewQueue"
  | "profile"
  | "scan"
  | "scanDetails"
  | "processing"
  | "result"
  | "detail"
  | "evidence"
  | "report";

/** Scan capture/processing hides chrome so the camera has the full viewport. */
export const FOCUSED_FLOW_VIEWS: View[] = ["scan", "scanDetails", "processing"];

export function isFocusedFlow(view: View): boolean {
  return FOCUSED_FLOW_VIEWS.includes(view);
}
